# -*- coding: utf-8 -*-

from typing import Dict, List, Optional, Set

from PySide6.QtCore import QEvent, QSize, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QMenu, QVBoxLayout

from qgitc.aichatcontextprovider import AiChatContextProvider, AiContextDescriptor
from qgitc.aichatedit import AiChatEdit
from qgitc.aicontexttoolbutton import AiContextToolButton
from qgitc.coloredicontoolbutton import ColoredIconToolButton
from qgitc.common import dataDirPath
from qgitc.flowlayout import FlowLayout
from qgitc.inlinecombobox import InlineComboBox
from qgitc.llm import AiChatMode, AiModelBase, AiModelFactory


class AiChatContextPanel(QFrame):
    enterPressed = Signal()
    modeChanged = Signal(AiChatMode)
    textChanged = Signal()
    modelChanged = Signal(int)
    contextSelectionChanged = Signal(list)
    contextActivated = Signal(str)

    def __init__(self, showSettings=True, parent=None):
        super().__init__(parent)

        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Plain)
        self.setLineWidth(1)

        self._updateFrameStyle(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self._availableContexts: Dict[str, AiContextDescriptor] = {}
        self._defaultContextIds: List[str] = []
        self._selectedContextIds: List[str] = []
        self._contextProvider: Optional[AiChatContextProvider] = None
        self._contextChipsLayout: Optional[FlowLayout] = None

        # Text input (auto-expanding) at top
        self.edit = AiChatEdit(self)
        self.edit.setPlaceholderText(self.tr("Ask anything..."))
        self.edit.enterPressed.connect(self.enterPressed)
        self.edit.textChanged.connect(self.textChanged)
        # Remove border from inner edit
        self.edit.edit.setStyleSheet(
            "QPlainTextEdit { border: none; background: transparent; }")
        # Install event filter to track focus
        self.edit.edit.installEventFilter(self)
        layout.addWidget(self.edit)

        # Bottom control line
        controlLayout = QHBoxLayout()
        controlLayout.setContentsMargins(4, 4, 4, 4)
        controlLayout.setSpacing(4)

        self.cbBots = InlineComboBox(self)
        self.cbBots.currentIndexChanged.connect(self._onModelChanged)
        self.cbBots.popupClosed.connect(self._restoreFocus)
        controlLayout.addWidget(self.cbBots)

        self.cbModelNames = InlineComboBox(self)
        self.cbModelNames.popupClosed.connect(self._restoreFocus)
        controlLayout.addWidget(self.cbModelNames)

        # Mode selector
        self.cbMode = InlineComboBox(self)
        self._setupChatMode()
        self.cbMode.currentIndexChanged.connect(self._onModeChanged)
        self.cbMode.popupClosed.connect(self._restoreFocus)
        controlLayout.addWidget(self.cbMode)

        if showSettings:
            settingsIcon = QIcon(dataDirPath() + "/icons/settings.svg")
            self.btnSettings = ColoredIconToolButton(
                settingsIcon, QSize(16, 16), self)
            self.btnSettings.setToolTip(self.tr("Configure Chat"))
            controlLayout.addWidget(self.btnSettings)

        controlLayout.addStretch()

        # Send button
        sendIcon = QIcon(dataDirPath() + "/icons/send.svg")
        self.btnSend = ColoredIconToolButton(sendIcon, QSize(20, 20), self)
        self.btnSend.setToolTip(self.tr("Send"))
        self.btnSend.setEnabled(False)
        controlLayout.addWidget(self.btnSend)

        # Stop button (hidden by default)
        stopIcon = QIcon(dataDirPath() + "/icons/stop.svg")
        self.btnStop = ColoredIconToolButton(stopIcon, QSize(20, 20), self)
        self.btnStop.setVisible(False)
        controlLayout.addWidget(self.btnStop)

        layout.addLayout(controlLayout)
        self.setFocusProxy(self.edit)

    def _setupContextBar(self, parentLayout: QVBoxLayout):
        self._contextChipsLayout = FlowLayout(None, margin=0, spacing=2)
        attachIcon = QIcon(dataDirPath() + "/icons/attach-add.svg")
        btnAttachContext = ColoredIconToolButton(
            attachIcon, QSize(16, 16), self)
        btnAttachContext.setFixedSize(QSize(20, 20))
        btnAttachContext.setToolTip(self.tr("Add context"))
        btnAttachContext.setPopupMode(ColoredIconToolButton.InstantPopup)
        self._attachMenu = QMenu(btnAttachContext)
        btnAttachContext.setMenu(self._attachMenu)
        self._attachMenu.aboutToShow.connect(self.refreshContexts)
        self._attachMenu.aboutToHide.connect(self._restoreFocus)

        self._contextChipsLayout.addWidget(btnAttachContext)
        parentLayout.insertLayout(0, self._contextChipsLayout)

    def setContextProvider(self, provider: Optional[AiChatContextProvider]):
        if self._contextProvider == provider:
            return

        if self._contextChipsLayout is None:
            self._setupContextBar(self.layout())

        if self._contextProvider is not None:
            self._contextProvider.contextsChanged.disconnect(
                self.refreshContexts)

        self._contextProvider = provider
        if self._contextProvider is not None:
            self._contextProvider.contextsChanged.connect(self.refreshContexts)

        self.refreshContexts()

    def contextProvider(self) -> Optional[AiChatContextProvider]:
        return self._contextProvider

    def refreshContexts(self):
        """Re-query available/default contexts from provider.

        Context availability can change by commit/scene, so this is called whenever
        the attach menu opens and whenever provider emits contextsChanged.
        """
        if self._contextProvider is None:
            self._availableContexts = {}
            self._defaultContextIds = []
        else:
            contexts = self._contextProvider.availableContexts() or []
            self._availableContexts = {c.id: c for c in contexts}
            self._defaultContextIds = list(
                self._contextProvider.defaultContextIds() or [])

        newSelected = []
        for id in self._selectedContextIds:
            if id in self._availableContexts:
                newSelected.append(id)
        self._selectedContextIds = newSelected
        self._rebuildAttachMenu()
        self._refreshContextChips()

    def selectedContextIds(self) -> List[str]:
        return self._selectedContextIds

    def toggleContext(self, contextId: str):
        if contextId not in self._availableContexts:
            return
        if contextId in self._selectedContextIds:
            self._selectedContextIds.remove(contextId)
        else:
            self._selectedContextIds.append(contextId)

        self._rebuildAttachMenu()
        self._refreshContextChips()
        self.contextSelectionChanged.emit(self.selectedContextIds())
        self._restoreFocus()

    def _rebuildAttachMenu(self):
        self._attachMenu.clear()

        for ctx in self._availableContexts.values():
            action = QAction(ctx.icon or QIcon(), ctx.label, self._attachMenu)
            if ctx.tooltip:
                action.setToolTip(ctx.tooltip)
            action.setCheckable(True)
            action.setChecked(ctx.id in self._selectedContextIds)
            action.triggered.connect(
                lambda checked=False, cid=ctx.id: self.toggleContext(cid))
            self._attachMenu.addAction(action)

    def _clearContextChips(self):
        # The first widget is always the attach button, keep it.
        item = self._contextChipsLayout.takeAt(1)
        while item is not None:
            w = item.widget()
            if w is not None:
                w.deleteLater()
            item = self._contextChipsLayout.takeAt(1)

    def _displayedContextIds(self) -> List[str]:
        defaults = [cid for cid in self._defaultContextIds if cid in self._availableContexts]

        # Default contexts are "pinned": always display them so they are not removable.
        selected = [cid for cid in self._selectedContextIds
                    if cid in self._availableContexts and cid not in defaults]
        if defaults:
            return defaults + selected
        return selected

    def _refreshContextChips(self):
        self._clearContextChips()

        displayed = self._displayedContextIds()
        hasSelection = bool(self._selectedContextIds)
        for cid in displayed:
            ctx = self._availableContexts.get(cid)
            if not ctx:
                continue

            isSelected = cid in self._selectedContextIds
            # If nothing is selected, defaults are displayed in "not selected" state.
            if not hasSelection:
                isSelected = False

            btn = self._createContextChip(ctx, isSelected)
            self._contextChipsLayout.addWidget(btn)

        # self._contextChipsLayout.updateGeometry()

    def _createContextChip(self, ctx: AiContextDescriptor, selected: bool) -> AiContextToolButton:
        addIcon = QIcon(dataDirPath() + "/icons/add.svg")
        closeIcon = QIcon(dataDirPath() + "/icons/close.svg")

        btn = AiContextToolButton(
            ctx.id,
            ctx.label,
            addIcon,
            closeIcon,
            QSize(16, 16),
            self,
        )
        btn.setFixedHeight(20)
        btn.setSelected(selected)
        btn.setToolTip(ctx.tooltip or ctx.label)

        btn.toggleRequested.connect(self.toggleContext)
        btn.activated.connect(self.contextActivated.emit)
        return btn

    def _updateFrameStyle(self, focused):
        """Update frame border color based on focus state"""
        if focused:
            self.setStyleSheet("""
                AiChatContextPanel {
                    border: 1px solid palette(highlight);
                    border-radius: 4px;
                    background-color: palette(base);
                }
            """)
        else:
            # Use darker border for Fusion style which needs more contrast
            # Use mid for other styles to avoid too dark borders
            isFusion = QApplication.style().name().lower() == "fusion"
            borderColor = "palette(dark)" if isFusion else "palette(mid)"
            self.setStyleSheet(f"""
                AiChatContextPanel {{
                    border: 1px solid {borderColor};
                    border-radius: 4px;
                    background-color: palette(base);
                }}
            """)

    def eventFilter(self, watched, event: QEvent):
        """Track focus changes on the edit widget to highlight frame border"""
        if watched == self.edit.edit:
            if event.type() == QEvent.FocusIn:
                # Highlight border when focused
                self._updateFrameStyle(True)
            elif event.type() == QEvent.FocusOut:
                # Reset to inactive color when focus lost
                self._updateFrameStyle(False)
        return super().eventFilter(watched, event)

    def _onModeChanged(self, index):
        mode = self.cbMode.currentData()
        self.modeChanged.emit(mode)

        # Agent mode requires tool-call capable models.
        # Refresh model-id list on mode changes so the selection stays valid.
        model = self.cbBots.currentData()
        if model:
            self.setupModelNames(model)

    def _onModelChanged(self, index):
        self.modelChanged.emit(index)

    def _restoreFocus(self):
        """Restore focus to the edit box after combobox popup closes"""
        self.edit.setFocus()

    def toPlainText(self):
        return self.edit.toPlainText()

    def clear(self):
        self.edit.clear()

    def textCursor(self):
        return self.edit.textCursor()

    def currentMode(self) -> AiChatMode:
        return self.cbMode.currentData()

    def currentModelIndex(self) -> int:
        return self.cbBots.currentIndex()

    def currentModelId(self) -> str:
        return self.cbModelNames.currentData()

    def setMode(self, mode: AiChatMode):
        for i in range(self.cbMode.count()):
            if self.cbMode.itemData(i) == mode:
                self.cbMode.setCurrentIndex(i)
                break

    def userPrompt(self) -> str:
        return self.edit.toPlainText()

    def switchToModel(self, modelKey: str, modelId: str):
        """Switch to the specified model"""

        for i in range(self.cbBots.count()):
            model = self.cbBots.itemData(i)
            if AiModelFactory.modelKey(model) == modelKey:
                if self.cbBots.currentIndex() != i:
                    self.cbBots.setCurrentIndex(i)

                # Set the specific model ID if available
                if modelId:
                    for j in range(self.cbModelNames.count()):
                        if self.cbModelNames.itemData(j) == modelId:
                            self.cbModelNames.setCurrentIndex(j)
                            break
                break

    def _setupChatMode(self):
        modes = {
            AiChatMode.Agent: "🔧 " + self.tr("Agent"),
            AiChatMode.Chat: "💬 " + self.tr("Chat"),
            AiChatMode.CodeReview: "📝 " + self.tr("Code Review"),
        }
        self.cbMode.clear()
        for mode, label in modes.items():
            self.cbMode.addItem(label, mode)
        self.cbMode.setCurrentIndex(0)
        self.cbMode.setEnabled(len(modes) > 0)

    def setupModelNames(self, model: AiModelBase):
        prevSelectedId = self.cbModelNames.currentData()
        self.cbModelNames.clear()

        defaultId = model.modelId
        mode: AiChatMode = self.currentMode()

        newIndex = -1
        defaultidIndex = -1
        for id, name in model.models():
            if mode == AiChatMode.Agent and not model.supportsToolCalls(id):
                continue

            self.cbModelNames.addItem(name, id)
            if newIndex == -1 and id == prevSelectedId:
                newIndex = self.cbModelNames.count() - 1
            if defaultidIndex == -1 and id == defaultId:
                defaultidIndex = self.cbModelNames.count() - 1

        index = 0
        # Prefer restoring the previous selection if it still exists.
        if newIndex != -1:
            index = newIndex
        elif defaultidIndex != -1:
            index = defaultidIndex

        if self.cbModelNames.count() > 0:
            self.cbModelNames.setCurrentIndex(index)
