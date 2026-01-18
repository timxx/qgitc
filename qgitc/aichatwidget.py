# -*- coding: utf-8 -*-

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QEventLoop, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QScrollBar, QSplitter, QVBoxLayout, QWidget

from qgitc.agenttoolexecutor import AgentToolExecutor, AgentToolResult
from qgitc.agenttools import AgentToolRegistry, ToolType, parseToolArguments
from qgitc.aichatbot import AiChatbot
from qgitc.aichatcontextpanel import AiChatContextPanel
from qgitc.aichathistory import AiChatHistory
from qgitc.aichathistorypanel import AiChatHistoryPanel
from qgitc.aichattitlegenerator import AiChatTitleGenerator
from qgitc.applicationbase import ApplicationBase
from qgitc.common import commitRepoDir, logger
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
from qgitc.preferences import Preferences


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
        self._agentExecutor = AgentToolExecutor(self)
        self._agentExecutor.toolFinished.connect(self._onAgentToolFinished)
        self._pendingAgentTool: str = None

        # Auto-run queue for READ_ONLY tools.
        # Each item: (tool_name, params, group_id)
        self._autoToolQueue: List[Tuple[str, dict, int]] = []
        # group_id -> {remaining:int, outputs:[str], auto_continue:bool}
        self._autoToolGroups: Dict[int, Dict[str, object]] = {}
        self._nextAutoGroupId: int = 1
        self._pendingToolSource: Optional[str] = None  # 'auto' | 'approved'
        self._pendingAutoGroupId: Optional[int] = None

        self._isInitialized = False
        QTimer.singleShot(100, self._onDelayInit)

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
        self._chatBot.toolConfirmationApproved.connect(self._onToolApproved)
        self._chatBot.toolConfirmationRejected.connect(self._onToolRejected)
        layout.addWidget(self._chatBot)

        self._contextPanel = AiChatContextPanel(self)
        layout.addWidget(self._contextPanel)
        self._contextPanel.setFocus()

        self._contextPanel.enterPressed.connect(
            self._onEnterKeyPressed)
        self._contextPanel.textChanged.connect(
            self._onUsrInputTextChanged)

        self._contextPanel.btnSend.clicked.connect(self._onButtonSend)
        self._contextPanel.btnStop.clicked.connect(self._onButtonStop)

        self._contextPanel.cbBots.currentIndexChanged.connect(
            self._onModelChanged)
        self._contextPanel.btnSettings.clicked.connect(
            self._onOpenSettings)

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
            self._contextPanel.cbBots.addItem(model.name, model)
            model.responseAvailable.connect(self._onMessageReady)
            model.finished.connect(self._onResponseFinish)
            model.serviceUnavailable.connect(self._onServiceUnavailable)
            if AiModelFactory.modelKey(model) == defaultModelKey:
                currentModelIndex = i

            model.modelsReady.connect(self._onModelsReady)

        if currentModelIndex != -1:
            self._contextPanel.cbBots.setCurrentIndex(currentModelIndex)

        self._onModelChanged(self._contextPanel.cbBots.currentIndex())

    def queryClose(self):
        if self._titleGenerator:
            self._titleGenerator.cancel()

        if self._agentExecutor:
            self._agentExecutor.shutdown()

        for i in range(self._contextPanel.cbBots.count()):
            model: AiModelBase = self._contextPanel.cbBots.itemData(i)
            if model.isRunning():
                model.requestInterruption()
            model.cleanup()

    def sizeHint(self):
        return QSize(800, 600)

    def _onButtonSend(self, clicked):
        prompt = self._contextPanel.userPrompt().strip()
        if not prompt:
            return

        model = self.currentChatModel()
        chatMode: AiChatMode = self._contextPanel.currentMode()
        self._doRequest(prompt, chatMode)

        app = ApplicationBase.instance()
        app.trackFeatureUsage("aichat_send", {
            "chat_mode": chatMode.name,
            "model": model.modelId or model.name,
        })

        # Clear input after sending
        self._contextPanel.clear()

    def _onButtonStop(self):
        model = self.currentChatModel()
        if not model.isRunning():
            return

        model.requestInterruption()

        chatHistory = self._historyPanel.updateCurrentHistory(model)
        if chatHistory:
            settings = ApplicationBase.instance().settings()
            settings.saveChatHistory(
                chatHistory.historyId, chatHistory.toDict())

    def _doRequest(self, prompt: str, chatMode: AiChatMode, sysPrompt: str = None, collapsed=False):
        params = AiParameters()
        params.prompt = prompt
        params.sys_prompt = sysPrompt
        params.stream = True
        # TODO: make these configurable
        params.temperature = 0.1
        params.chat_mode = chatMode
        params.model = self._contextPanel.currentModelId()

        self._disableAutoScroll = False

        model = self.currentChatModel()
        isNewConversation = not model.history

        if chatMode == AiChatMode.Agent:
            params.tools = AgentToolRegistry.openai_tools()
            params.tool_choice = "auto"

            if not Git.REPO_DIR:
                self._doMessageReady(model, AiResponse(
                    AiRole.User, params.prompt), collapsed)
                self._doMessageReady(model, AiResponse(
                    AiRole.System, self.tr("No repository is currently opened.")))
                return

            # Don't add system prompt if there is already one
            if not sysPrompt and (len(model.history) == 0 or not collapsed):
                params.sys_prompt = (
                    "You are a Git assistant inside QGitc. "
                    "When you need repo information or to perform git actions, call tools. "
                    "Never assume; use tools like git_status/git_log/git_diff/git_show/git_current_branch/git_branch. "
                    "If the user asks for the Nth commit, call git_log with the 'nth' parameter; the tool returns a labeled single-line result that you should trust. "
                    "Do not call git_log repeatedly to fetch commits 1..N just to locate the Nth commit. "
                    "After a tool result is provided, continue with the user's request."
                )
                self._doMessageReady(model, AiResponse(
                    AiRole.System, params.sys_prompt), True)
        elif chatMode == AiChatMode.CodeReview:
            params.prompt = CODE_REVIEW_PROMPT.format(
                diff=params.prompt,
                language=ApplicationBase.instance().uiLanguage())
        self._doMessageReady(model, AiResponse(
            AiRole.User, params.prompt), collapsed)

        self._contextPanel.btnSend.setVisible(False)
        self._contextPanel.btnStop.setVisible(True)
        self._historyPanel.setEnabled(False)
        self._contextPanel.cbBots.setEnabled(False)
        self._contextPanel.setFocus()

        model.queryAsync(params)

        if isNewConversation and not ApplicationBase.instance().testing and model.history:
            message = model.history[0].message
            if model.history[0].role == AiRole.System and len(model.history) > 1:
                message += "\n" + model.history[1].message
            self._generateChatTitle(
                self._historyPanel.currentHistory().historyId, message)

        self._updateChatHistoryModel(model)

    def _onMessageReady(self, response: AiResponse):
        # tool-only responses can have empty message.
        if response.message is None and not response.tool_calls:
            return

        model: AiModelBase = self.sender()
        self._doMessageReady(model, response)

    def _doMessageReady(self, model: AiModelBase, response: AiResponse, collapsed=False):
        index = self._contextPanel.cbBots.findData(model)

        assert (index != -1)
        messages: AiChatbot = self._chatBot
        if response.message:
            messages.appendResponse(response, collapsed)

        # If the assistant produced tool calls, auto-run READ_ONLY tools and
        # insert confirmations for WRITE/DANGEROUS tools.
        if response.role == AiRole.Assistant and response.tool_calls:
            autoGroupId: Optional[int] = None
            autoToolsCount = 0
            hasConfirmations = False

            for tc in response.tool_calls:
                func = (tc or {}).get("function") or {}
                toolName = func.get("name")
                args = parseToolArguments(func.get("arguments"))
                tool = AgentToolRegistry.tool_by_name(
                    toolName) if toolName else None

                if toolName and tool and tool.tool_type == ToolType.READ_ONLY:
                    if autoGroupId is None:
                        autoGroupId = self._nextAutoGroupId
                        self._nextAutoGroupId += 1
                    self._autoToolQueue.append(
                        (toolName, args or {}, autoGroupId))
                    autoToolsCount += 1
                    continue

                # Anything else requires explicit confirmation.
                if toolName and tool:
                    hasConfirmations = True
                    messages.insertToolConfirmation(
                        toolName=toolName,
                        params=args,
                        toolDesc=tool.description,
                        toolType=tool.tool_type,
                    )
                elif toolName:
                    hasConfirmations = True
                    messages.insertToolConfirmation(
                        toolName=toolName,
                        params=args,
                        toolDesc=self.tr("Unknown tool requested by model"),
                    )

            if autoGroupId is not None and autoToolsCount:
                # Only auto-continue once all READ_ONLY tools finish, and only
                # if there are no pending confirmations from the same tool-call batch.
                self._autoToolGroups[autoGroupId] = {
                    "remaining": autoToolsCount,
                    "outputs": [],
                    "auto_continue": not hasConfirmations,
                }
                self._startNextAutoToolIfIdle()

        if not self._disableAutoScroll:
            sb = messages.verticalScrollBar()
            self._adjustingSccrollbar = True
            sb.setValue(sb.maximum())
            self._adjustingSccrollbar = False

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
        self._contextPanel.btnSend.setVisible(True)
        self._contextPanel.btnStop.setVisible(False)
        self._historyPanel.setEnabled(True)
        self._contextPanel.cbBots.setEnabled(True)
        self._contextPanel.setFocus()

    def _onToolApproved(self, tool_name: str, params: dict):
        # Prevent overlapping executions.
        if self._pendingAgentTool:
            self._doMessageReady(self.currentChatModel(), AiResponse(
                AiRole.System, self.tr("A tool is already running.")))
            return

        self._pendingAgentTool = tool_name
        self._pendingToolSource = "approved"
        self._pendingAutoGroupId = None

        started = self._agentExecutor.executeAsync(tool_name, params or {})
        if not started:
            self._pendingAgentTool = None
            self._pendingToolSource = None
            self._doMessageReady(self.currentChatModel(), AiResponse(
                AiRole.System, self.tr("Failed to start tool execution.")))

    def _onToolRejected(self, tool_name: str):
        # Keep it simple: just record and continue.
        model = self.currentChatModel()
        msg = self.tr("Tool rejected: {0}").format(tool_name)
        model.addHistory(AiRole.System, msg)
        self._doMessageReady(model, AiResponse(AiRole.System, msg))

    def _onAgentToolFinished(self, result: AgentToolResult):
        model = self.currentChatModel()
        tool_name = result.tool_name
        ok = result.ok
        output = result.output or ""

        source = self._pendingToolSource
        group_id = self._pendingAutoGroupId

        self._pendingAgentTool = None
        self._pendingToolSource = None
        self._pendingAutoGroupId = None

        prefix = "✓" if ok else "✗"
        tool_msg = f"{prefix} Tool `{tool_name}` result:\n\n{output}" if output else f"{prefix} Tool `{tool_name}` finished."

        model.addHistory(AiRole.Tool, tool_msg)
        self._doMessageReady(model, AiResponse(
            AiRole.Tool, tool_msg), collapsed=True)

        if source == "auto" and group_id is not None and group_id in self._autoToolGroups:
            group = self._autoToolGroups[group_id]
            outputs: list = group.get("outputs", [])
            outputs.append(
                f"[{tool_name}]\n{output}" if output else f"[{tool_name}] (no output)")
            group["outputs"] = outputs

            remaining = int(group.get("remaining", 0)) - 1
            group["remaining"] = remaining

            if remaining <= 0:
                auto_continue = bool(group.get("auto_continue", True))
                combined = "\n\n".join(outputs)
                del self._autoToolGroups[group_id]
                if auto_continue:
                    followup = combined
                    if followup:
                        self._doRequest(
                            followup, AiChatMode.Agent, collapsed=True)

            # Continue draining the queue.
            self._startNextAutoToolIfIdle()
            return

        # Approved (WRITE/DANGEROUS) tools: send ONLY the tool output back as a collapsed user message.
        followup = f"[{tool_name}]\n{output}" if output else f"[{tool_name}] (no output)"
        self._doRequest(followup, AiChatMode.Agent, collapsed=True)

    def _startNextAutoToolIfIdle(self):
        if self._pendingAgentTool:
            return
        if not self._autoToolQueue:
            return

        tool_name, params, group_id = self._autoToolQueue.pop(0)
        self._pendingAgentTool = tool_name
        self._pendingToolSource = "auto"
        self._pendingAutoGroupId = group_id

        started = self._agentExecutor.executeAsync(tool_name, params or {})
        if not started:
            # Fall back to a synthetic failure result and keep draining.
            self._pendingAgentTool = None
            self._pendingToolSource = None
            self._pendingAutoGroupId = None
            self._onAgentToolFinished(AgentToolResult(
                tool_name, False, self.tr("Failed to start tool execution.")))

    def _onServiceUnavailable(self):
        model: AiModelBase = self.sender()
        index = self._contextPanel.cbBots.findData(model)
        assert (index != -1)
        messages: AiChatbot = self._chatBot
        messages.appendServiceUnavailable()
        self._updateStatus()

    def _onModelChanged(self, index: int):
        model = self.currentChatModel()
        self._contextPanel.setFocus()
        self._contextPanel.setupModelNames(model)

        chatHistory = self._historyPanel.currentHistory()
        if chatHistory:
            self._loadMessagesFromHistory(chatHistory.messages, False)

    def _onEnterKeyPressed(self):
        self._onButtonSend(False)

    def _onUsrInputTextChanged(self):
        curChat = self._historyPanel.currentHistory()
        enabled = curChat is not None and self._contextPanel.userPrompt().strip() != ""
        self._contextPanel.btnSend.setEnabled(enabled)

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
        return self._contextPanel.cbBots.currentData()

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

    def _onModelsReady(self):
        model: AiModelBase = self.sender()
        if model == self.currentChatModel():
            self._contextPanel.setupModelNames(model)
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

        self._setupModels()
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
        self._contextPanel.setFocus()

    def _createNewConversation(self):
        """Create and switch to a new conversation"""
        model = self.currentChatModel()
        if model is None:
            logger.warning(
                "Cannot create new conversation: no model available")
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
        self._contextPanel.switchToModel(
            chatHistory.modelKey, chatHistory.modelId)

        # Clear and load messages
        self._clearCurrentChat()
        if not chatHistory.messages:
            return

        self._loadMessagesFromHistory(chatHistory.messages)

        sb = self.messages.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _loadMessagesFromHistory(self, messages: List[Dict], addToChatBot=True):
        """Load messages from history into the chat"""
        if not messages:
            return

        model = self.currentChatModel()
        chatbot = self.messages

        # Clear model history and add messages
        model.clear()

        if addToChatBot:
            chatbot.setHighlighterEnabled(False)

        prevRole = None
        for msg in messages:
            role = AiRole.fromString(msg.get('role', 'user'))
            content = msg.get('content', '')
            if not content:
                prevRole = role
                continue

            model.addHistory(role, content)
            if addToChatBot:
                response = AiResponse(role, content)
                # Auto-collapse Tool messages and user messages that follow Tool messages
                collapsed = (role == AiRole.Tool) or (role == AiRole.System) or (
                    role == AiRole.User and prevRole == AiRole.Tool)
                chatbot.appendResponse(response, collapsed=collapsed)

            prevRole = role

        if addToChatBot:
            chatbot.setHighlighterEnabled(True)

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

    def _onOpenSettings(self):
        settings = ApplicationBase.instance().settings()
        dlg = Preferences(settings)
        dlg.ui.tabWidget.setCurrentWidget(dlg.ui.tabLLM)
        dlg.exec()
