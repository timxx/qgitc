# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, Signal

from qgitc.common import fullRepoDir
from qgitc.gitutils import Git
from qgitc.resolver.enums import ResolveOperation, ResolveOutcomeStatus
from qgitc.resolver.models import ResolveOutcome
from qgitc.resolver.resolvepanel import ResolvePanel


class CherryPickItemStatus:
    PENDING = "pending"
    PICKED = "picked"
    NEEDS_RESOLUTION = "needsResolution"
    FAILED = "failed"
    ABORTED = "aborted"


@dataclass
class CherryPickItem:
    sha1: str
    repoDir: Optional[str] = None
    sourceIndex: Optional[int] = None


@dataclass
class _ActiveStep:
    itemIndex: int
    item: CherryPickItem
    targetRepoDir: str
    sourceRepoDir: str


class CherryPickSession(QObject):
    """Async multi-commit cherry-pick runner with conflict resolution via ResolvePanel.

    - Runs git commands in TaskRunner threads (via ResolvePanel's TaskRunner).
    - Keeps UI responsive.
    - Supports "abort safely" (stop after current step boundary).
    """

    statusTextChanged = Signal(str)
    progressChanged = Signal(int, int)  # current, total

    itemStarted = Signal(int, object)  # itemIndex, CherryPickItem
    itemStatusChanged = Signal(int, str, str)  # itemIndex, status, message

    conflictsDetected = Signal(object, object)  # ResolveOperation, List[str]

    # ok, aborted, needReload, message
    finished = Signal(bool, bool, bool, str)

    def __init__(
        self,
        *,
        resolvePanel: ResolvePanel,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)

        self._resolvePanel = resolvePanel
        self._resolvePanel.currentFileChanged.connect(
            self._onResolveCurrentFileChanged)
        self._resolvePanel.fileOutcome.connect(self._onResolveFileOutcome)
        self._resolvePanel.finalizeOutcome.connect(
            self._onResolveFinalizeOutcome)
        self._resolvePanel.abortSafePointReached.connect(
            self._onResolveAbortSafePoint)

        self._items: List[CherryPickItem] = []
        self._steps: List[_ActiveStep] = []
        self._stepIndex = 0
        self._needReload = False

        self._recordOrigin = True
        self._aiChatWidget = None
        self._allowPatchPick = True

        self._applyLocalChangesFn: Optional[Callable[[
            str, str, str], bool]] = None

        self._abortRequested = False
        self._inConflictResolution = False
        self._activeOperation: Optional[ResolveOperation] = None
        self._activeRepoDir: Optional[str] = None
        self._activeSha1: str = ""
        self._activeInitialError: str = ""
        self._conflictFiles: List[str] = []
        self._failedConflictMessage: Optional[str] = None

        self._markCallback: Optional[Callable[[str, bool], None]] = None

        self._finishedOnce = False
        self._reportFile = None

    def setMarkCallback(self, callback: Optional[Callable[[str, bool], None]]):
        self._markCallback = callback

    def setAiChatWidget(self, chatWidget: Optional[object]):
        self._aiChatWidget = chatWidget

    def setReportFile(self, reportFile: Optional[str]):
        self._reportFile = reportFile

    def start(
        self,
        *,
        items: List[CherryPickItem],
        targetBaseRepoDir: str,
        sourceBaseRepoDir: str,
        recordOrigin: bool,
        allowPatchPick: bool = True,
        applyLocalChangesFn: Optional[Callable[[str, str, str], bool]] = None,
    ):
        self._items = list(items or [])
        self._steps = []
        for i, item in enumerate(self._items):
            sha1 = (item.sha1 or "").strip()
            if not sha1:
                continue
            targetRepoDir = fullRepoDir(item.repoDir, targetBaseRepoDir)
            sourceRepoDir = fullRepoDir(item.repoDir, sourceBaseRepoDir)
            self._steps.append(_ActiveStep(
                itemIndex=i,
                item=item,
                targetRepoDir=targetRepoDir,
                sourceRepoDir=sourceRepoDir,
            ))

        self._stepIndex = 0
        self._needReload = False
        self._recordOrigin = bool(recordOrigin)
        self._allowPatchPick = bool(allowPatchPick)
        self._applyLocalChangesFn = applyLocalChangesFn
        self._abortRequested = False
        self._inConflictResolution = False
        self._activeOperation = None
        self._activeRepoDir = None
        self._activeSha1 = ""
        self._activeInitialError = ""
        self._conflictFiles = []
        self._failedConflictMessage = None

        self._finishedOnce = False

        self.progressChanged.emit(0, len(self._steps))
        self._setStatus(self.tr("Starting cherry-pick…"))
        self._runNextStep()

    def requestAbortSafely(self):
        self._abortRequested = True
        self._setStatus(
            self.tr("Abort requested; stopping after current step…"))
        if self._inConflictResolution:
            self._resolvePanel.requestAbortSafely()

    def _runNextStep(self):
        if self._abortRequested:
            self._finish(ok=False, aborted=True, message=self.tr("Aborted"))
            return

        if self._stepIndex >= len(self._steps):
            self._finish(ok=True, aborted=False, message=self.tr("Done"))
            return

        step = self._steps[self._stepIndex]
        self.progressChanged.emit(self._stepIndex, len(self._steps))
        self.itemStarted.emit(step.itemIndex, step.item)

        if step.item.sha1 in [Git.LUC_SHA1, Git.LCC_SHA1]:
            if self._applyLocalChangesFn is None:
                msg = self.tr("Local changes are not supported in this mode")
                self._mark(step.item.sha1, False)
                self.itemStatusChanged.emit(
                    step.itemIndex, CherryPickItemStatus.FAILED, msg)
                self._finish(ok=False, aborted=False, message=msg)
                return

            self._setStatus(self.tr("Applying local changes…"))
            ok = self._applyLocalChangesFn(
                step.targetRepoDir, step.item.sha1, step.sourceRepoDir)

            self._needReload = self._needReload or ok
            self._mark(step.item.sha1, ok)
            self.itemStatusChanged.emit(
                step.itemIndex,
                CherryPickItemStatus.PICKED if ok else CherryPickItemStatus.FAILED,
                "",
            )
            if not ok:
                self._finish(ok=False, aborted=False, message=self.tr(
                    "Failed to apply local changes"))
                return

            self._stepIndex += 1
            self._runNextStep()
            return

        self._setStatus(
            self.tr("Cherry-picking {0}…").format(step.item.sha1[:7]))

        runner = self._resolvePanel._runner  # shared TaskRunner
        task = runner.run(lambda: Git.cherryPick(
            [step.item.sha1],
            recordOrigin=self._recordOrigin,
            repoDir=step.targetRepoDir,
        ))
        task.finished.connect(
            lambda ok, result, error, s=step: self._onCherryPickFinished(ok, result, error, s))

    def _onCherryPickFinished(self, ok: bool, result: object, error: object, step: _ActiveStep):
        if self._abortRequested:
            # If cherry-pick entered in-progress state, abort at next boundary.
            if Git.isCherryPicking(step.targetRepoDir):
                self._abortInProgressOperation(
                    step.targetRepoDir, ResolveOperation.CHERRY_PICK)
                return
            self._finish(ok=False, aborted=True, message=self.tr("Aborted"))
            return

        if not ok:
            msg = str(error or self.tr("Cherry-pick failed"))
            self._mark(step.item.sha1, False)
            self.itemStatusChanged.emit(
                step.itemIndex, CherryPickItemStatus.FAILED, msg)
            self._finish(ok=False, aborted=False, message=msg)
            return

        ret, err, _ = result if isinstance(result, tuple) and len(
            result) == 3 else (1, None, None)
        if ret == 0:
            self._needReload = True
            self._mark(step.item.sha1, True)
            self.itemStatusChanged.emit(
                step.itemIndex, CherryPickItemStatus.PICKED, "")
            self._stepIndex += 1
            self._runNextStep()
            return

        errText = (err or "").strip()

        # External drop: commit missing in target repo, pick via patch.
        if self._allowPatchPick and errText and ("fatal: bad object" in errText) and step.sourceRepoDir:
            self._setStatus(self.tr("Picking from another repo…"))
            runner = self._resolvePanel._runner
            task = runner.run(lambda: self._pickFromAnotherRepo(
                step.targetRepoDir, step.sourceRepoDir, step.item.sha1))
            task.finished.connect(lambda ok2, result2, error2, s=step: self._onPickFromAnotherRepoFinished(
                ok2, result2, error2, s))
            return

        # Conflict: git started cherry-pick sequence.
        if Git.isCherryPicking(step.targetRepoDir):
            self._mark(step.item.sha1, False)
            self.itemStatusChanged.emit(
                step.itemIndex, CherryPickItemStatus.NEEDS_RESOLUTION, "")
            self._startConflictResolution(
                repoDir=step.targetRepoDir,
                operation=ResolveOperation.CHERRY_PICK,
                sha1=step.item.sha1,
                initialError=errText,
            )
            return

        self._mark(step.item.sha1, False)
        self.itemStatusChanged.emit(
            step.itemIndex, CherryPickItemStatus.FAILED, errText)
        self._finish(ok=False, aborted=False,
                     message=errText or self.tr("Cherry-pick failed"))

    def _pickFromAnotherRepo(self, repoDir: str, sourceRepoDir: str, sha1: str):
        patchFile = None
        try:
            # Generate patch from source repo.
            args = ["format-patch", "-1", "--stdout", sha1]
            process = Git.run(args, repoDir=sourceRepoDir, text=True)
            patchContent, error = process.communicate()
            if process.returncode != 0:
                return process.returncode, (error or "").strip(), None
            if not patchContent:
                return 1, self.tr("No patch content generated"), None

            with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False, encoding="utf-8") as f:
                patchFile = f.name
                f.write(patchContent)

            # Apply patch to target repo.
            args = ["am", "--3way", "--ignore-space-change", patchFile]
            process = Git.run(args, repoDir=repoDir, text=True)
            _, error2 = process.communicate()
            if process.returncode != 0:
                return process.returncode, (error2 or "").strip(), None
            return 0, None, None
        finally:
            if patchFile and os.path.exists(patchFile):
                try:
                    os.remove(patchFile)
                except Exception:
                    pass

    def _onPickFromAnotherRepoFinished(self, ok: bool, result: object, error: object, step: _ActiveStep):
        if self._abortRequested:
            if Git.isApplying(step.targetRepoDir):
                self._abortInProgressOperation(
                    step.targetRepoDir, ResolveOperation.AM)
                return
            self._finish(ok=False, aborted=True, message=self.tr("Aborted"))
            return

        if not ok:
            msg = str(error or self.tr("Pick failed"))
            self._mark(step.item.sha1, False)
            self.itemStatusChanged.emit(
                step.itemIndex, CherryPickItemStatus.FAILED, msg)
            self._finish(ok=False, aborted=False, message=msg)
            return

        ret, err, _ = result if isinstance(result, tuple) and len(
            result) == 3 else (1, None, None)
        if ret == 0:
            self._needReload = True
            self._mark(step.item.sha1, True)
            self.itemStatusChanged.emit(
                step.itemIndex, CherryPickItemStatus.PICKED, "")
            self._stepIndex += 1
            self._runNextStep()
            return

        errText = (err or "").strip()
        if Git.isApplying(step.targetRepoDir):
            self._mark(step.item.sha1, False)
            self.itemStatusChanged.emit(
                step.itemIndex, CherryPickItemStatus.NEEDS_RESOLUTION, "")
            self._startConflictResolution(
                repoDir=step.targetRepoDir,
                operation=ResolveOperation.AM,
                sha1=step.item.sha1,
                initialError=errText,
            )
            return

        self._mark(step.item.sha1, False)
        self.itemStatusChanged.emit(
            step.itemIndex, CherryPickItemStatus.FAILED, errText)
        self._finish(ok=False, aborted=False,
                     message=errText or self.tr("Pick failed"))

    def _startConflictResolution(self, *, repoDir: str, operation: ResolveOperation, sha1: str, initialError: str):
        self._inConflictResolution = True
        self._activeOperation = operation
        self._activeRepoDir = repoDir
        self._activeSha1 = sha1
        self._activeInitialError = initialError or ""
        self._failedConflictMessage = None

        self._conflictFiles = Git.conflictFiles(repoDir) or []
        self.conflictsDetected.emit(operation, self._conflictFiles)

        self._resolvePanel.clear()
        self._resolvePanel.setContext(
            repoDir=repoDir,
            operation=operation,
            sha1=sha1,
            initialError=initialError or "",
            chatWidget=self._aiChatWidget,
            reportFile=self._reportFile,
        )
        self._resolvePanel.setConflictFiles(self._conflictFiles)
        self._resolvePanel.startResolveAll()

    def _onResolveFileOutcome(self, path: str, outcome: ResolveOutcome):
        if not self._inConflictResolution:
            return
        if outcome.status != ResolveOutcomeStatus.RESOLVED:
            self._failedConflictMessage = outcome.message or self.tr(
                "Resolve failed")

    def _onResolveCurrentFileChanged(self, pathObj: object):
        if not self._inConflictResolution:
            return

        if pathObj is not None:
            # A (re-)resolve attempt is starting. Clear any previous failure latch so
            # a successful retry can proceed to finalize.
            self._failedConflictMessage = None
            return

        # Queue finished.
        if self._abortRequested:
            # Wait for panel safe point, then abort.
            return

        if self._failedConflictMessage:
            self._setStatus(self.tr("Resolve needs user action"))
            if 0 <= self._stepIndex < len(self._steps):
                step = self._steps[self._stepIndex]
                if step.item.sha1 == self._activeSha1:
                    self.itemStatusChanged.emit(
                        step.itemIndex,
                        CherryPickItemStatus.NEEDS_RESOLUTION,
                        self._failedConflictMessage or self.tr("Resolve needs user action"),
                    )
            # Do not finish the session; allow the user to retry resolving.
            return

        # All files resolved, try to finalize.
        self._setStatus(self.tr("Finalizing…"))
        self._resolvePanel.startFinalize()

    def _onResolveFinalizeOutcome(self, outcome: ResolveOutcome):
        if not self._inConflictResolution:
            return

        if self._abortRequested:
            return

        if outcome.status == ResolveOutcomeStatus.RESOLVED:
            # If operation is still in progress and conflicts remain, loop again.
            repoDir = self._activeRepoDir or ""
            op = self._activeOperation
            inProgress = False
            if op == ResolveOperation.CHERRY_PICK:
                inProgress = Git.isCherryPicking(repoDir)
            elif op == ResolveOperation.AM:
                inProgress = Git.isApplying(repoDir)

            if inProgress:
                conflictFiles = Git.conflictFiles(repoDir) or []
                if conflictFiles:
                    self._resolvePanel.setConflictFiles(conflictFiles)
                    self._resolvePanel.startResolveAll()
                    return

            # Done resolving this commit.
            self._inConflictResolution = False
            self._needReload = True

            # Once resolved + finalized, the item should be marked as picked.
            if 0 <= self._stepIndex < len(self._steps):
                step = self._steps[self._stepIndex]
                if step.item.sha1 == self._activeSha1:
                    self._mark(step.item.sha1, True)
                    self.itemStatusChanged.emit(
                        step.itemIndex, CherryPickItemStatus.PICKED, "")

            self._stepIndex += 1
            self._runNextStep()
            return

        msg = outcome.message or self.tr("Finalize failed")
        aborted = outcome.status == ResolveOutcomeStatus.ABORTED
        self._finish(ok=False, aborted=aborted, message=msg)

    def _onResolveAbortSafePoint(self):
        if not self._abortRequested:
            return

        repoDir = self._activeRepoDir
        op = self._activeOperation
        if not repoDir or op is None:
            self._finish(ok=False, aborted=True, message=self.tr("Aborted"))
            return

        self._abortInProgressOperation(repoDir, op)

    def _abortInProgressOperation(self, repoDir: str, operation: ResolveOperation):
        runner = self._resolvePanel._runner

        if operation == ResolveOperation.CHERRY_PICK:
            task = runner.run(lambda: Git.cherryPickAbort(repoDir))
        else:
            task = runner.run(lambda: Git.amAbort(repoDir))

        task.finished.connect(lambda ok, result, error: self._finish(
            ok=False,
            aborted=True,
            message=self.tr("Aborted"),
        ))

    def _mark(self, sha1: str, ok: bool):
        if self._markCallback is None:
            return
        try:
            self._markCallback(sha1, ok)
        except Exception:
            pass

    def _setStatus(self, text: str):
        self.statusTextChanged.emit(text)

    def _finish(self, *, ok: bool, aborted: bool, message: str):
        if self._finishedOnce:
            return
        self._finishedOnce = True

        self.progressChanged.emit(
            min(self._stepIndex, len(self._steps)), len(self._steps))
        self.finished.emit(ok, aborted, self._needReload, message or "")
