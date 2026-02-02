# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.resolver.enums import (
    ResolveEventKind,
    ResolveOperation,
    ResolveOutcomeStatus,
    ResolvePromptKind,
)
from qgitc.resolver.handlers.finalize import (
    AmFinalizeHandler,
    CherryPickFinalizeHandler,
)
from qgitc.resolver.helpers import buildResolveHandlers
from qgitc.resolver.manager import ResolveManager
from qgitc.resolver.models import (
    ResolveContext,
    ResolveEvent,
    ResolveOutcome,
    ResolvePrompt,
)
from qgitc.resolver.services import ResolveServices
from qgitc.resolver.taskrunner import TaskRunner


class _FileState:
    PENDING = 0
    RESOLVED = 1
    FAILED = 2


@dataclass
class ResolvePanelContext:
    repoDir: str
    operation: ResolveOperation
    sha1: str
    initialError: str = ""
    context: Optional[str] = None
    chatWidget: Optional[object] = None


class ResolvePanel(QWidget):
    """Shared resolve UI component for in-progress git operations.

    Designed to be embedded in other windows (cherry-pick progress, merge window, etc).
    Runs ResolveManager asynchronously and keeps UI responsive.
    """

    statusTextChanged = Signal(str)
    currentFileChanged = Signal(object)  # str|None

    conflictFilesChanged = Signal(object)  # list[str]
    eventEmitted = Signal(object)  # ResolveEvent

    fileOutcome = Signal(str, object)  # path, ResolveOutcome
    finalizeOutcome = Signal(object)  # ResolveOutcome

    abortSafePointReached = Signal()
    aiAutoResolveToggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._ctx: Optional[ResolvePanelContext] = None
        self._runner = TaskRunner(self)
        self._services: Optional[ResolveServices] = None

        self._manager: Optional[ResolveManager] = None
        self._abortRequested = False

        self._fileStates: Dict[str, int] = {}
        self._queue: List[str] = []
        self._currentPath: Optional[str] = None

        self._setupUi()

    def _setupUi(self):
        frame = QFrame(self)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setFrameShadow(QFrame.Shadow.Raised)

        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.addWidget(frame)

        layout = QVBoxLayout(frame)
        self.setLayout(layout)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._label = QLabel(self.tr("No conflicts"), self)
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._label)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(self._list)

        actions = QHBoxLayout()
        self._resolveSelectedBtn = QPushButton(
            self.tr("Resolve selected"), self)
        self._resolveAllBtn = QPushButton(self.tr("Resolve all"), self)
        actions.addWidget(self._resolveSelectedBtn)
        actions.addWidget(self._resolveAllBtn)

        self._aiAutoResolveCheck = QCheckBox(self.tr("Auto-resolve"), self)
        self._aiAutoResolveCheck.setChecked(False)
        self._aiAutoResolveCheck.setToolTip(
            self.tr("Use assistant to auto-resolve conflicts if possible"))

        actions.addWidget(self._aiAutoResolveCheck)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.setVisible(False)

        self._resolveSelectedBtn.clicked.connect(self._onResolveSelected)
        self._resolveAllBtn.clicked.connect(self.startResolveAll)
        self._aiAutoResolveCheck.toggled.connect(self._onAiAutoResolveToggled)
        self._list.itemDoubleClicked.connect(self._onItemDoubleClicked)

        self._updateActionState()

    def setContext(
        self,
        *,
        repoDir: str,
        operation: ResolveOperation,
        sha1: str,
        initialError: str = "",
        context: Optional[str] = None,
        chatWidget: Optional[object] = None,
    ):
        self._ctx = ResolvePanelContext(
            repoDir=repoDir,
            operation=operation,
            sha1=sha1,
            initialError=initialError or "",
            context=context,
            chatWidget=chatWidget,
        )
        self._services = ResolveServices(runner=self._runner, ai=chatWidget)

    def setAiChatWidget(self, chatWidget: Optional[object]):
        """Enable/disable AI resolving for the current resolve context."""
        if self._ctx is not None:
            self._ctx.chatWidget = chatWidget
        if self._services is not None:
            self._services.ai = chatWidget

    def setAiAutoResolveEnabled(self, enabled: bool):
        self._aiAutoResolveCheck.setChecked(enabled)

    def isBusy(self) -> bool:
        return self._manager is not None

    def requestAbortSafely(self):
        self._abortRequested = True
        self._setStatus(
            self.tr("Abort requested; stopping after current step…"))
        if not self.isBusy():
            self.abortSafePointReached.emit()

        self._resolveAllBtn.setDisabled(True)
        self._resolveSelectedBtn.setDisabled(True)

    def clear(self):
        self._abortRequested = False
        self._queue.clear()
        self._currentPath = None
        self._fileStates.clear()
        self._list.clear()
        self.setVisible(False)
        self._setStatus(self.tr("No conflicts"))
        self._updateActionState()

    def setConflictFiles(self, files: List[str]):
        files = [f for f in (files or []) if f]

        # Preserve existing states where possible.
        for f in files:
            self._fileStates.setdefault(f, _FileState.PENDING)

        # Drop removed files.
        removed = [p for p in list(self._fileStates.keys()) if p not in files]
        for p in removed:
            del self._fileStates[p]

        self._renderFileList()
        self._label.setText(self.tr("Conflicts ({0})").format(len(files)))
        self.setVisible(bool(files))
        self.conflictFilesChanged.emit(files)
        self._updateActionState()

    def startResolveAll(self):
        if self._abortRequested:
            self.abortSafePointReached.emit()
            return
        if self.isBusy():
            return

        # "Resolve all" should retry files that previously failed.
        for p, st in list(self._fileStates.items()):
            if st == _FileState.FAILED:
                self._fileStates[p] = _FileState.PENDING

        pending = [p for p, st in self._fileStates.items() if st ==
                   _FileState.PENDING]
        self._queue = list(pending)
        self._startNextFile()
        self._updateActionState()

    def startResolveFile(self, path: str):
        if self._abortRequested:
            self.abortSafePointReached.emit()
            return
        if self.isBusy():
            return
        if not path:
            return

        self._queue = [path]
        self._startNextFile()
        self._updateActionState()

    def _onItemDoubleClicked(self, item: QListWidgetItem):
        if item is None or self._abortRequested:
            return
        self._retryResolveForPath(item.text())

    def _onResolveSelected(self):
        path = self._selectedPath()
        if not path:
            return
        self._retryResolveForPath(path)

    def _selectedPath(self) -> str:
        item = self._list.currentItem()
        return "" if item is None else str(item.text() or "")

    def _retryResolveForPath(self, path: str):
        if self.isBusy():
            return
        if not path:
            return
        st = self._fileStates.get(path)
        if st == _FileState.RESOLVED:
            return

        # Allow re-running after failure by putting the file back into pending.
        self._fileStates[path] = _FileState.PENDING
        self._renderFileList()
        self.startResolveFile(path)

    def _updateActionState(self):
        hasFiles = bool(self._fileStates)
        busy = self.isBusy() or self._abortRequested
        selected = bool(self._selectedPath())
        self._resolveSelectedBtn.setEnabled(hasFiles and selected and not busy)
        self._resolveAllBtn.setEnabled(hasFiles and not busy)

    def startFinalize(self):
        if self._abortRequested:
            self.abortSafePointReached.emit()
            return
        if self.isBusy():
            return

        ctx = self._ctx
        if ctx is None or self._services is None:
            self.finalizeOutcome.emit(ResolveOutcome(
                status=ResolveOutcomeStatus.FAILED,
                message=self.tr("Resolve context not set"),
            ))
            return

        if ctx.operation == ResolveOperation.CHERRY_PICK:
            handler = CherryPickFinalizeHandler(self)
        else:
            handler = AmFinalizeHandler(self)

        rc = ResolveContext(
            repoDir=ctx.repoDir,
            operation=ctx.operation,
            sha1=ctx.sha1,
            path="",
            initialError=ctx.initialError,
            context=ctx.context,
            mergetoolName=None,
        )

        self._startManager([handler], rc, isFinalize=True)

    def _startNextFile(self):
        if self._abortRequested:
            self.abortSafePointReached.emit()
            return

        if self.isBusy():
            return

        while self._queue:
            path = self._queue.pop(0)
            if self._fileStates.get(path) != _FileState.PENDING:
                continue
            self._startResolveForFile(path)
            return

        # Nothing else to do.
        self.currentFileChanged.emit(None)

    def _startResolveForFile(self, path: str):
        ctx = self._ctx
        services = self._services
        if ctx is None or services is None:
            out = ResolveOutcome(status=ResolveOutcomeStatus.FAILED,
                                 message=self.tr("Resolve context not set"))
            self.fileOutcome.emit(path, out)
            return

        handlers, mergeToolName, hasGitDefaultTool = buildResolveHandlers(
            parent=self,
            path=path,
            aiEnabled=bool(ctx.chatWidget is not None),
            chatWidget=ctx.chatWidget,
        )

        if not handlers:
            if not hasGitDefaultTool and ctx.chatWidget is None:
                QMessageBox.warning(
                    self,
                    self.tr("Merge Tool Not Configured"),
                    self.tr(
                        "No merge tool is configured.\n\n"
                        "Please configure a merge tool in:\n"
                        "- Git global config: git config --global merge.tool <tool-name>\n"
                        "- Or in Preferences > Tools tab"
                    ),
                )

            out = ResolveOutcome(
                status=ResolveOutcomeStatus.FAILED,
                message=self.tr("No resolve handler available"),
            )
            self._fileStates[path] = _FileState.FAILED
            self._renderFileList()
            self.fileOutcome.emit(path, out)
            return

        self._currentPath = path
        self.currentFileChanged.emit(path)
        self._setStatus(self.tr("Resolving {0}…").format(path))

        rc = ResolveContext(
            repoDir=ctx.repoDir,
            operation=ctx.operation,
            sha1=ctx.sha1,
            path=path,
            initialError=ctx.initialError,
            context=ctx.context,
            mergetoolName=mergeToolName,
        )

        self._startManager(handlers, rc, isFinalize=False)

    def _startManager(self, handlers, ctx: ResolveContext, *, isFinalize: bool):
        services = self._services
        if services is None:
            out = ResolveOutcome(status=ResolveOutcomeStatus.FAILED,
                                 message=self.tr("Resolve services not set"))
            if isFinalize:
                self.finalizeOutcome.emit(out)
            else:
                self.fileOutcome.emit(ctx.path, out)
            return

        manager = ResolveManager(handlers, services, parent=self)
        manager.promptRequested.connect(
            lambda p, m=manager: self._onPrompt(m, p))
        manager.eventEmitted.connect(self._onResolveEvent)

        if isFinalize:
            manager.completed.connect(
                lambda out: self._onFinalizeCompleted(out))
        else:
            manager.completed.connect(
                lambda out, p=ctx.path: self._onFileCompleted(p, out))

        self._manager = manager
        manager.start(ctx)

    def _onResolveEvent(self, ev: ResolveEvent):
        self.eventEmitted.emit(ev)
        if ev.kind == ResolveEventKind.STEP and ev.message:
            self._setStatus(ev.message)

    def _onFileCompleted(self, path: str, outcome: ResolveOutcome):
        self._manager = None

        if outcome.status == ResolveOutcomeStatus.RESOLVED:
            self._fileStates[path] = _FileState.RESOLVED
        else:
            self._fileStates[path] = _FileState.FAILED

        self._renderFileList()
        self.fileOutcome.emit(path, outcome)
        self._updateActionState()

        if self._abortRequested:
            self.abortSafePointReached.emit()
            return

        if outcome.status == ResolveOutcomeStatus.RESOLVED:
            self._startNextFile()

    def _onFinalizeCompleted(self, outcome: ResolveOutcome):
        self._manager = None
        self.finalizeOutcome.emit(outcome)
        self._updateActionState()
        if self._abortRequested:
            self.abortSafePointReached.emit()

    def _setStatus(self, text: str):
        self._label.setText(text)
        self.statusTextChanged.emit(text)

    def _renderFileList(self):
        self._list.clear()
        for path, st in sorted(self._fileStates.items(), key=lambda kv: kv[0]):
            item = QListWidgetItem(path)
            if st == _FileState.RESOLVED:
                item.setForeground(
                    ApplicationBase.instance().colorSchema().ResolvedFg)
            elif st == _FileState.FAILED:
                item.setForeground(
                    ApplicationBase.instance().colorSchema().ConflictFg)
            self._list.addItem(item)

        # Highlight current.
        if self._currentPath:
            matches = self._list.findItems(self._currentPath, Qt.MatchExactly)
            if matches:
                self._list.setCurrentItem(matches[0])

    def _onPrompt(self, manager: ResolveManager, prompt: ResolvePrompt):
        # Deleted merge conflict prompt - must be user-driven.
        if prompt.kind == ResolvePromptKind.DELETED_CONFLICT_CHOICE:
            text = prompt.text
            isCreated = bool((prompt.meta or {}).get("isCreated"))
            box = QMessageBox(
                QMessageBox.Question,
                ApplicationBase.instance().applicationName(),
                text,
                QMessageBox.NoButton,
                self,
            )
            primary = prompt.options[0] if prompt.options else "m"
            deleteOpt = prompt.options[1] if len(prompt.options) > 1 else "d"
            abortOpt = prompt.options[2] if len(prompt.options) > 2 else "a"

            primaryText = self.tr(
                "Use &created") if isCreated else self.tr("Use &modified")
            box.addButton(primaryText, QMessageBox.AcceptRole)
            box.addButton(self.tr("&Deleted file"), QMessageBox.RejectRole)
            box.addButton(QMessageBox.Abort)
            r = box.exec()
            if r == QMessageBox.AcceptRole:
                manager.replyPrompt(prompt.promptId, primary)
            elif r == QMessageBox.RejectRole:
                manager.replyPrompt(prompt.promptId, deleteOpt)
            else:
                manager.replyPrompt(prompt.promptId, abortOpt)
            return

        if prompt.kind == ResolvePromptKind.SYMLINK_CONFLICT_CHOICE:
            text = prompt.text
            box = QMessageBox(
                QMessageBox.Question,
                ApplicationBase.instance().applicationName(),
                text,
                QMessageBox.NoButton,
                self,
            )
            localOpt = prompt.options[0] if prompt.options else "l"
            remoteOpt = prompt.options[1] if len(prompt.options) > 1 else "r"
            abortOpt = prompt.options[2] if len(prompt.options) > 2 else "a"
            box.addButton(self.tr("Use &local"), QMessageBox.AcceptRole)
            box.addButton(self.tr("Use &remote"), QMessageBox.RejectRole)
            box.addButton(QMessageBox.Abort)
            r = box.exec()
            if r == QMessageBox.AcceptRole:
                manager.replyPrompt(prompt.promptId, localOpt)
            elif r == QMessageBox.RejectRole:
                manager.replyPrompt(prompt.promptId, remoteOpt)
            else:
                manager.replyPrompt(prompt.promptId, abortOpt)
            return

        if prompt.kind == ResolvePromptKind.EMPTY_COMMIT_CHOICE:
            sha1Meta = (prompt.meta or {}).get("sha1") or (
                self._ctx.sha1 if self._ctx else "")
            box = QMessageBox(self)
            box.setWindowTitle(prompt.title)
            box.setText(
                self.tr(
                    "Commit {0} results in an empty commit (possibly already applied).\n\n"
                    "What do you want to do?"
                ).format(str(sha1Meta)[:7])
            )
            skipBtn = box.addButton(self.tr("&Skip"), QMessageBox.AcceptRole)
            allowBtn = box.addButton(
                self.tr("&Create empty commit"), QMessageBox.ActionRole)
            abortBtn = box.addButton(QMessageBox.Abort)
            box.setDefaultButton(skipBtn)
            box.exec()
            clicked = box.clickedButton()
            if clicked == skipBtn:
                manager.replyPrompt(prompt.promptId, "skip")
            elif clicked == allowBtn:
                manager.replyPrompt(prompt.promptId, "allow-empty")
            else:
                manager.replyPrompt(prompt.promptId, "abort")
            return

    def _onAiAutoResolveToggled(self, checked: bool):
        self.aiAutoResolveToggled.emit(checked)
