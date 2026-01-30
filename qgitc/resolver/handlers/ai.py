# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List, Optional

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
        self._paths: List[str] = []
        self._i = 0

    def start(self, ctx: ResolveContext, services: ResolveServices):
        self._ctx = ctx
        self._services = services
        if not ctx.policy.aiAutoResolveEnabled:
            self.finished.emit(False, None)
            return
        if services.ai is None:
            self.finished.emit(False, None)
            return

        # Determine which files to resolve.
        if ctx.paths:
            self._paths = list(ctx.paths)
        else:
            # Could be expensive; run in thread.
            runner = services.runner
            task = runner.run(lambda: Git.conflictFiles(ctx.repoDir) or [])
            task.finished.connect(self._onConflictFiles)
            return

        self._i = 0
        self._nextFile()

    def _onConflictFiles(self, ok: bool, result: object, error: object):
        if not ok:
            self.finished.emit(False, None)
            return
        self._paths = list(result or [])
        self._i = 0
        self._nextFile()

    def _emit(self, ev: ResolveEvent):
        self._services.manager.emitEvent(ev)

    def _nextFile(self):
        ctx = self._ctx
        services = self._services
        if ctx is None or services is None:
            self.finished.emit(False, None)
            return

        if self._i >= len(self._paths):
            # Check remaining conflicts
            runner = services.runner
            task = runner.run(lambda: Git.conflictFiles(ctx.repoDir) or [])
            task.finished.connect(self._onFinalRemaining)
            return

        path = self._paths[self._i]
        self._i += 1

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
            self._nextFile()
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
            self._nextFile()
            return

        if mode != "non_trivial":
            self._nextFile()
            return

        conflictText = buildConflictExcerpt(ctx.repoDir, path)
        if not conflictText:
            self._nextFile()
            return

        self._emit(ResolveEvent(kind=ResolveEventKind.STEP,
                   message=f"ai_resolving:{path}", path=path, method=ResolveMethod.AI))

        job = services.ai.resolveFileAsync(
            ctx.repoDir, ctx.sha1, path, conflictText, ctx.extraContext
        )
        job.finished.connect(
            lambda ok3, reason: self._afterAi(path, ok3, reason))

    def _afterAi(self, path: str, ok: bool, reason: object):
        ctx = self._ctx
        services = self._services
        if ctx is None or services is None:
            self.finished.emit(False, None)
            return

        if not ok:
            # Leave it for next handler.
            self._nextFile()
            return

        addTask = services.runner.run(
            lambda: Git.addFiles(ctx.repoDir, [path]))
        addTask.finished.connect(
            lambda ok2, res2, err2: self._afterAdd(path, "ai", ok2, res2, err2))

    def _afterAdd(self, path: str, mode: str, ok: bool, result: object, error: object):
        if ok and not result:
            m = ResolveMethod.AI if mode == "ai" else (
                ResolveMethod.OURS if mode == "take_ours" else ResolveMethod.THEIRS)
            self._emit(ResolveEvent(kind=ResolveEventKind.FILE_RESOLVED,
                       message="file_resolved", path=path, method=m))
        self._nextFile()

    def _onFinalRemaining(self, ok: bool, result: object, error: object):
        remaining = list(result or []) if ok else []
        if remaining:
            out = ResolveOutcome(
                status=ResolveOutcomeStatus.NEEDS_USER,
                message="ai_needs_user",
                remainingConflicts=remaining,
            )
            self.finished.emit(True, out)
            return
        out = ResolveOutcome(
            status=ResolveOutcomeStatus.RESOLVED, message="ai_resolved")
        self.finished.emit(True, out)
