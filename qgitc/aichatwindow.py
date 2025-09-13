import queue as queue
from datetime import datetime
from typing import Dict, List, Union

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollBar,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from qgitc.aichatbot import AiChatbot
from qgitc.aichathistory import AiChatHistory
from qgitc.aichathistorypanel import AiChatHistoryPanel
from qgitc.aichattitlegenerator import AiChatTitleGenerator
from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.common import commitRepoDir, fullRepoDir, logger, toSubmodulePath
from qgitc.gitutils import Git
from qgitc.llm import (
    AiChatMode,
    AiModelBase,
    AiModelFactory,
    AiParameters,
    AiResponse,
    AiRole,
)
from qgitc.llmprovider import AiModelProvider
from qgitc.statewindow import StateWindow
from qgitc.submoduleexecutor import SubmoduleExecutor


class ChatEdit(QWidget):
    MaxLines = 5
    enterPressed = Signal()
    textChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.edit = QPlainTextEdit(self)
        layout.addWidget(self.edit)

        font = self.font()
        font.setPointSize(9)
        self.setFont(font)

        self.setFocusProxy(self.edit)

        self.edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.edit.document().setDocumentMargin(4)

        self._lineHeight = self.fontMetrics().height()

        self.edit.textChanged.connect(self._onTextChanged)
        self.edit.textChanged.connect(self.textChanged)

        self._adjustHeight()

    def toPlainText(self):
        return self.edit.toPlainText()

    def clear(self):
        self.edit.clear()

    def setPlaceholderText(self, text):
        self.edit.setPlaceholderText(text)

    def textCursor(self):
        return self.edit.textCursor()

    def _onTextChanged(self):
        self._adjustHeight()

    def _adjustHeight(self):
        lineCount = self.edit.document().lineCount()
        margin = self.edit.document().documentMargin()
        # see `QLineEdit::sizeHint()`
        verticalMarin = 2 * 1
        if lineCount < ChatEdit.MaxLines:
            height = lineCount * self._lineHeight
            self.edit.setMinimumHeight(height)
            self.setFixedHeight(height + margin * 2 + verticalMarin)
        else:
            maxHeight = ChatEdit.MaxLines * self._lineHeight
            self.edit.setMinimumHeight(maxHeight + margin * 2)
            self.setFixedHeight(maxHeight + margin * 2 + verticalMarin)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() in [
                Qt.Key_Enter, Qt.Key_Return]:
            self.enterPressed.emit()

        return super().keyPressEvent(event)


class AiChatWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        mainLayout = QHBoxLayout(self)
        mainLayout.setContentsMargins(4, 4, 4, 4)
        mainLayout.setSpacing(4)

        self.splitter = QSplitter(Qt.Horizontal, self)
        mainLayout.addWidget(self.splitter)

        self._setupHistoryPanel()
        self._setupChatPanel()

        # Initialize chat histories
        self._chatHistories: Dict[str, AiChatHistory] = {}
        self._currentHistoryId = None
        self._titleGenerator: AiChatTitleGenerator = None
        self._isNewConversation = False

        QTimer.singleShot(100, self._loadChatHistories)

    def _setupHistoryPanel(self):
        self._historyPanel = AiChatHistoryPanel(self)
        self._historyPanel.requestNewChat.connect(self._onNewChatRequested)
        self._historyPanel.historySelectionChanged.connect(
            self._onHistorySelectionChanged)
        self.splitter.addWidget(self._historyPanel)

    def _setupChatPanel(self):
        chatWidget = QWidget(self)
        layout = QVBoxLayout(chatWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.stackWidget = QStackedWidget(self)
        layout.addWidget(self.stackWidget)

        self.sysInput = ChatEdit(self)
        self.sysInput.setPlaceholderText(
            self.tr("Enter the system prompt here"))

        self.usrInput = ChatEdit(self)
        self.usrInput.setPlaceholderText(
            self.tr("Enter the query prompt here"))
        self.usrInput.setFocus()

        self.usrInput.enterPressed.connect(
            self._onEnterKeyPressed)

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(0, 0, 0, 0)
        gridLayout.setSpacing(4)
        gridLayout.addWidget(QLabel(self.tr("System")), 0, 0)
        gridLayout.addWidget(self.sysInput, 0, 1)
        gridLayout.addWidget(QLabel(self.tr("User")), 1, 0)
        gridLayout.addWidget(self.usrInput, 1, 1)

        layout.addLayout(gridLayout)

        hlayout = QHBoxLayout()
        layout.addLayout(hlayout)

        hlayout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding))

        hlayout.addWidget(QLabel(self.tr("Max Tokens")))
        self.sbMaxTokens = QSpinBox(self)
        self.sbMaxTokens.setRange(1, 0x7FFFFFFF)
        self.sbMaxTokens.setSingleStep(500)
        self.sbMaxTokens.setValue(4096)
        self.sbMaxTokens.setToolTip(self.tr("Max tokens to generate"))
        self.sbMaxTokens.setFixedWidth(80)
        hlayout.addWidget(self.sbMaxTokens)

        hlayout.addWidget(QLabel(self.tr("Temperature"), self))
        self.sbTemperature = QDoubleSpinBox(self)
        self.sbTemperature.setRange(0.0, 1.0)
        self.sbTemperature.setSingleStep(0.1)
        self.sbTemperature.setValue(0.1)
        hlayout.addWidget(self.sbTemperature)

        self.cbBots = QComboBox(self)
        self.cbBots.setEditable(False)
        self.cbBots.setSizeAdjustPolicy(QComboBox.AdjustToContents)

        aiModels: List[AiModelBase] = [
            model(parent=self) for model in AiModelProvider.models()]
        defaultModelKey = ApplicationBase.instance().settings().defaultLlmModel()

        for i, model in enumerate(aiModels):
            self.cbBots.addItem(model.name, model)
            tb = AiChatbot(self)
            self.stackWidget.addWidget(tb)
            tb.verticalScrollBar().valueChanged.connect(
                self._onTextBrowserScrollbarChanged)
            model.responseAvailable.connect(self._onMessageReady)
            model.finished.connect(self._onResponseFinish)
            model.serviceUnavailable.connect(self._onServiceUnavailable)
            if AiModelFactory.modelKey(model) == defaultModelKey:
                self.cbBots.setCurrentIndex(i)

            model.modelsReady.connect(
                self._onModelsReady)

        self.stackWidget.setCurrentIndex(self.cbBots.currentIndex())

        hlayout.addWidget(self.cbBots)

        self.cbModelNames = QComboBox(self)
        self.cbModelNames.setEditable(False)
        self.cbModelNames.setMinimumWidth(130)
        self.cbModelNames.setSizeAdjustPolicy(QComboBox.AdjustToContents)

        hlayout.addWidget(self.cbModelNames)

        self.cbChatMode = QComboBox(self)
        self.cbChatMode.setEditable(False)
        hlayout.addWidget(self.cbChatMode)

        self.cbLang = QComboBox(self)
        self.cbLang.setEditable(False)
        self.cbLang.addItem("None")
        self.cbLang.addItem("python")
        self.cbLang.addItem("cpp")
        self.cbLang.addItem("csharp")
        hlayout.addWidget(self.cbLang)
        self.cbLang.setEnabled(False)
        self.cbLang.setCurrentIndex(1)

        self.btnSend = QPushButton(self.tr("Send"), self)
        hlayout.addWidget(self.btnSend)
        self.btnClear = QPushButton(self.tr("Clear"), self)
        hlayout.addWidget(self.btnClear)

        hlayout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding))

        self.statusBar = QStatusBar(self)
        layout.addWidget(self.statusBar)

        self.lbTokens = QLabel(self)
        self.statusBar.addPermanentWidget(self.lbTokens)

        self.btnSend.clicked.connect(self._onButtonSend)
        self.btnClear.clicked.connect(self._onButtonClear)

        self.cbBots.currentIndexChanged.connect(
            self._onModelChanged)
        self.cbChatMode.currentIndexChanged.connect(
            self._onChatModeChanged)

        self._onModelChanged(self.cbBots.currentIndex())

        QWidget.setTabOrder(self.usrInput, self.btnSend)
        QWidget.setTabOrder(self.btnSend, self.btnClear)
        QWidget.setTabOrder(self.btnClear, self.usrInput)

        self._disableAutoScroll = False
        self._adjustingSccrollbar = False

        self.splitter.addWidget(chatWidget)
        self.splitter.setSizes([200, 600])

    def _chatModeStr(self, mode: AiChatMode):
        strings = {
            AiChatMode.Chat: self.tr("Chat"),
            AiChatMode.Completion: self.tr("Completion"),
            AiChatMode.Infilling: self.tr("Infilling"),
            AiChatMode.CodeReview: self.tr("Code Review"),
            AiChatMode.CodeFix: self.tr("Code Fix"),
            AiChatMode.CodeExplanation: self.tr("Code Explanation"),
        }
        return strings[mode]

    def queryClose(self):
        # Save current conversation before closing
        self._saveCurrentConversation()

        if self._titleGenerator:
            self._titleGenerator.cancel()

        for i in range(self.cbBots.count()):
            model: AiModelBase = self.cbBots.itemData(i)
            if model.isRunning():
                model.requestInterruption()
            model.cleanup()

    def sizeHint(self):
        return QSize(800, 600)

    def _onButtonSend(self, clicked):
        prompt = self.usrInput.toPlainText().strip()
        if not prompt:
            return

        # If this is a new conversation and first message, generate title
        if self._isNewConversation and self._currentHistoryId:
            self._generateChatTitle(prompt)
            self._isNewConversation = False

        chatMode: AiChatMode = self.cbChatMode.currentData()
        self._doRequest(
            prompt,
            chatMode,
            self.cbLang.currentText(),
            self.sysInput.toPlainText())

        app = ApplicationBase.instance()
        model = self.currentChatModel()
        app.trackFeatureUsage("aichat_send", {
            "chat_mode": chatMode.name,
            "model": model.modelId or model.name,
        })

        # Clear input after sending
        self.usrInput.clear()

    def _doRequest(self, prompt: str, chatMode: AiChatMode, language="", sysPrompt: str = None):
        params = AiParameters()
        params.prompt = prompt
        params.sys_prompt = sysPrompt
        params.stream = True
        params.temperature = self.sbTemperature.value()
        params.max_tokens = self.sbMaxTokens.value()
        params.chat_mode = chatMode
        params.language = language
        params.model = self.cbModelNames.currentData()

        if params.chat_mode == AiChatMode.Infilling:
            params.fill_point = self.usrInput.textCursor().position()

        self._disableAutoScroll = False

        model = self.currentChatModel()
        prompt = params.prompt
        if chatMode == AiChatMode.CodeReview:
            prompt = f"```diff\n{prompt}\n```"
        self._doMessageReady(model, AiResponse(AiRole.User, prompt))

        model.queryAsync(params)

        self.btnSend.setEnabled(False)
        self.btnClear.setEnabled(False)

        self.statusBar.showMessage(self.tr("Work in progress..."))
        self.usrInput.setFocus()

    def _onButtonClear(self, clicked):
        # Save current conversation before clearing
        self._saveCurrentConversation()

        # Clear current chat
        self._clearCurrentChat()

        # Create a new conversation
        self._createNewConversation()

    def _onMessageReady(self, response: AiResponse):
        if response.message is None:
            return

        model: AiModelBase = self.sender()
        self._doMessageReady(model, response)

    def _doMessageReady(self, model: AiModelBase, response: AiResponse):
        index = self.cbBots.findData(model)

        assert (index != -1)
        messages: AiChatbot = self.stackWidget.widget(index)
        messages.appendResponse(response)

        if not self._disableAutoScroll:
            sb = messages.verticalScrollBar()
            self._adjustingSccrollbar = True
            sb.setValue(sb.maximum())
            self._adjustingSccrollbar = False

        if response.total_tokens is not None:
            self.statusBar.showMessage(
                f"Totoal tokens {response.total_tokens}")

    def _onResponseFinish(self):
        clear = True
        for i in range(self.cbBots.count()):
            model: AiModelBase = self.cbBots.itemData(i)
            if model.isRunning():
                clear = False
                break

        model = self.currentChatModel()
        enabled = model is None or not model.isRunning()
        self.btnSend.setEnabled(enabled)
        self.btnClear.setEnabled(enabled)
        if clear:
            self.statusBar.clearMessage()
        self.usrInput.setFocus()

    def _onServiceUnavailable(self):
        model: AiModelBase = self.sender()
        index = self.cbBots.findData(model)
        assert (index != -1)
        messages: AiChatbot = self.stackWidget.widget(index)
        messages.appendServiceUnavailable()

    def _onModelChanged(self, index: int):
        self.stackWidget.setCurrentIndex(index)

        model = self.currentChatModel()
        enabled = model is None or not model.isRunning()

        self.btnSend.setEnabled(enabled)
        self.btnClear.setEnabled(enabled)
        self.usrInput.setFocus()

        self._initChatMode(model)
        self._onChatModeChanged(self.cbChatMode.currentIndex())

        self._updateModelNames(model)

    def _initChatMode(self, model: AiModelBase):
        modes = model.supportedChatModes()
        self.cbChatMode.clear()
        for mode in modes:
            self.cbChatMode.addItem(self._chatModeStr(mode), mode)
        self.cbChatMode.setCurrentIndex(0)
        self.cbChatMode.setEnabled(len(modes) > 0)

    def _onChatModeChanged(self, index):
        self.cbLang.setEnabled(
            self.cbChatMode.currentData() == AiChatMode.Infilling)

    def _onEnterKeyPressed(self):
        self._onButtonSend(False)

    def _onTextBrowserScrollbarChanged(self, value):
        if self._adjustingSccrollbar:
            return

        model = self.currentChatModel()
        if model is not None and model.isRunning():
            sb: QScrollBar = self.messages.verticalScrollBar()
            self._disableAutoScroll = sb.value() != sb.maximum()

    @property
    def messages(self) -> AiChatbot:
        return self.stackWidget.currentWidget()

    def currentChatModel(self) -> AiModelBase:
        return self.cbBots.currentData()

    def isLocalLLM(self):
        return self.currentChatModel().isLocal()

    def codeReview(self, commit, args):
        repoDir = commitRepoDir(commit)
        data: bytes = Git.commitRawDiff(
            commit.sha1, gitArgs=args, repoDir=repoDir)
        if not data:
            return

        for subCommit in commit.subCommits:
            repoDir = commitRepoDir(subCommit)
            subData = Git.commitRawDiff(
                subCommit.sha1, gitArgs=args, repoDir=repoDir)
            if subData:
                data += b"\n" + subData

        diff = data.decode("utf-8", errors="replace")
        self._doRequest(diff, AiChatMode.CodeReview)

    def codeReviewForDiff(self, diff: str):
        self._doRequest(diff, AiChatMode.CodeReview)

    def _updateModelNames(self, model: AiModelBase):
        self.cbModelNames.clear()
        modelKey = AiModelFactory.modelKey(model)
        defaultId = ApplicationBase.instance().settings().defaultLlmModelId(modelKey)
        if not defaultId:
            defaultId = model.modelId
        for id, name in model.models():
            self.cbModelNames.addItem(name, id)
            if id == defaultId:
                self.cbModelNames.setCurrentText(name)

    def _onModelsReady(self):
        model: AiModelBase = self.sender()
        if model == self.currentChatModel():
            self._updateModelNames(model)

    def _loadChatHistories(self):
        """Load chat histories from settings"""
        try:
            settings = ApplicationBase.instance().settings()
            histories = settings.chatHistories()

            for historyData in histories:
                if isinstance(historyData, dict):
                    history = AiChatHistory.fromDict(historyData)
                    self._chatHistories[history.historyId] = history

            self._refreshHistoryList()

            # Load the last used conversation or create a new one
            currentId = settings.currentChatHistoryId()
            if currentId and currentId in self._chatHistories:
                self._loadChatHistory(currentId)
            else:
                self._createNewConversation()

        except Exception as e:
            logger.warning(f"Failed to load chat histories: {e}")
            self._createNewConversation()

    def _refreshHistoryList(self):
        """Refresh the history list widget"""
        self._historyPanel.refreshHistories(self._chatHistories.values())

    def _onNewChatRequested(self):
        """Create a new chat conversation"""
        self._createNewConversation()

    def _createNewConversation(self):
        """Create and switch to a new conversation"""
        history = AiChatHistory()
        history.modelKey = AiModelFactory.modelKey(self.currentChatModel())
        history.modelId = self.cbModelNames.currentData() or ""

        self._chatHistories[history.historyId] = history
        self._currentHistoryId = history.historyId
        self._isNewConversation = True

        # Clear current chat
        self._clearCurrentChat()

        # Update UI
        self._refreshHistoryList()
        self._historyPanel.setCurrentHistory(history.historyId)

        # Save to settings
        settings = ApplicationBase.instance().settings()
        settings.setCurrentChatHistoryId(history.historyId)

    def _onHistorySelectionChanged(self, historyId: str):
        """Handle history selection change"""
        if historyId != self._currentHistoryId:
            self._saveCurrentConversation()
            self._loadChatHistory(historyId)

    def _loadChatHistory(self, historyId: str):
        """Load a specific chat history"""
        if historyId not in self._chatHistories:
            return

        history = self._chatHistories[historyId]
        self._currentHistoryId = historyId
        self._isNewConversation = False

        # Switch to the correct model if different
        self._switchToModel(history.modelKey, history.modelId)

        # Clear and load messages
        self._clearCurrentChat()
        self._loadMessagesFromHistory(history.messages)

        # Update settings
        settings = ApplicationBase.instance().settings()
        settings.setCurrentChatHistoryId(historyId)

    def _switchToModel(self, modelKey: str, modelId: str):
        """Switch to the specified model"""
        # Find the correct model
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

    def _loadMessagesFromHistory(self, messages: List[Dict]):
        """Load messages from history into the chat"""
        if not messages:
            return

        model = self.currentChatModel()
        chatbot = self.messages

        # Clear model history and add messages
        model.clear()

        for msg in messages:
            role = AiRole(msg.get('role', 0))
            content = msg.get('content', '')

            if content:
                # Add to model history
                if role == AiRole.User:
                    model.add_history({"role": "user", "content": content})
                elif role == AiRole.Assistant:
                    model.add_history(
                        {"role": "assistant", "content": content})

                # Display in chat
                response = AiResponse(role, content)
                chatbot.appendResponse(response)

    def _clearCurrentChat(self):
        """Clear the current chat display and model history"""
        model = self.currentChatModel()
        if model:
            model.clear()
        self.messages.clear()

    def _saveCurrentConversation(self):
        """Save the current conversation to history"""
        if not self._currentHistoryId or self._currentHistoryId not in self._chatHistories:
            return

        history = self._chatHistories[self._currentHistoryId]
        model = self.currentChatModel()

        if model and hasattr(model, '_history'):
            # Convert model history to our format
            messages = []
            for msg in model._history:
                role_str = msg.get('role', 'user')
                if role_str == 'user':
                    role = AiRole.User
                elif role_str == 'assistant':
                    role = AiRole.Assistant
                elif role_str == 'system':
                    role = AiRole.System
                else:
                    role = AiRole.User

                messages.append({
                    'role': role.value,
                    'content': msg.get('content', '')
                })

            history.messages = messages
            history.modelKey = AiModelFactory.modelKey(model)
            history.modelId = self.cbModelNames.currentData() or ""
            history.timestamp = datetime.now().isoformat()

            # Save to settings
            settings = ApplicationBase.instance().settings()
            settings.saveChatHistory(history.historyId, history.toDict())

    def _generateChatTitle(self, firstMessage: str):
        """Generate a title for the conversation"""
        if not firstMessage.strip() or not self._currentHistoryId:
            return

        if not self._titleGenerator:
            self._titleGenerator = AiChatTitleGenerator(self)
            self._titleGenerator.titleReady.connect(self._onChatTitleReady)
        self._titleGenerator.startGenerate(
            self._currentHistoryId, firstMessage)

    def _onChatTitleReady(self, historyId: str, title: str):
        """Handle generated title"""
        if historyId in self._chatHistories:
            history = self._chatHistories[historyId]
            history.title = title

            self._historyPanel.updateTitle(historyId, title)

            # Save to settings
            settings = ApplicationBase.instance().settings()
            settings.saveChatHistory(historyId, history.toDict())


