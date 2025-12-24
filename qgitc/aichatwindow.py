import queue as queue
from typing import Dict, List, Union

from PySide6.QtCore import QEvent, QEventLoop, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollBar,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QSplitter,
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
from qgitc.colorediconbutton import ColoredIconButton
from qgitc.common import (
    commitRepoDir,
    dataDirPath,
    fullRepoDir,
    logger,
    toSubmodulePath,
)
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
from qgitc.models.prompts import CODE_REVIEW_PROMPT
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
        self.edit.installEventFilter(self)

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

    def eventFilter(self, watched, event):
        if watched == self.edit and event.type() == QEvent.KeyPress:
            if event.key() in [Qt.Key_Enter, Qt.Key_Return]:
                if event.modifiers() == Qt.NoModifier:
                    self.enterPressed.emit()
                    return True
                elif event.modifiers() == Qt.ShiftModifier:
                    return False
        return super().eventFilter(watched, event)


class AiChatWidget(QWidget):

    initialized = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        mainLayout = QHBoxLayout(self)
        mainLayout.setContentsMargins(4, 4, 4, 4)
        mainLayout.setSpacing(4)

        self.splitter = QSplitter(Qt.Horizontal, self)
        mainLayout.addWidget(self.splitter)

        self._setupHistoryPanel()
        self._setupChatPanel()

        self._titleGenerator: AiChatTitleGenerator = None

        self._isInitialized = False
        QTimer.singleShot(100, self._onDelayInit)
        self.usrInput.setFocus()

    def _setupHistoryPanel(self):
        self._historyPanel = AiChatHistoryPanel(self)
        self._historyPanel.requestNewChat.connect(self._onNewChatRequested)
        self._historyPanel.historySelectionChanged.connect(
            self._onHistorySelectionChanged)
        self._historyPanel.historyRemoved.connect(self._onHistoryRemoved)
        self.splitter.addWidget(self._historyPanel)

        # wait until history loaded
        self._historyPanel.setEnabled(False)

    def _setupChatPanel(self):
        chatWidget = QWidget(self)
        layout = QVBoxLayout(chatWidget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._chatBot = AiChatbot(self)
        self._chatBot.verticalScrollBar().valueChanged.connect(
            self._onTextBrowserScrollbarChanged)
        layout.addWidget(self._chatBot)

        self.sysInput = ChatEdit(self)
        self.sysInput.setPlaceholderText(
            self.tr("Enter the system prompt here"))

        self.usrInput = ChatEdit(self)
        self.usrInput.setPlaceholderText(
            self.tr("Enter the query prompt here"))
        self.usrInput.setFocus()

        self.usrInput.enterPressed.connect(
            self._onEnterKeyPressed)
        self.usrInput.textChanged.connect(
            self._onUsrInputTextChanged)

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

        sendIcon = QIcon(dataDirPath() + "/icons/send.svg")
        stopIcon = QIcon(dataDirPath() + "/icons/stop.svg")

        self.btnSend = ColoredIconButton(sendIcon, self.tr("Send"), self)
        self.btnStop = ColoredIconButton(stopIcon, self.tr("Stop"), self)
        self.btnStop.setVisible(False)
        hlayout.addWidget(self.btnSend)
        hlayout.addWidget(self.btnStop)
        self.btnSend.setEnabled(False)

        hlayout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding))

        self.statusBar = QStatusBar(self)
        layout.addWidget(self.statusBar)

        self.lbTokens = QLabel(self)
        self.statusBar.addPermanentWidget(self.lbTokens)

        self.btnSend.clicked.connect(self._onButtonSend)
        self.btnStop.clicked.connect(self._onButtonStop)

        self.cbBots.currentIndexChanged.connect(
            self._onModelChanged)
        self.cbChatMode.currentIndexChanged.connect(
            self._onChatModeChanged)

        QWidget.setTabOrder(self.usrInput, self.btnSend)
        QWidget.setTabOrder(self.btnSend, self.usrInput)

        self._disableAutoScroll = False
        self._adjustingSccrollbar = False

        self.splitter.addWidget(chatWidget)
        self.splitter.setSizes([200, 600])

    def _setupModels(self):
        aiModels: List[AiModelBase] = [
            model(parent=self) for model in AiModelProvider.models()]
        defaultModelKey = ApplicationBase.instance().settings().defaultLlmModel()
        currentModelIndex = -1

        for i, model in enumerate(aiModels):
            self.cbBots.addItem(model.name, model)
            model.responseAvailable.connect(self._onMessageReady)
            model.finished.connect(self._onResponseFinish)
            model.serviceUnavailable.connect(self._onServiceUnavailable)
            if AiModelFactory.modelKey(model) == defaultModelKey:
                currentModelIndex = i

            model.modelsReady.connect(self._onModelsReady)

        if currentModelIndex != -1:
            self.cbBots.setCurrentIndex(currentModelIndex)

        self._onModelChanged(self.cbBots.currentIndex())

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

        model = self.currentChatModel()
        chatMode: AiChatMode = self.cbChatMode.currentData()
        self._doRequest(
            prompt,
            chatMode,
            self.cbLang.currentText(),
            self.sysInput.toPlainText())

        app = ApplicationBase.instance()
        app.trackFeatureUsage("aichat_send", {
            "chat_mode": chatMode.name,
            "model": model.modelId or model.name,
        })

        # Clear input after sending
        self.usrInput.clear()

    def _onButtonStop(self):
        model = self.currentChatModel()
        if not model.isRunning():
            return

        model.requestInterruption()
        self.statusBar.clearMessage()

        chatHistory = self._historyPanel.updateCurrentHistory(model)
        if chatHistory:
            settings = ApplicationBase.instance().settings()
            settings.saveChatHistory(
                chatHistory.historyId, chatHistory.toDict())

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
        isNewConversation = not model.history
        if chatMode == AiChatMode.CodeReview:
            params.prompt = CODE_REVIEW_PROMPT.format(
                diff=params.prompt,
                language=ApplicationBase.instance().uiLanguage())
        self._doMessageReady(model, AiResponse(AiRole.User, params.prompt))

        self.btnSend.setVisible(False)
        self.btnStop.setVisible(True)
        self._historyPanel.setEnabled(False)
        self.cbBots.setEnabled(False)

        self.statusBar.showMessage(self.tr("Work in progress..."))
        self.usrInput.setFocus()

        model.queryAsync(params)

        if isNewConversation and not ApplicationBase.instance().testing and model.history:
            message = model.history[0].message
            if model.history[0].role == AiRole.System and len(model.history) > 1:
                message += "\n" + model.history[1].message
            self._generateChatTitle(
                self._historyPanel.currentHistory().historyId, message)

        self._updateChatHistoryModel(model)

    def _onMessageReady(self, response: AiResponse):
        if response.message is None:
            return

        model: AiModelBase = self.sender()
        self._doMessageReady(model, response)

    def _doMessageReady(self, model: AiModelBase, response: AiResponse):
        index = self.cbBots.findData(model)

        assert (index != -1)
        messages: AiChatbot = self._chatBot
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
        model = self.currentChatModel()
        chatHistory = self._historyPanel.updateCurrentHistory(model)
        if chatHistory:
            # Save to settings
            settings = ApplicationBase.instance().settings()
            settings.saveChatHistory(
                chatHistory.historyId, chatHistory.toDict())

        self._updateStatus()

    def _updateStatus(self):
        self.btnSend.setVisible(True)
        self.btnStop.setVisible(False)
        self._historyPanel.setEnabled(True)
        self.cbBots.setEnabled(True)
        self.usrInput.setFocus()
        self.statusBar.clearMessage()

    def _onServiceUnavailable(self):
        model: AiModelBase = self.sender()
        index = self.cbBots.findData(model)
        assert (index != -1)
        messages: AiChatbot = self._chatBot
        messages.appendServiceUnavailable()
        self._updateStatus()

    def _onModelChanged(self, index: int):
        model = self.currentChatModel()
        self.usrInput.setFocus()

        self._initChatMode(model)
        self._onChatModeChanged(self.cbChatMode.currentIndex())

        self._updateModelNames(model)

        chatHistory = self._historyPanel.currentHistory()
        if chatHistory:
            self._loadMessagesFromHistory(chatHistory.messages, False)

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

    def _onUsrInputTextChanged(self):
        curChat = self._historyPanel.currentHistory()
        enabled = curChat is not None and self.usrInput.toPlainText().strip() != ""
        self.btnSend.setEnabled(enabled)

    def _onTextBrowserScrollbarChanged(self, value):
        if self._adjustingSccrollbar:
            return

        model = self.currentChatModel()
        if model is not None and model.isRunning():
            sb: QScrollBar = self.messages.verticalScrollBar()
            self._disableAutoScroll = sb.value() != sb.maximum()

    @property
    def messages(self) -> AiChatbot:
        return self._chatBot

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

        self._waitForInitialization()
        # create a new conversation if current one is not empty
        curHistory = self._historyPanel.currentHistory()
        if not curHistory or curHistory.messages:
            self._createNewConversation()
        self._doRequest(diff, AiChatMode.CodeReview)

    def codeReviewForDiff(self, diff: str):
        self._waitForInitialization()

        curHistory = self._historyPanel.currentHistory()
        if not curHistory or curHistory.messages:
            self._createNewConversation()
        self._doRequest(diff, AiChatMode.CodeReview)

    def _waitForInitialization(self, timeout_ms: int = 5000) -> bool:
        if self._isInitialized:
            return

        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)
        self.initialized.connect(loop.quit)
        loop.exec()

    def _updateModelNames(self, model: AiModelBase):
        self.cbModelNames.clear()
        defaultId = model.modelId
        for id, name in model.models():
            self.cbModelNames.addItem(name, id)
            if id == defaultId:
                self.cbModelNames.setCurrentText(name)

    def _onModelsReady(self):
        model: AiModelBase = self.sender()
        if model == self.currentChatModel():
            self._updateModelNames(model)
            self._updateChatHistoryModel(model)

    def _updateChatHistoryModel(self, model: AiModelBase):
        self._historyPanel.updateCurrentModelId(model.modelId)

    def _onDelayInit(self):
        # Load chat histories from settings
        settings = ApplicationBase.instance().settings()
        histories = settings.chatHistories()
        chatHistories: List[AiChatHistory] = []

        for historyData in histories:
            if isinstance(historyData, dict):
                history = AiChatHistory.fromDict(historyData)
                chatHistories.append(history)

        curHistory = self._historyPanel.currentHistory()

        self._historyPanel.loadHistories(chatHistories)

        # required model to init
        self.statusBar.showMessage(self.tr("Initializing models..."))
        self._setupModels()
        self.statusBar.clearMessage()

        self._isInitialized = True
        self.initialized.emit()

        # if there is a new conversation from code review, keep it
        if curHistory and not curHistory.messages:
            self._historyPanel.blockSignals(True)
            self._historyPanel.insertHistoryAtTop(curHistory)
            self._historyPanel.blockSignals(False)
        else:
            self._createNewConversation()

        self._historyPanel.setEnabled(True)

    def _onNewChatRequested(self):
        """Create a new chat conversation"""
        self._createNewConversation()
        self.usrInput.setFocus()

    def _createNewConversation(self):
        """Create and switch to a new conversation"""
        model = self.currentChatModel()
        if model is None:
            logger.warning("Cannot create new conversation: no model available")
            return

        history = AiChatHistory()
        history.modelKey = AiModelFactory.modelKey(model)
        history.modelId = model.modelId or model.name
        self._historyPanel.insertHistoryAtTop(history)

        # Clear current chat
        self._clearCurrentChat()

    def _onHistorySelectionChanged(self, chatHistory: AiChatHistory):
        """Handle history selection change"""
        self._onUsrInputTextChanged()
        self._loadChatHistory(chatHistory)

    def _onHistoryRemoved(self, historyId: str):
        """Handle history removal"""
        # Remove from persistent storage
        settings = ApplicationBase.instance().settings()
        settings.removeChatHistory(historyId)

        # If the removed history was currently selected, create a new conversation
        currentHistory = self._historyPanel.currentHistory()
        if not currentHistory or currentHistory.historyId == historyId:
            self._createNewConversation()

    def _loadChatHistory(self, chatHistory: AiChatHistory):
        """Load a specific chat history"""
        if not chatHistory:
            self._clearCurrentChat()
            return

        # Switch to the correct model if different
        self._switchToModel(chatHistory.modelKey, chatHistory.modelId)

        # Clear and load messages
        self._clearCurrentChat()
        if not chatHistory.messages:
            return

        self._loadMessagesFromHistory(chatHistory.messages)

        sb = self.messages.verticalScrollBar()
        sb.setValue(sb.maximum())

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

    def _loadMessagesFromHistory(self, messages: List[Dict], addToChatBot = True):
        """Load messages from history into the chat"""
        if not messages:
            return

        model = self.currentChatModel()
        chatbot = self.messages

        # Clear model history and add messages
        model.clear()

        for msg in messages:
            role = AiRole.fromString(msg.get('role', 'user'))
            content = msg.get('content', '')

            if content:
                model.addHistory(role, content)
                if addToChatBot:
                    response = AiResponse(role, content)
                    chatbot.appendResponse(response)

    def _clearCurrentChat(self):
        """Clear the current chat display and model history"""
        model = self.currentChatModel()
        if model:
            model.clear()
        self.messages.clear()

    def _generateChatTitle(self, historyId: str, firstMessage: str):
        """Generate a title for the conversation"""
        if not firstMessage.strip():
            return

        if not self._titleGenerator:
            self._titleGenerator = AiChatTitleGenerator(self)
            self._titleGenerator.titleReady.connect(self._onChatTitleReady)
        self._titleGenerator.startGenerate(
            historyId, firstMessage)

    def _onChatTitleReady(self, historyId: str, title: str):
        """Handle generated title"""
        chatHistory = self._historyPanel.updateTitle(historyId, title)
        if not chatHistory:
            return

        # Save to settings
        settings = ApplicationBase.instance().settings()
        settings.saveChatHistory(historyId, chatHistory.toDict())


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
