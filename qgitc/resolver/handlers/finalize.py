# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject

from qgitc.gitutils import Git
from qgitc.resolver.enums import (
    ResolveOperation,
    ResolveOutcomeStatus,
    ResolvePromptKind,
)
from qgitc.resolver.handlers.base import ResolveHandler
from qgitc.resolver.models import ResolveContext, ResolveOutcome, ResolvePrompt
from qgitc.resolver.services import ResolveServices


class CherryPickFinalizeHandler(ResolveHandler):

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._ctx: Optional[ResolveContext] = None
        self._services: ResolveServices = None
        self._promptId = 1
        self._awaitingPrompt = False
        self._pendingPrompt: Optional[ResolvePrompt] = None

    def start(self, ctx: ResolveContext, services: ResolveServices):
        self._ctx = ctx
        self._services = services
        self._awaitingPrompt = False
        self._pendingPrompt = None

        if ctx.operation != ResolveOperation.CHERRY_PICK:
            self.finished.emit(False, None)
            return

        task = services.runner.run(lambda: Git.cherryPickContinue(ctx.repoDir))
        task.finished.connect(self._onContinue)

    def onPromptReply(self, promptId: int, choice: str):
        if not self._awaitingPrompt or not self._pendingPrompt:
            return
        if self._pendingPrompt.promptId != promptId:
            return

        ctx = self._ctx
        services = self._services
        if ctx is None or services is None:
            self.finished.emit(True, ResolveOutcome(
                status=ResolveOutcomeStatus.FAILED,
                message=self.tr("Cherry-pick failed"),
            ))
            return

        if choice == "skip":
            task = services.runner.run(lambda: Git.cherryPickSkip(ctx.repoDir))
            task.finished.connect(lambda ok, res, err: self._finishFromGitTuple(
                ok, res, err,
                okMessage=self.tr("Skipped empty commit"),
                failFallback=self.tr("Failed to skip empty commit"),
                statusOnSuccess=ResolveOutcomeStatus.RESOLVED,
            ))
            return

        if choice == "allow-empty":
            task = services.runner.run(
                lambda: Git.cherryPickAllowEmpty(ctx.repoDir))
            task.finished.connect(lambda ok, res, err: self._finishFromGitTuple(
                ok, res, err,
                okMessage=self.tr("Created empty commit"),
                failFallback=self.tr("Failed to create empty commit"),
                statusOnSuccess=ResolveOutcomeStatus.RESOLVED,
            ))
            return

        # Default: abort
        task = services.runner.run(lambda: Git.cherryPickAbort(ctx.repoDir))
        task.finished.connect(lambda ok, res, err: self._finishFromGitTuple(
            ok, res, err,
            okMessage=self.tr("Cherry-pick aborted"),
            failFallback=self.tr("Failed to abort cherry-pick"),
            statusOnSuccess=ResolveOutcomeStatus.ABORTED,
        ))

    def _onContinue(self, ok: bool, result: object, error: object):
        if not ok:
            self.finished.emit(True, ResolveOutcome(
                status=ResolveOutcomeStatus.FAILED,
                message=self.tr("Cherry-pick failed"),
            ))
            return

        ret, err = result if isinstance(
            result, tuple) and len(result) == 2 else (1, None)
        if ret == 0:
            self.finished.emit(True, ResolveOutcome(
                status=ResolveOutcomeStatus.RESOLVED,
                message=self.tr("Cherry-pick continued"),
            ))
            return

        errText = (err or "").strip()
        if errText and "git commit --allow-empty" in errText:
            # Delegate choice to UI.
            p = ResolvePrompt(
                promptId=self._promptId,
                kind=ResolvePromptKind.EMPTY_COMMIT_CHOICE,
                title=self.tr("Empty Cherry-pick"),
                text=self.tr(
                    "This cherry-pick results in an empty commit (possibly already applied).\n\n"
                    "What do you want to do?"
                ),
                options=["skip", "allow-empty", "abort"],
                meta={"sha1": (self._ctx.sha1 if self._ctx else "")},
            )
            self._promptId += 1
            self._awaitingPrompt = True
            self._pendingPrompt = p
            self._services.manager.requestPrompt(p)
            return

        # Any other error means the cherry-pick still needs user action.
        self.finished.emit(True, ResolveOutcome(
            status=ResolveOutcomeStatus.NEEDS_USER,
            message=errText or self.tr("Cherry-pick could not continue"),
        ))

    def _finishFromGitTuple(
        self,
        ok: bool,
        result: object,
        error: object,
        *,
        okMessage: str,
        failFallback: str,
        statusOnSuccess: ResolveOutcomeStatus,
    ):
        if not ok:
            self.finished.emit(True, ResolveOutcome(
                status=ResolveOutcomeStatus.FAILED,
                message=failFallback,
            ))
            return

        ret, err = result if isinstance(
            result, tuple) and len(result) == 2 else (1, None)
        if ret == 0:
            self.finished.emit(True, ResolveOutcome(
                status=statusOnSuccess,
                message=okMessage,
            ))
            return

        errText = (err or "").strip()
        self.finished.emit(True, ResolveOutcome(
            status=ResolveOutcomeStatus.FAILED,
            message=errText or failFallback,
        ))


class AmFinalizeHandler(ResolveHandler):

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._ctx: Optional[ResolveContext] = None
        self._services: ResolveServices = None

    def start(self, ctx: ResolveContext, services: ResolveServices):
        self._ctx = ctx
        self._services = services

        if ctx.operation != ResolveOperation.AM:
            self.finished.emit(False, None)
            return

        task = services.runner.run(lambda: Git.amContinue(ctx.repoDir))
        task.finished.connect(self._onContinue)

    def _onContinue(self, ok: bool, result: object, error: object):
        if not ok:
            self.finished.emit(True, ResolveOutcome(
                status=ResolveOutcomeStatus.FAILED,
                message=self.tr("Apply patch failed"),
            ))
            return

        ret, err = result if isinstance(
            result, tuple) and len(result) == 2 else (1, None)
        if ret == 0:
            self.finished.emit(True, ResolveOutcome(
                status=ResolveOutcomeStatus.RESOLVED,
                message=self.tr("Apply patch continued"),
            ))
            return

        errText = (err or "").strip()
        self.finished.emit(True, ResolveOutcome(
            status=ResolveOutcomeStatus.NEEDS_USER,
            message=errText or self.tr("Apply patch could not continue"),
        ))
