# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from qgitc.aichatwidget import AiChatWidget
from qgitc.applicationbase import ApplicationBase
from qgitc.cherrypickprogressaichatcontextprovider import (
    CherryPickProgressAiChatContextProvider,
)
from qgitc.cherrypicksession import (
    CherryPickItem,
    CherryPickItemStatus,
    CherryPickSession,
)
from qgitc.resolver.enums import ResolveOperation
from qgitc.resolver.resolvepanel import ResolvePanel


class CherryPickProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(self.tr("Cherry-pick Progress"))
        self.setWindowFlag(Qt.WindowMinMaxButtonsHint)
        self.setModal(True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(900, 650)

        self._resolvePanel = ResolvePanel(self)
        self._session = CherryPickSession(
            resolvePanel=self._resolvePanel, parent=self)

        self._aiChatWidget: Optional[AiChatWidget] = None
        self._aiContextProvider: Optional[CherryPickProgressAiChatContextProvider] = None

        self._aiContainer: Optional[QWidget] = None
        self._aiContainerLayout: Optional[QVBoxLayout] = None

        self._items: List[CherryPickItem] = []
        self._reloadCallback: Optional[Callable[[], None]] = None
        self._ensureVisibleCallback: Optional[Callable[[int], None]] = None
        self._applyLocalChangesCallback: Optional[Callable[[
            str, str, str], bool]] = None

        self._setupUi()
        self._setupSignals()

    def _setupUi(self):
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 2-column layout: left column contains status/progress/list/resolve/buttons,
        # right column contains the embedded AI chat.
        self._mainSplitter = QSplitter(Qt.Horizontal, self)
        self._mainSplitter.setChildrenCollapsible(False)
        layout.addWidget(self._mainSplitter)

        leftPane = QWidget(self._mainSplitter)
        leftLayout = QVBoxLayout(leftPane)
        leftLayout.setContentsMargins(0, 0, 0, 0)
        leftLayout.setSpacing(4)

        self._status = QLabel(self.tr("Ready"), leftPane)
        self._status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        leftLayout.addWidget(self._status)

        self._progress = QProgressBar(leftPane)
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        leftLayout.addWidget(self._progress)

        self._aiAutoResolveCheck = QCheckBox(self.tr("Auto-resolve with AI"), leftPane)
        self._aiAutoResolveCheck.setChecked(False)
        self._aiAutoResolveCheck.setToolTip(
            self.tr("When enabled, conflicts are auto-resolved using the assistant. Disable to use merge tool only.")
        )
        leftLayout.addWidget(self._aiAutoResolveCheck)

        self._leftSplitter = QSplitter(Qt.Vertical, leftPane)
        self._leftSplitter.setChildrenCollapsible(False)

        self._list = QListWidget(self._leftSplitter)
        self._leftSplitter.addWidget(self._list)
        self._leftSplitter.addWidget(self._resolvePanel)
        self._leftSplitter.setStretchFactor(0, 2)
        self._leftSplitter.setStretchFactor(1, 3)
        leftLayout.addWidget(self._leftSplitter)

        self._buttons = QDialogButtonBox(leftPane)
        self._abortBtn = self._buttons.addButton(QDialogButtonBox.Abort)
        self._closeBtn = self._buttons.addButton(QDialogButtonBox.Close)
        self._closeBtn.setEnabled(False)
        leftLayout.addWidget(self._buttons)

        self._mainSplitter.addWidget(leftPane)

        self._aiContainer = QWidget(self._mainSplitter)
        self._aiContainerLayout = QVBoxLayout(self._aiContainer)
        self._aiContainerLayout.setContentsMargins(0, 0, 0, 0)
        self._aiContainer.setVisible(False)
        self._mainSplitter.addWidget(self._aiContainer)

        self._mainSplitter.setStretchFactor(0, 3)
        self._mainSplitter.setStretchFactor(1, 2)

    def _setupSignals(self):
        self._abortBtn.clicked.connect(self._onAbort)
        self._closeBtn.clicked.connect(self.close)

        self._aiAutoResolveCheck.toggled.connect(self._onAiAutoResolveToggled)

        self._session.statusTextChanged.connect(self._status.setText)
        self._session.progressChanged.connect(self._onProgress)
        self._session.itemStarted.connect(self._onItemStarted)
        self._session.itemStatusChanged.connect(self._onItemStatusChanged)
        self._session.conflictsDetected.connect(self._onConflictsDetected)
        self._session.finished.connect(self._onFinished)

        self._resolvePanel.currentFileChanged.connect(self._onResolveCurrentFileChanged)

    def setMarkCallback(self, callback: Optional[Callable[[str, bool], None]]):
        self._session.setMarkCallback(callback)

    def setEnsureVisibleCallback(self, callback: Optional[Callable[[int], None]]):
        self._ensureVisibleCallback = callback

    def setReloadCallback(self, callback: Optional[Callable[[], None]]):
        self._reloadCallback = callback

    def setApplyLocalChangesCallback(self, callback: Optional[Callable[[str, str, str], bool]]):
        self._applyLocalChangesCallback = callback

    def _ensureAiChatEnabled(self, enabled: bool):
        if not enabled:
            self._session.setAiChatWidget(None)
            self._resolvePanel.setAiChatWidget(None)
            if self._aiChatWidget is not None:
                self._aiChatWidget.setVisible(False)
            if self._aiContainer is not None:
                self._aiContainer.setVisible(False)
                self._mainSplitter.setSizes([1, 0])
            return

        if self._aiChatWidget is None:
            if self._aiContainer is None or self._aiContainerLayout is None:
                return

            self._aiChatWidget = AiChatWidget(self._aiContainer, embedded=True)
            self._aiContextProvider = CherryPickProgressAiChatContextProvider(self)
            self._aiChatWidget.setContextProvider(self._aiContextProvider)

            self._aiContainerLayout.addWidget(self._aiChatWidget)

        self._aiChatWidget.setVisible(True)
        if self._aiContainer is not None:
            self._aiContainer.setVisible(True)
            self._mainSplitter.setSizes([650, 450])
        self._session.setAiChatWidget(self._aiChatWidget)
        self._resolvePanel.setAiChatWidget(self._aiChatWidget)

    def _onAiAutoResolveToggled(self, checked: bool):
        # Session-scoped toggle: affects subsequent resolve attempts.
        self._ensureAiChatEnabled(bool(checked))

    def startSession(
        self,
        *,
        items: List[CherryPickItem],
        targetBaseRepoDir: str,
        sourceBaseRepoDir: str,
        recordOrigin: bool,
        allowPatchPick: bool = True,
        aiEnabled: bool = False,
    ):
        # Initialize checkbox + AI pane from caller-provided default.
        self._aiAutoResolveCheck.blockSignals(True)
        self._aiAutoResolveCheck.setChecked(bool(aiEnabled))
        self._aiAutoResolveCheck.blockSignals(False)

        self._ensureAiChatEnabled(bool(aiEnabled))

        if self._aiContextProvider is not None:
            self._aiContextProvider.setBaseDirs(
                targetBaseRepoDir=targetBaseRepoDir,
                sourceBaseRepoDir=sourceBaseRepoDir,
            )

        self._items = list(items or [])
        self._list.clear()

        for item in self._items:
            label = item.sha1[:7]
            lw = QListWidgetItem(label)
            lw.setData(Qt.UserRole, CherryPickItemStatus.PENDING)
            self._list.addItem(lw)

        self._progress.setRange(0, max(1, len(self._items)))
        self._progress.setValue(0)

        self._session.start(
            items=self._items,
            targetBaseRepoDir=targetBaseRepoDir,
            sourceBaseRepoDir=sourceBaseRepoDir,
            recordOrigin=recordOrigin,
            allowPatchPick=allowPatchPick,
            applyLocalChangesFn=self._applyLocalChangesCallback,
        )

        return self.exec()

    def _onAbort(self):
        self._abortBtn.setEnabled(False)
        self._session.requestAbortSafely()

    def _onProgress(self, cur: int, total: int):
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(cur)

    def _onItemStarted(self, itemIndex: int, itemObj: object):
        if 0 <= itemIndex < self._list.count():
            self._list.setCurrentRow(itemIndex)

        item = itemObj if isinstance(itemObj, CherryPickItem) else None
        if item is not None and item.sourceIndex is not None and self._ensureVisibleCallback:
            self._ensureVisibleCallback(int(item.sourceIndex))

        if self._aiContextProvider is not None and item is not None:
            self._aiContextProvider.setCurrentItem(
                sha1=item.sha1,
                repoDir=item.repoDir or "",
            )

    def _onItemStatusChanged(self, itemIndex: int, status: str, message: str):
        if not (0 <= itemIndex < self._list.count()):
            return
        item = self._list.item(itemIndex)
        item.setData(Qt.UserRole, status)

        baseText = self._items[itemIndex].sha1[:7]
        text = baseText
        if status == CherryPickItemStatus.PICKED:
            text = f"{baseText}  {self.tr('Picked')}"
            item.setForeground(
                ApplicationBase.instance().colorSchema().ResolvedFg)
        elif status == CherryPickItemStatus.NEEDS_RESOLUTION:
            text = f"{baseText}  {self.tr('Needs resolution')}"
            item.setForeground(
                ApplicationBase.instance().colorSchema().ConflictFg)
        elif status == CherryPickItemStatus.FAILED:
            text = f"{baseText}  {self.tr('Failed')}"
            item.setForeground(
                ApplicationBase.instance().colorSchema().ConflictFg)
        elif status == CherryPickItemStatus.ABORTED:
            text = f"{baseText}  {self.tr('Aborted')}"
        if message:
            text = f"{text}  -  {message}"
        item.setText(text)

    def _onConflictsDetected(self, operationObj: object, filesObj: object):
        op = operationObj if isinstance(
            operationObj, ResolveOperation) else None
        if op == ResolveOperation.CHERRY_PICK:
            self._status.setText(self.tr("Conflicts detected; resolving…"))
        else:
            self._status.setText(
                self.tr("Patch conflicts detected; resolving…"))

        if self._aiContextProvider is not None:
            opText = "cherry-pick" if op == ResolveOperation.CHERRY_PICK else "am"
            self._aiContextProvider.setConflicts(operation=opText, files=list(filesObj or []))

    def _onResolveCurrentFileChanged(self, pathObj: object):
        if self._aiContextProvider is None:
            return
        path = "" if pathObj is None else str(pathObj)
        self._aiContextProvider.setCurrentFile(path)

    def _onFinished(self, ok: bool, aborted: bool, needReload: bool, message: str):
        if needReload and self._reloadCallback is not None and not aborted:
            self._reloadCallback()

        if aborted:
            self._status.setText(self.tr("Aborted"))
        elif ok:
            self._status.setText(self.tr("Completed"))
        else:
            self._status.setText(message or self.tr("Failed"))

        self._abortBtn.setEnabled(False)
        self._closeBtn.setEnabled(True)
