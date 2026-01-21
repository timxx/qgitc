# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QVBoxLayout

from qgitc.aichatedit import AiChatEdit
from qgitc.coloredicontoolbutton import ColoredIconToolButton
from qgitc.common import dataDirPath
from qgitc.inlinecombobox import InlineComboBox
from qgitc.llm import AiChatMode, AiModelBase, AiModelFactory


class AiChatContextPanel(QFrame):
    enterPressed = Signal()
    modeChanged = Signal(AiChatMode)
    textChanged = Signal()
    modelChanged = Signal(int)

    def __init__(self, showSettings=True, parent=None):
        super().__init__(parent)

        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Plain)
        self.setLineWidth(1)

        self._updateFrameStyle(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

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
