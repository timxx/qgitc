from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QStackedWidget,
    QGridLayout,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
    QSpacerItem,
    QTextBrowser,
    QComboBox,
    QPushButton,
    QStatusBar,
    QScrollBar)

from PySide6.QtGui import (
    QTextCursor,
    QTextBlockFormat,
    QTextCharFormat,
    QFont)

from PySide6.QtCore import (
    QThread,
    Signal,
    QSize,
    Qt)

import json
import queue as queue
import multiprocessing
import threading
import requests

from .common import commitRepoDir
from .gitutils import Git
from .llm import AiChatMode, AiModelBase, AiParameters, AiResponse, LocalLLM
from .statewindow import StateWindow


class LocalLLMTokensCalculator(QThread):

    calcTokensFinished = Signal(int)

    def __init__(self, url):
        super().__init__()
        self._tasks = queue.Queue()
        self._server_url = url

    def calc_async(self, model, text):
        self._tasks.put((model, text))

    def run(self):
        while not self.isInterruptionRequested():
            model, text = self._tasks.get()
            if model is None:
                break

            tokens = LocalLLMTokensCalculator.calc_tokens(
                self._server_url, model, text)
            self.calcTokensFinished.emit(tokens)

    @staticmethod
    def calc_tokens(url, model, text):
        url = f"{url}/tokens"
        payload = {
            "text": text,
            "model": model,
        }

        headers = {
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                url, headers=headers, json=payload, stream=False)
            if not response.ok:
                return 0

            data = json.loads(response.text)
            return int(data["tokens"])
        except:
            return 0


