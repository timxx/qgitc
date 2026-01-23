# -*- coding: utf-8 -*-

import json
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QEventLoop, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollBar,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from qgitc.agenttoolexecutor import AgentToolExecutor, AgentToolResult
from qgitc.agenttools import AgentToolRegistry, ToolType, parseToolArguments
from qgitc.aichatbot import AiChatbot
from qgitc.aichatcontextpanel import AiChatContextPanel
from qgitc.aichatcontextprovider import AiChatContextProvider
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
from qgitc.models.prompts import AGENT_SYS_PROMPT, CODE_REVIEW_PROMPT
from qgitc.preferences import Preferences


class AiChatWidget(QWidget):

    initialized = Signal()
    chatTitleReady = Signal()

    def __init__(self, parent=None, embedded=False):
        super().__init__(parent)

        self._embedded = embedded
        if not embedded:
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
        self._historyPanel.requestNewChat.connect(self.onNewChatRequested)
        self._historyPanel.historySelectionChanged.connect(
            self._onHistorySelectionChanged)
        self._historyPanel.historyRemoved.connect(self._onHistoryRemoved)

        if not self._embedded:
            self.splitter.addWidget(self._historyPanel)
        else:
            # Embedded mode: show history panel at the top in compact mode.
            self._historyPanel.setCompactMode(True)
            self._historyPanel.setMaxVisibleRows(3)

        # wait until history loaded
        self._historyPanel.setEnabled(False)

    def _setupChatPanel(self):
        if not self._embedded:
            chatWidget = QWidget(self)
            layout = QVBoxLayout(chatWidget)
            layout.setContentsMargins(0, 0, 0, 0)
            self.splitter.addWidget(chatWidget)
            self.splitter.setSizes([200, 600])
        else:  # as main layout
            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(0)

            # Embedded mode: mount the existing history panel at the top.
            layout.addWidget(self._historyPanel)
            self._historyPanel.setSizePolicy(
                QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._chatBot = AiChatbot(self)
        self._chatBot.verticalScrollBar().valueChanged.connect(
            self._onTextBrowserScrollbarChanged)
        self._chatBot.toolConfirmationApproved.connect(self._onToolApproved)
        self._chatBot.toolConfirmationRejected.connect(self._onToolRejected)
        layout.addWidget(self._chatBot)
        self._chatBot.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)

        showSettings = not self._embedded
        self._contextPanel = AiChatContextPanel(showSettings, self)

        if self._embedded:
            layout.addSpacing(4)

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

        if showSettings:
            self._contextPanel.btnSettings.clicked.connect(
                self.onOpenSettings)

        self._disableAutoScroll = False
        self._adjustingSccrollbar = False

    def setContextProvider(self, provider: AiChatContextProvider | None):
        self._contextPanel.setContextProvider(provider)

    def contextProvider(self) -> AiChatContextProvider | None:
        return self._contextPanel.contextProvider()

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
            model.networkError.connect(self._onNetworkError)
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
        if self._embedded:
            return QSize(400, 600)
        return QSize(800, 600)

    def historyPanel(self):
        return self._historyPanel

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
        self._saveChatHistory(model)

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

        self._setEmbeddedRecentListVisible(False)

        # Keep title generation based on the user's original prompt (no injected context).
        titleSeed = (params.sys_prompt + "\n" +
                     prompt) if params.sys_prompt else prompt

        if chatMode == AiChatMode.Agent:
            params.tools = AgentToolRegistry.openai_tools()
            params.tool_choice = "auto"

            # Don't add system prompt if there is already one
            if not sysPrompt and (len(model.history) == 0 or not collapsed):
                provider = self.contextProvider()
                overridePrompt = provider.agentSystemPrompt() if provider is not None else None
                params.sys_prompt = overridePrompt or AGENT_SYS_PROMPT
                self._doMessageReady(model, AiResponse(
                    AiRole.System, params.sys_prompt), True)
        elif chatMode == AiChatMode.CodeReview:
            params.prompt = CODE_REVIEW_PROMPT.format(
                diff=params.prompt,
                language=ApplicationBase.instance().uiLanguage())

        provider = self.contextProvider()
        if not collapsed and provider is not None:
            selectedIds = self._contextPanel.selectedContextIds()
            contextText = provider.buildContextText(selectedIds)
            if contextText:
                params.prompt = f"<context>\n{contextText}\n</context>\n\n" + \
                    params.prompt

        self._doMessageReady(model, AiResponse(
            AiRole.User, params.prompt), collapsed)

        self._contextPanel.btnSend.setVisible(False)
        self._contextPanel.btnStop.setVisible(True)
        self._historyPanel.setEnabled(False)
        self._contextPanel.cbBots.setEnabled(False)
        self._contextPanel.setFocus()

        model.queryAsync(params)

        if isNewConversation and not ApplicationBase.instance().testing and titleSeed:
            self._generateChatTitle(
                self._historyPanel.currentHistory().historyId, titleSeed)

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
                description = self.tr("{} run `{}`").format(
                    self._getToolIcon(tool.tool_type), toolName)
                # TODO: save the tool information in history
                toolMessage = json.dumps(args, ensure_ascii=False)
                model.addHistory(AiRole.Tool, toolMessage, description)
                messages.appendResponse(AiResponse(
                    AiRole.Tool, toolMessage, description))

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
                QTimer.singleShot(0, self._startNextAutoToolIfIdle)

        if not self._disableAutoScroll:
            sb = messages.verticalScrollBar()
            self._adjustingSccrollbar = True
            sb.setValue(sb.maximum())
            self._adjustingSccrollbar = False

    def _onResponseFinish(self):
        model = self.currentChatModel()
        self._saveChatHistory(model)
        self._updateStatus()

    def _saveChatHistory(self, model: AiModelBase):
        chatHistory = self._historyPanel.updateCurrentHistory(model)
        if chatHistory:
            # Save to settings
            settings = ApplicationBase.instance().settings()
            settings.saveChatHistory(
                chatHistory.historyId, chatHistory.toDict())

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
        toolDesc = self.tr("{} `{}` output").format(prefix, tool_name)
        model.addHistory(AiRole.Tool, output, description=toolDesc)
        resp = AiResponse(AiRole.Tool, output, description=toolDesc)
        self._doMessageReady(model, resp, collapsed=True)

        if source == "auto" and group_id is not None and group_id in self._autoToolGroups:
            group = self._autoToolGroups[group_id]
            outputs: list = group.get("outputs", [])
            outputs.append(
                f"[{tool_name}]\n{output}" if output else f"[{tool_name}] (no output)")
            group["outputs"] = outputs

            remaining = int(group.get("remaining", 0)) - 1
            group["remaining"] = remaining

            if remaining <= 0:
                del self._autoToolGroups[group_id]
            else:
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

        toolMessage = json.dumps(params or {}, ensure_ascii=False)
        description = self.tr("{} run `{}`").format(
            self._getToolIcon(ToolType.READ_ONLY), tool_name)
        model = self.currentChatModel()
        model.addHistory(AiRole.Tool, toolMessage, description=description)
        self._chatBot.appendResponse(AiResponse(
            AiRole.Tool, toolMessage,
            description=description),
            collapsed=True)
        started = self._agentExecutor.executeAsync(tool_name, params or {})
        if not started:
            # Fall back to a synthetic failure result and keep draining.
            self._pendingAgentTool = None
            self._pendingToolSource = None
            self._pendingAutoGroupId = None
            self._onAgentToolFinished(AgentToolResult(
                tool_name, False, self.tr("Failed to start tool execution.")))

    def _onServiceUnavailable(self):
        messages: AiChatbot = self._chatBot
        messages.appendServiceUnavailable()
        self._updateStatus()

    def _onNetworkError(self, errorMsg: str):
        messages: AiChatbot = self._chatBot
        messages.appendServiceUnavailable(errorMsg)
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
        self._setEmbeddedRecentListVisible(True)

    def onNewChatRequested(self):
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
        self._setEmbeddedRecentListVisible(True)

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

        self._setEmbeddedRecentListVisible(
            currentHistory and not currentHistory.messages)

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
        self._setEmbeddedRecentListVisible(False)

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
            description = msg.get('description', None)

            model.addHistory(role, content, description=description)
            if addToChatBot:
                response = AiResponse(role, content, description=description)
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

    def _setEmbeddedRecentListVisible(self, visible: bool):
        if not self._embedded:
            return

        if visible:
            visible = self._historyPanel.historyModel().rowCount() > 0
        self._historyPanel.setVisible(visible)

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
        self.chatTitleReady.emit()

    def onOpenSettings(self):
        settings = ApplicationBase.instance().settings()
        dlg = Preferences(settings)
        dlg.ui.tabWidget.setCurrentWidget(dlg.ui.tabLLM)
        dlg.exec()

    @staticmethod
    def _getToolIcon(toolType: int) -> str:
        """Get emoji icon based on tool type"""
        if toolType == ToolType.READ_ONLY:
            return "🔍"
        elif toolType == ToolType.WRITE:
            return "✏️"
        else:  # DANGEROUS
            return "⚠️"

    @property
    def contextPanel(self) -> AiChatContextPanel:
        return self._contextPanel
