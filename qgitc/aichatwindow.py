from typing import List, Union
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
    QComboBox,
    QPushButton,
    QStatusBar,
    QScrollBar)

from PySide6.QtCore import (
    QThread,
    Signal,
    QSize,
    Qt,
    QEvent)

import json
import queue as queue
import requests

from .aichatbot import AiChatbot
from .cancelevent import CancelEvent
from .common import commitRepoDir, fullRepoDir, toSubmodulePath
from .githubcopilot import GithubCopilot
from .gitutils import Git
from .llm import AiChatMode, AiModelBase, AiParameters, AiResponse, AiRole, LocalLLM
from .statewindow import StateWindow
from .submoduleexecutor import SubmoduleExecutor


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
        self.sbMaxTokens.setValue(4096)
        self.sbMaxTokens.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        self.sbMaxTokens.setToolTip(self.tr("Max tokens to generate"))
        hlayout.addWidget(self.sbMaxTokens)

        hlayout.addWidget(QLabel(self.tr("Temperature"), self))
        self.sbTemperature = QDoubleSpinBox(self)
        self.sbTemperature.setRange(0.0, 1.0)
        self.sbTemperature.setSingleStep(0.1)
        self.sbTemperature.setValue(0.1)
        hlayout.addWidget(self.sbTemperature)

        self.cbBots = QComboBox(self)
        self.cbBots.setEditable(False)
        self.cbBots.setMinimumWidth(130)

        aiModels: List[AiModelBase] = [
            LocalLLM(qApp.settings().llmServer(), self),
            GithubCopilot(self),
        ]

        aiModels[0].nameChanged.connect(
            self._onModelNameChanged)

        for model in aiModels:
            self.cbBots.addItem(model.name, model)
            tb = AiChatbot(self)
            self.stackWidget.addWidget(tb)
            tb.verticalScrollBar().valueChanged.connect(
                self._onTextBrowserScrollbarChanged)
            model.responseAvailable.connect(self._onMessageReady)
            model.finished.connect(self._onResponseFinish)
            model.serviceUnavailable.connect(self._onServiceUnavailable)

        if qApp.settings().useLocalLlm():
            self.cbBots.setCurrentIndex(0)
        else:
            self.cbBots.setCurrentIndex(1)

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
        self.cbChatMode.setEnabled(self.isLocalLLM())

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

        QWidget.setTabOrder(self.usrInput, self.btnSend)
        QWidget.setTabOrder(self.btnSend, self.btnClear)
        QWidget.setTabOrder(self.btnClear, self.usrInput)

        self._disableAutoScroll = False
        self._adjustingSccrollbar = False

        self._tokenCalculator = None

    def queryClose(self):
        if self._tokenCalculator:
            self._tokenCalculator.calc_async(None, None)
            self._tokenCalculator.requestInterruption()
            self._tokenCalculator = None

        for i in range(self.cbBots.count()):
            model: AiModelBase = self.cbBots.itemData(i)
            if model.isRunning():
                model.requestInterruption()

    def sizeHint(self):
        return QSize(800, 600)

    def _onButtonSend(self, clicked):
        self._doRequest(
            self.usrInput.toPlainText(),
            self.cbChatMode.currentData(),
            self.cbLang.currentText())

    def _doRequest(self, prompt: str, chatMode: AiChatMode, language=""):
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
        if model := self.currentChatModel():
            model.clear()
        self.messages.clear()

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

        if response.total_tokens != None:
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

    def _onModelChanged(self, index):
        self.stackWidget.setCurrentIndex(index)

        model = self.currentChatModel()
        enabled = model is None or not model.isRunning()

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

        model = self.currentChatModel()
        if model is not None and model.isRunning():
            sb: QScrollBar = self.messages.verticalScrollBar()
            self._disableAutoScroll = sb.value() != sb.maximum()

    def _onModelNameChanged(self):
        model: AiModelBase = self.sender()
        index = self.cbBots.findData(model)
        self.cbBots.setItemText(index, model.name)

    def _onCalcTokensFinished(self, tokens):
        self.lbTokens.setText(f"{tokens} tokens")

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
        data: bytes = Git.commitRawDiff(Git.LCC_SHA1, repoFiles, repoDir=repoDir)
        if not data:
            return

        if cancelEvent.isSet():
            return

        diff = data.decode("utf-8", errors="replace")
        qApp.postEvent(self, DiffAvailableEvent(diff))

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