class ChatThread(QThread):

    responseAvailable = Signal(AiModelBase, AiResponse)
    responseFinish = Signal()
    serviceUnavailable = Signal(AiModelBase)

    def __init__(self, model: AiModelBase, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._task_queue = queue.Queue(multiprocessing.cpu_count())
        self._model = model
        self._querying = False

        self._model.responseAvailable.connect(
            self._onResponseAvailable, Qt.UniqueConnection)
        self._model.serviceUnavailable.connect(
            self._onServiceUnavailable, Qt.UniqueConnection)

    def addTask(self, params: AiParameters):
        self._task_queue.put(params)

    def clearHistory(self):
        self._model.clear()

    def run(self):
        while not self.isInterruptionRequested():
            task = self._task_queue.get()
            if task is None:
                break

            with self._lock:
                self._querying = True
            self._model.query(task)
            self.responseFinish.emit()

            with self._lock:
                self._querying = False

    def inQuery(self):
        with self._lock:
            return self._querying

    def _onResponseAvailable(self, response):
        self.responseAvailable.emit(self._model, response)

    def _onServiceUnavailable(self):
        self.serviceUnavailable.emit(self._model)


class ChatEdit(QWidget):
    MaxLines = 5
    enterPressed = Signal()
    textChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        self.edit = QPlainTextEdit(self)
        layout.addWidget(self.edit)

        font = self.font()
        font.setPointSize(9)
        self.setFont(font)

        self.setFocusProxy(self.edit)

        self._margin = 6
        self.edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.edit.document().setDocumentMargin(4)

        self._lineHeight = self.fontMetrics().height()
        self._lineSpace = self.height() - self._lineHeight

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
        if lineCount < ChatEdit.MaxLines:
            height = lineCount * self._lineHeight + self._lineSpace
            self.edit.setMinimumHeight(height - self._margin)
            self.setFixedHeight(height + margin)
        else:
            maxHeight = ChatEdit.MaxLines * self._lineHeight + self._lineSpace
            self.edit.setMinimumHeight(maxHeight - self._margin)
            self.setFixedHeight(maxHeight + margin)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() in [Qt.Key_Enter, Qt.Key_Return]:
            self.enterPressed.emit()

        return super().keyPressEvent(event)


class AiChatWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.stackWidget = QStackedWidget(self)
        layout.addWidget(self.stackWidget)

        self.usrInput = ChatEdit(self)
        self.usrInput.setPlaceholderText(
            self.tr("Enter the query prompt here"))
        self.usrInput.setFocus()

        self.usrInput.enterPressed.connect(
            self._onEnterKeyPressed)
        self.usrInput.textChanged.connect(
            self._onPromptTextChanged)

        gridLayout = QGridLayout()
        gridLayout.setContentsMargins(0, 0, 0, 0)
        gridLayout.setSpacing(0)
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
        self.sbMaxTokens.setValue(2048)
        self.sbMaxTokens.setMaximumWidth(60)
        self.sbMaxTokens.setToolTip(self.tr("Max tokens to generate"))
        hlayout.addWidget(self.sbMaxTokens)

        hlayout.addWidget(QLabel(self.tr("Temperature"), self))
        self.sbTemperature = QDoubleSpinBox(self)
        self.sbTemperature.setRange(0.0, 1.0)
        self.sbTemperature.setSingleStep(0.1)
        self.sbTemperature.setValue(0)
        hlayout.addWidget(self.sbTemperature)

        self.cbBots = QComboBox(self)
        self.cbBots.setEditable(False)
        self.cbBots.setMinimumWidth(130)

        self._ai_models = [
            LocalLLM(qApp.settings().llmServer(), self),
        ]

        self._ai_models[0].nameChanged.connect(
            self._onModelNameChanged)

        for model in self._ai_models:
            self.cbBots.addItem(model.name)
            tb = QTextBrowser(self)
            self.stackWidget.addWidget(tb)
            tb.verticalScrollBar().valueChanged.connect(
                self._onTextBrowserScrollbarChanged)

        self.stackWidget.setCurrentIndex(self.cbBots.currentIndex())

        hlayout.addWidget(self.cbBots)

        self.cbChatMode = QComboBox(self)
        self.cbChatMode.setEditable(False)
        self.cbChatMode.addItem(self.tr("Chat"), AiChatMode.Chat)
        self.cbChatMode.addItem(self.tr("Completion"), AiChatMode.Completion)
        self.cbChatMode.addItem(self.tr("Infilling"), AiChatMode.Infilling)
        self.cbChatMode.addItem(self.tr("Code Review"), AiChatMode.CodeReview)
        self.cbChatMode.addItem(self.tr("Code Fix"), AiChatMode.CodeFix)
        self.cbChatMode.addItem(
            self.tr("Code Explanation"), AiChatMode.CodeExplanation)
        self.cbChatMode.setEnabled(True)

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

        self._chatThreads = {}

        self.cbBots.currentIndexChanged.connect(
            self._onModelChanged)
        self.cbChatMode.currentIndexChanged.connect(
            self._onChatModeChanged)

        QWidget.setTabOrder(self.usrInput, self.btnSend)
        QWidget.setTabOrder(self.btnSend, self.btnClear)
        QWidget.setTabOrder(self.btnClear, self.usrInput)

        self._disableAutoScroll = False
        self._adjustingSccrollbar = False

        self._tokenCalculator = None

    def __del__(self):
        for _, thread in self._chatThreads.items():
            thread.requestInterruption()
            thread.addTask(None)

        if self._tokenCalculator:
            self._tokenCalculator.calc_async(None, None)
            self._tokenCalculator.requestInterruption()

    def sizeHint(self):
        return QSize(800, 600)

    def _ensureChatThread(self):
        index = self.cbBots.currentIndex()
        if index in self._chatThreads:
            return

        chatThread = ChatThread(self._ai_models[index], self)
        chatThread.responseAvailable.connect(
            self._onMessageReady)
        chatThread.responseFinish.connect(
            self._onResponseFinish)
        chatThread.serviceUnavailable.connect(
            self._onServiceUnavailable)
        chatThread.start()

        self._chatThreads[index] = chatThread

    def _onButtonSend(self, clicked):
        self._doRequest(
            self.usrInput.toPlainText(),
            self.cbChatMode.currentData(),
            self.cbLang.currentText())

    def _doRequest(self, prompt, chatMode, language=""):
        params = AiParameters()
        params.prompt = prompt
        params.stream = True
        params.temperature = self.sbTemperature.value()
        params.max_tokens = self.sbMaxTokens.value()
        params.chat_mode = chatMode
        params.language = language

        if self.isLocalLLM():
            if params.chat_mode == AiChatMode.Infilling:
                params.fill_point = self.usrInput.textCursor().position()

        self._disableAutoScroll = False

        self._ensureChatThread()

        self._onMessageReady(None, AiResponse("user", params.prompt))

        self.currentChatThread().addTask(params)

        self.btnSend.setEnabled(False)
        self.btnClear.setEnabled(False)

        self.statusBar.showMessage(self.tr("Work in progress..."))
        self.usrInput.setFocus()

    def _onButtonClear(self, clicked):
        if chatThread := self.currentChatThread():
            chatThread.clearHistory()
        self.messages.clear()

    def _onMessageReady(self, model, response: AiResponse):
        if response.message is None:
            return

        index = -1
        if model is None:
            index = self.cbBots.currentIndex()
        else:
            index = self._ai_models.index(model)

        assert (index != -1)
        messages = self.stackWidget.widget(index)

        cursor = messages.textCursor()
        cursor.movePosition(QTextCursor.End)

        format = QTextBlockFormat()
        roleFormat = QTextCharFormat()
        roleFormat.setFontWeight(QFont.Bold)
        if messages.document().blockCount() == 1:
            cursor.setBlockCharFormat(roleFormat)
        elif not response.is_delta or response.first_delta:
            cursor.insertBlock(format, roleFormat)
        if not response.is_delta or response.first_delta:
            cursor.insertText(response.role + ":")

        if response.role != "user" and response.role != "system":
            format.setBackground(Qt.lightGray)

        if not response.is_delta or response.first_delta:
            cursor.insertBlock(format, QTextCharFormat())
        cursor.insertText(response.message)

        if not response.is_delta:
            cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
            cursor.insertText("")

        if not self._disableAutoScroll:
            sb = messages.verticalScrollBar()
            self._adjustingSccrollbar = True
            sb.setValue(sb.maximum())
            self._adjustingSccrollbar = False

        if response.total_tokens != None:
            self.statusBar.showMessage(
                f"Totoal tokens {response.total_tokens}")

    def _onResponseFinish(self):
        clear = True
        for thread in self._chatThreads.values():
            if thread.inQuery():
                clear = False
                break

        thread = self.currentChatThread()
        enabled = thread is None or not thread.inQuery()
        self.btnSend.setEnabled(enabled)
        self.btnClear.setEnabled(enabled)
        if clear:
            self.statusBar.clearMessage()
        self.usrInput.setFocus()

    def _onServiceUnavailable(self, model):
        index = -1
        if model is None:
            index = self.cbBots.currentIndex()
        else:
            index = self._ai_models.index(model)

        assert (index != -1)
        messages = self.stackWidget.widget(index)

        cursor = messages.textCursor()
        cursor.movePosition(QTextCursor.End)

        format = QTextBlockFormat()
        roleFormat = QTextCharFormat()
        roleFormat.setFontWeight(QFont.Bold)
        cursor.insertBlock(format, roleFormat)
        cursor.insertText("System:")

        errorFormat = QTextCharFormat()
        errorFormat.setForeground(qApp.colorSchema().ErrorText)
        cursor.insertBlock(QTextBlockFormat(), errorFormat)
        cursor.insertText(self.tr("Service Unavailable"))
        cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())

    def _onModelChanged(self, index):
        self.stackWidget.setCurrentIndex(index)

        thread = self.currentChatThread()
        enabled = thread is None or not thread.inQuery()

        self.btnSend.setEnabled(enabled)
        self.btnClear.setEnabled(enabled)
        self.usrInput.setFocus()

        self.cbChatMode.setEnabled(self.isLocalLLM())
        self._onChatModeChanged(self.cbChatMode.currentIndex())

    def _onChatModeChanged(self, index):
        self.cbLang.setEnabled(
            self.isLocalLLM() and self.cbChatMode.currentData() == AiChatMode.Infilling)

    def _onEnterKeyPressed(self):
        self._onButtonSend(False)

    def _onPromptTextChanged(self):
        if not self.isLocalLLM():
            self.lbTokens.clear()
            return

        if self._tokenCalculator is None:
            self._tokenCalculator = LocalLLMTokensCalculator(
                qApp.settings().llmServer())
            self._tokenCalculator.start()
            self._tokenCalculator.calcTokensFinished.connect(
                self._onCalcTokensFinished)

        self._tokenCalculator.calc_async(
            self.cbBots.currentText(),
            self.usrInput.toPlainText())

    def _onTextBrowserScrollbarChanged(self, value):
        if self._adjustingSccrollbar:
            return

        chatThread = self.currentChatThread()
        if chatThread is not None and chatThread.inQuery():
            sb: QScrollBar = self.messages.verticalScrollBar()
            self._disableAutoScroll = sb.value() != sb.maximum()

    def _onModelNameChanged(self):
        model = self.sender()
        index = self._ai_models.index(model)
        self.cbBots.setItemText(index, model.name)

    def _onCalcTokensFinished(self, tokens):
        self.lbTokens.setText(f"{tokens} tokens")

    @property
    def messages(self):
        return self.stackWidget.currentWidget()

    def currentChatThread(self):
        index = self.cbBots.currentIndex()
        if index not in self._chatThreads:
            return None

        return self._chatThreads[index]

    def isLocalLLM(self):
        return self.cbBots.currentIndex() == 0

    def codeReview(self, commit, args):
        repoDir = commitRepoDir(commit)
        data: bytes = Git.commitRawDiff(commit.sha1, gitArgs=args, repoDir=repoDir)
        if not data:
            return
        
        for subCommit in commit.subCommits:
            repoDir = commitRepoDir(subCommit)
            subData = Git.commitRawDiff(subCommit.sha1, gitArgs=args, repoDir=repoDir)
            if subData:
                data += b"\n" + subData

        diff = data.decode("utf-8", errors="replace")
        self._doRequest(diff, AiChatMode.CodeReview)


class AiChatWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(self.tr("AI Assistant"))
        centralWidget = AiChatWidget(self)
        self.setCentralWidget(centralWidget)

    def codeReview(self, commit, args=None):
        self.centralWidget().codeReview(commit, args)
