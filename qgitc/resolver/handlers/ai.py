# -*- coding: utf-8 -*-

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject

from qgitc.common import buildConflictExcerpt
from qgitc.gitutils import Git
from qgitc.resolver.enums import ResolveEventKind, ResolveMethod, ResolveOutcomeStatus
from qgitc.resolver.handlers.base import ResolveHandler
from qgitc.resolver.models import ResolveContext, ResolveEvent, ResolveOutcome
from qgitc.resolver.services import ResolveServices


class AiResolveHandler(ResolveHandler):

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._ctx: Optional[ResolveContext] = None
        self._services: ResolveServices = None
        self._path: Optional[str] = None
        self._job = None

    def start(self, ctx: ResolveContext, services: ResolveServices):
        self._ctx = ctx
        self._services = services
        self._path = ctx.path
        if services.ai is None:
            self.finished.emit(False, None)
            return

        self._resolveFile(self._path)

    def cancel(self):
        if self._job:
            self._job.abort()

    def _emit(self, ev: ResolveEvent):
        self._services.manager.emitEvent(ev)

    def _resolveFile(self, path: str):
        ctx = self._ctx
        services = self._services

        # Fast-path checks via blob ids.
        def _trivial() -> str:
            stageIds = Git.getConflictFileBlobIds(path, ctx.repoDir)
            baseId = stageIds.get(1)
            oursId = stageIds.get(2)
            theirsId = stageIds.get(3)
            if not oursId or not theirsId:
                return "skip_missing_stage"
            if oursId == theirsId:
                return "take_ours" if Git.resolveBy(True, path, repoDir=ctx.repoDir) else "fail_checkout_ours"
            if baseId == oursId:
                return "take_theirs" if Git.resolveBy(False, path, repoDir=ctx.repoDir) else "fail_checkout_theirs"
            if baseId == theirsId:
                return "take_ours" if Git.resolveBy(True, path, repoDir=ctx.repoDir) else "fail_checkout_ours"
            return "non_trivial"

        runner = services.runner
        task = runner.run(_trivial)
        task.finished.connect(
            lambda ok, res, err: self._afterTrivial(path, ok, res, err))

    def _afterTrivial(self, path: str, ok: bool, result: object, error: object):
        ctx = self._ctx
        services = self._services
        if ctx is None or services is None:
            self.finished.emit(False, None)
            return

        if not ok:
            self.finished.emit(False, None)
            return

        mode = str(result)
        if mode in ("take_ours", "take_theirs"):
            # Stage.
            addTask = services.runner.run(
                lambda: Git.addFiles(ctx.repoDir, [path]))
            addTask.finished.connect(
                lambda ok2, res2, err2: self._afterAdd(path, mode, ok2, res2, err2))
            return

        if mode.startswith("fail_"):
            self.finished.emit(False, None)
            return

        if mode != "non_trivial":
            self.finished.emit(False, None)
            return

        if self._isLikelyBinaryPath(path) or self._isLikelyBinaryWorktreeFile(ctx.repoDir, path):
            self._emit(
                ResolveEvent(
                    kind=ResolveEventKind.STEP,
                    message=self.tr(
                        "Unhandled (binary file): {path}").format(path=path),
                    path=path,
                    method=ResolveMethod.AI,
                )
            )
            # Leave it for next handler.
            self.finished.emit(False, None)
            return

        conflictText = buildConflictExcerpt(ctx.repoDir, path)
        if not conflictText:
            self.finished.emit(False, None)
            return

        self._emit(
            ResolveEvent(
                kind=ResolveEventKind.STEP,
                message=self.tr(
                    "Assistant is resolving {path}").format(path=path),
                path=path,
                method=ResolveMethod.AI,
            )
        )

        self._job = services.ai.resolveFileAsync(
            ctx.repoDir, ctx.sha1, path, conflictText, ctx.context,
            ctx.reportFile
        )
        self._job.finished.connect(
            lambda ok3, reason: self._afterAi(path, ok3, reason))

    def _isLikelyBinaryPath(self, path: str) -> bool:
        # Fast extension check to avoid reading huge files / blobs.
        _, ext = os.path.splitext(path.lower())
        if not ext:
            return False
        return ext in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".tif",
            ".tiff",
            ".ico",
            ".webp",
            ".svgz",
            ".pdf",
            ".zip",
            ".7z",
            ".rar",
            ".gz",
            ".bz2",
            ".xz",
            ".tar",
            ".exe",
            ".dll",
            ".pdb",
            ".so",
            ".dylib",
            ".bin",
            ".class",
            ".jar",
            ".pyc",
            ".mp3",
            ".wav",
            ".flac",
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
        }

    def _isLikelyBinaryWorktreeFile(self, repoDir: str, path: str) -> bool:
        absPath = os.path.join(repoDir, path)
        try:
            with open(absPath, "rb") as f:
                sample = f.read(4096)
        except Exception:
            return False

        if not sample:
            return False
        if b"\x00" in sample:
            return True

        # Heuristic: if a significant portion of bytes are control chars, treat as binary.
        control = 0
        for b in sample:
            if b < 9 or (13 < b < 32):
                control += 1
        return (control / max(1, len(sample))) > 0.30

    def _afterAi(self, path: str, ok: bool, reason: object):
        ctx = self._ctx
        self._job = None
        services = self._services
        if ctx is None or services is None:
            self.finished.emit(False, None)
            return

        if not ok:
            # Leave it for next handler.
            self.finished.emit(False, None)
            return

        addTask = services.runner.run(
            lambda: Git.addFiles(ctx.repoDir, [path]))
        addTask.finished.connect(
            lambda ok2, res2, err2: self._afterAdd(path, "ai", ok2, res2, err2))

    def _afterAdd(self, path: str, mode: str, ok: bool, result: object, error: object):
        if ok and not result:
            m = ResolveMethod.AI if mode == "ai" else (
                ResolveMethod.OURS if mode == "take_ours" else ResolveMethod.THEIRS)
            self._emit(
                ResolveEvent(
                    kind=ResolveEventKind.FILE_RESOLVED,
                    message=self.tr("Resolved {path}").format(path=path),
                    path=path,
                    method=m,
                )
            )

            out = ResolveOutcome(
                status=ResolveOutcomeStatus.RESOLVED,
                message=self.tr("Resolved by assistant"),
            )
            self.finished.emit(True, out)
            return

        # Staging failed, let next handler attempt.
        self.finished.emit(False, None)