class DiffAvailableEvent(QEvent):
    Type = QEvent.User + 1

    def __init__(self, diff: str):
        super().__init__(QEvent.Type(DiffAvailableEvent.Type))
        self.diff = diff


class AiChatWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(self.tr("AI Assistant"))
        centralWidget = AiChatWidget(self)
        self.setCentralWidget(centralWidget)

        self._executor: SubmoduleExecutor = None
        self._diffs: List[str] = []

    def codeReview(self, commit, args=None):
        self.centralWidget().codeReview(commit, args)

    def codeReviewForStagedFiles(self, submodules: Union[list, dict]):
        self._ensureExecutor()
        self._diffs.clear()
        self._executor.submit(submodules, self._fetchDiff)

    def _ensureExecutor(self):
        if self._executor is None:
            self._executor = SubmoduleExecutor(self)
            self._executor.finished.connect(self._onExecuteFinished)

    def _onExecuteFinished(self):
        if self._diffs:
            diff = "\n".join(self._diffs)
            self.centralWidget().codeReviewForDiff(diff)

    def _fetchDiff(self, submodule: str, files, cancelEvent: CancelEvent):
        repoDir = fullRepoDir(submodule)
        repoFiles = [toSubmodulePath(submodule, file) for file in files]
        data: bytes = Git.commitRawDiff(
            Git.LCC_SHA1, repoFiles, repoDir=repoDir)
        if not data:
            logger.warning("AiChat: no diff for %s", repoDir)
            return

        if cancelEvent.isSet():
            return

        diff = data.decode("utf-8", errors="replace")
        ApplicationBase.instance().postEvent(self, DiffAvailableEvent(diff))

    def event(self, event: QEvent):
        if event.type() == DiffAvailableEvent.Type:
            if event.diff:
                self._diffs.append(event.diff)
            return True

        return super().event(event)

    def closeEvent(self, event):
        if self._executor:
            self._executor.cancel()
            self._executor = None
        self.centralWidget().queryClose()
        return super().closeEvent(event)
