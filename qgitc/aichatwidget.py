# -*- coding: utf-8 -*-

import json
import os
import typing
from typing import Any, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import QEvent, QEventLoop, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollBar,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from qgitc.agenttoolexecutor import AgentToolExecutor, AgentToolResult
from qgitc.agenttools import AgentTool, AgentToolRegistry, ToolType, parseToolArguments
from qgitc.aichatbot import AiChatbot
from qgitc.aichatcontextpanel import AiChatContextPanel
from qgitc.aichatcontextprovider import AiChatContextProvider
from qgitc.aichathistory import AiChatHistory
from qgitc.aichathistorypanel import AiChatHistoryPanel
from qgitc.aichattitlegenerator import AiChatTitleGenerator
from qgitc.aitoolconfirmation import ConfirmationStatus
from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.common import Commit, commitRepoDir, fullRepoDir, logger, toSubmodulePath
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
from qgitc.models.prompts import (
    AGENT_SYS_PROMPT,
    CODE_REVIEW_PROMPT,
    CODE_REVIEW_SYS_PROMPT,
    RESOLVE_PROMPT,
    RESOLVE_SYS_PROMPT,
)
from qgitc.preferences import Preferences
from qgitc.submoduleexecutor import SubmoduleExecutor


class DiffAvailableEvent(QEvent):

    Type = QEvent.registerEventType()

    def __init__(self, diff: str):
        super().__init__(QEvent.Type(DiffAvailableEvent.Type))
        self.diff = diff


class CodeReviewSceneEvent(QEvent):

    Type = QEvent.registerEventType()

    def __init__(self, scene_line: str):
        super().__init__(QEvent.Type(CodeReviewSceneEvent.Type))
        self.scene_line = scene_line


class AiChatWidget(QWidget):

    initialized = Signal()
    chatTitleReady = Signal()
    modelStateChanged = Signal(bool)

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
        self._pendingToolCallId: Optional[str] = None

        # Auto-run queue for READ_ONLY tools.
        # Each item: (tool_name, params, group_id, tool_call_id)
        self._autoToolQueue: List[Tuple[str, dict, int, Optional[str]]] = []
        # group_id -> {remaining:int, outputs:[str], auto_continue:bool}
        self._autoToolGroups: Dict[int, Dict[str, object]] = {}
        self._nextAutoGroupId: int = 1
        self._pendingToolSource: Optional[str] = None  # 'auto' | 'approved'
        self._pendingAutoGroupId: Optional[int] = None

        # Track OpenAI tool_call_id values that have been requested by the
        # assistant but do not yet have corresponding tool *results*.
        # We must NOT call `_continueAgentConversation` until this is empty.
        self._awaitingToolResults: set[str] = set()

        # tool_call_id -> metadata used for persistence/cancellation.
        # Populated when tool calls are first received and when history is restored.
        self._toolCallMeta: Dict[str, Dict[str, object]] = {}

        # Tool_call_ids that have been intentionally cancelled/ignored.
        # If a tool finishes later (because we cannot truly cancel the subprocess),
        # we will drop the result to avoid duplicate tool outputs.
        self._ignoredToolCallIds: set[str] = set()

        # Code review diff collection (staged/local changes)
        self._codeReviewExecutor: Optional[SubmoduleExecutor] = None
        self._codeReviewDiffs: List[str] = []
        self._extraContext: str = None

        # allow auto-run WRITE tools without user confirmation.
        self._allowWriteTools: bool = False

        self._isInitialized = False
        QTimer.singleShot(100, self._onDelayInit)

    def _setGenerating(self, generating: bool):
        # we should connect model, but we have many models
        self.modelStateChanged.emit(generating)

    def _markToolResultComplete(self, tool_call_id: Optional[str]):
        if tool_call_id:
            self._awaitingToolResults.discard(tool_call_id)
            self._toolCallMeta.pop(tool_call_id, None)

    def event(self, event: QEvent):
        if event.type() == DiffAvailableEvent.Type:
            if event.diff:
                self._codeReviewDiffs.append(event.diff)
            return True
        if event.type() == CodeReviewSceneEvent.Type:
            if event.scene_line:
                if not self._extraContext:
                    self._extraContext = event.scene_line
                else:
                    self._extraContext += "\n" + event.scene_line
            return True
        return super().event(event)

    def hasPendingToolConfirmation(self) -> bool:
        """True if the chat is waiting for a tool confirmation action."""
        return bool(self._awaitingToolResults)

    def isGenerating(self) -> bool:
        """True if the current model is actively generating a response."""
        model = self.currentChatModel()
        return model is not None and model.isRunning()

    def isHistoryReady(self) -> bool:
        """True once history has been loaded and the widget is initialized."""
        return bool(self._isInitialized)

    def isBusyForCodeReview(self) -> bool:
        """True if starting a dock-based code review would be disruptive."""
        if self.isGenerating():
            return True
        for id in self._awaitingToolResults:
            meta = self._toolCallMeta.get(id)
            if meta and meta.get("tool_type") == ToolType.READ_ONLY:
                return True
        return False

    def _setupHistoryPanel(self):
        store = ApplicationBase.instance().aiChatHistoryStore()
        self._historyPanel = AiChatHistoryPanel(store, self)
        self._historyPanel.requestNewChat.connect(self.onNewChatRequested)
        self._historyPanel.historySelectionChanged.connect(
            self._onHistorySelectionChanged)
        store.historyRemoved.connect(self._onHistoryRemoved)

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

    def setEmbeddedOuterMargins(self, left: int, top: int, right: int, bottom: int):
        """Set the outer layout margins for embedded (dock) mode.

        This is used by dock widgets to avoid double-padding between the dock
        content and the main window while still keeping a 4px margin against
        the window border.
        """
        if not self._embedded:
            return

        layout = self.layout()
        if not layout:
            return

        l = max(0, int(left))
        t = max(0, int(top))
        r = max(0, int(right))
        b = max(0, int(bottom))
        layout.setContentsMargins(l, t, r, b)

    def setContextProvider(self, provider: AiChatContextProvider):
        self._contextPanel.setContextProvider(provider)

    def contextProvider(self) -> AiChatContextProvider:
        return self._contextPanel.contextProvider()

    def _setupModels(self):
        aiModels: List[AiModelBase] = [
            model(parent=self) for model in AiModelProvider.models()]
        defaultModelKey = ApplicationBase.instance().settings().defaultLlmModel()
        currentModelIndex = -1

        self._contextPanel.cbBots.blockSignals(True)

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

        self._contextPanel.cbBots.blockSignals(False)
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

        if self._codeReviewExecutor:
            self._codeReviewExecutor.cancel()
            self._codeReviewExecutor = None
            self._codeReviewDiffs.clear()
        self._extraContext = None

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

        # If the user types a new message while there are pending tool confirmations,
        # treat them as rejected to keep the conversation history consistent.
        # (Otherwise, switching chats / continuing can lose the confirmation UI and
        # later requests may lack required tool results.)
        if self.hasPendingToolConfirmation():
            if not self._autoRejectPendingConfirmationsForNewUserMessage():
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

    def _continueAgentConversation(self, delayMs: int = 0, retries: int = 20):
        """Continue an Agent-mode conversation after tool execution.

        This sends a new LLM request that includes the assistant tool call(s) and
        the tool result message(s) (with matching tool_call_id) without injecting
        a synthetic user follow-up.
        """
        model = self.currentChatModel()
        if model is None:
            return

        # Never continue while any tool_call_id is still awaiting results.
        if self._awaitingToolResults:
            return

        # Wait until the model has finished recording the assistant tool_calls
        # message; otherwise sending tool messages with tool_call_id can 400.
        if model.isRunning():
            if retries <= 0:
                return
            QTimer.singleShot(max(10, delayMs),
                              lambda: self._continueAgentConversation(delayMs, retries - 1))
            return

        def hasToolCallId(tcid: str) -> bool:
            if not tcid:
                return True
            for h in model.history:
                if h.role != AiRole.Assistant or not h.toolCalls:
                    continue
                if isinstance(h.toolCalls, list):
                    for tc in h.toolCalls:
                        if isinstance(tc, dict) and tc.get("id") == tcid:
                            return True
            return False

        # If we have a pending tool_call_id, ensure it exists in history.
        if self._pendingToolCallId and not hasToolCallId(self._pendingToolCallId):
            if retries <= 0:
                return
            QTimer.singleShot(max(10, delayMs),
                              lambda: self._continueAgentConversation(delayMs, retries - 1))
            return

        params = AiParameters()
        params.prompt = ""
        params.temperature = 0.1
        params.chat_mode = AiChatMode.Agent
        params.model = self._contextPanel.currentModelId()
        params.tools = AgentToolRegistry.openai_tools()
        params.tool_choice = "auto"
        params.continue_only = True

        self._contextPanel.btnSend.setVisible(False)
        self._contextPanel.btnStop.setVisible(True)
        self._historyPanel.setEnabled(False)
        self._contextPanel.cbBots.setEnabled(False)
        self._contextPanel.setFocus()

        model.queryAsync(params)
        self._setGenerating(True)
        self._updateChatHistoryModel(model)

    def _doRequest(self, prompt: str, chatMode: AiChatMode, sysPrompt: str = None, collapsed=False):
        settings = ApplicationBase.instance().settings()
        params = AiParameters()
        params.prompt = prompt
        params.sys_prompt = sysPrompt
        params.stream = True
        params.temperature = settings.llmTemperature()
        params.chat_mode = chatMode
        params.model = self._contextPanel.currentModelId()

        self._disableAutoScroll = False

        model = self.currentChatModel()
        isNewConversation = not model.history

        if model.isLocal():
            params.max_tokens = settings.llmMaxTokens()

        self._setEmbeddedRecentListVisible(False)

        # Keep title generation based on the user's original prompt (no injected context).
        titleSeed = (params.sys_prompt + "\n" +
                     prompt) if params.sys_prompt else prompt

        extraContext = self._extraContext

        if chatMode == AiChatMode.Agent:
            params.tools = AgentToolRegistry.openai_tools()
            params.tool_choice = "auto"

            # Don't add system prompt if there is already one
            if not sysPrompt and (len(model.history) == 0 or not collapsed):
                provider = self.contextProvider()
                overridePrompt = provider.agentSystemPrompt() if provider is not None else None
                params.sys_prompt = overridePrompt or AGENT_SYS_PROMPT
        elif chatMode == AiChatMode.CodeReview:
            # Code review can also use tools to fetch missing context.
            # (Models that don't support tool calls will simply ignore them.)
            params.tools = AgentToolRegistry.openai_tools()
            params.tool_choice = "auto"
            params.sys_prompt = sysPrompt or CODE_REVIEW_SYS_PROMPT
            params.prompt = CODE_REVIEW_PROMPT.format(
                diff=params.prompt,
                language=ApplicationBase.instance().uiLanguage())

        provider = self.contextProvider()
        if not collapsed:
            selectedIds = self._contextPanel.selectedContextIds() if provider is not None else []
            contextText = provider.buildContextText(
                selectedIds) if provider is not None else ""

            if extraContext:
                merged = (contextText or "").strip()
                if merged:
                    merged += "\n\n" + extraContext
                else:
                    merged = extraContext
                contextText = merged

            if contextText:
                params.prompt = f"<context>\n{contextText.rstrip()}\n</context>\n\n" + \
                    params.prompt

        if params.sys_prompt:
            self._doMessageReady(model, AiResponse(
                AiRole.System, params.sys_prompt), True)

        self._doMessageReady(model, AiResponse(
            AiRole.User, params.prompt), collapsed)

        self._contextPanel.btnSend.setVisible(False)
        self._contextPanel.btnStop.setVisible(True)
        self._historyPanel.setEnabled(False)
        self._contextPanel.cbBots.setEnabled(False)
        self._contextPanel.setFocus()

        model.queryAsync(params)
        self._setGenerating(True)

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
            # Track tool_call_id values so we only continue when *all* results exist.
            for tc in response.tool_calls:
                tcid = (tc or {}).get("id")
                if tcid:
                    self._awaitingToolResults.add(tcid)

                # Cache metadata for later cancellation/restore logic.
                func = (tc or {}).get("function") or {}
                toolName = func.get("name")
                args = parseToolArguments(func.get("arguments"))
                tool = AgentToolRegistry.tool_by_name(
                    toolName) if toolName else None
                toolType = tool.tool_type if tool else ToolType.WRITE
                toolDesc = tool.description if tool else self.tr(
                    "Unknown tool requested by model")
                if tcid:
                    self._toolCallMeta[tcid] = {
                        "tool_name": toolName or "",
                        "params": args or {},
                        "tool_type": toolType,
                        "tool_desc": toolDesc,
                    }

            autoGroupId: Optional[int] = None
            autoToolsCount = 0
            hasConfirmations = False

            for tc in response.tool_calls:
                func = (tc or {}).get("function") or {}
                toolName = func.get("name")
                args = parseToolArguments(func.get("arguments"))
                toolCallId = (tc or {}).get("id")
                tool = AgentToolRegistry.tool_by_name(
                    toolName) if toolName else None

                # Auto-run only READ_ONLY tools by default. For certain sync helper
                # flows we optionally auto-run *WRITE* tools, but never DANGEROUS.
                if toolName and tool and (
                    tool.tool_type == ToolType.READ_ONLY or (
                        self._allowWriteTools and tool.tool_type == ToolType.WRITE
                    )
                ):
                    if autoGroupId is None:
                        autoGroupId = self._nextAutoGroupId
                        self._nextAutoGroupId += 1
                    self._autoToolQueue.append(
                        (toolName, args or {}, autoGroupId, toolCallId))
                    autoToolsCount += 1
                    continue

                # Anything else requires explicit confirmation.
                uiResponse = self._makeUiToolCallResponse(tool, args)
                messages.appendResponse(uiResponse)

                if toolName and tool:
                    hasConfirmations = True
                    toolDesc = tool.description
                    if isinstance(args, dict):
                        expl = args.get("explanation", "").strip()
                        if expl:
                            toolDesc = expl
                    messages.insertToolConfirmation(
                        toolName=toolName,
                        params=args,
                        toolDesc=toolDesc,
                        toolType=tool.tool_type,
                        toolCallId=toolCallId,
                    )
                elif toolName:
                    hasConfirmations = True
                    messages.insertToolConfirmation(
                        toolName=toolName,
                        params=args,
                        toolDesc=self.tr("Unknown tool requested by model"),
                        toolCallId=toolCallId,
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

    @typing.overload
    def _makeUiToolCallResponse(
        self, tool: AgentTool, args: Union[str, dict]): ...

    @typing.overload
    def _makeUiToolCallResponse(
        self, toolName: str, args: Union[str, dict]): ...

    def _makeUiToolCallResponse(self, *args):
        if isinstance(args[0], str):
            tool = AgentToolRegistry.tool_by_name(args[0])
        else:
            tool = args[0]

        icon = self._getToolIcon(tool.tool_type)
        title = self.tr("{} run `{}`").format(icon, tool.name)

        if isinstance(args[1], str):
            body = args[1]
        else:
            body = json.dumps(args[1], ensure_ascii=False)
        return AiResponse(AiRole.Tool, body, title)

    def _onResponseFinish(self):
        model = self.currentChatModel()
        self._saveChatHistory(model)
        self._updateStatus()

    def _saveChatHistory(self, model: AiModelBase):
        chatHistory = self._historyPanel.currentHistory()
        if not chatHistory:
            return

        store = ApplicationBase.instance().aiChatHistoryStore()
        updated = store.updateFromModel(chatHistory.historyId, model)
        if updated:
            # Keep selection stable after potential row moves.
            self._historyPanel.setCurrentHistory(updated.historyId)

    def _updateStatus(self):
        self._contextPanel.btnSend.setVisible(True)
        self._contextPanel.btnStop.setVisible(False)
        self._historyPanel.setEnabled(True)
        self._contextPanel.cbBots.setEnabled(True)
        self._contextPanel.setFocus()
        self._setGenerating(False)

    def _onToolApproved(self, tool_name: str, params: dict, tool_call_id: str):
        # Prevent overlapping executions.
        if self._pendingAgentTool:
            self._doMessageReady(self.currentChatModel(), AiResponse(
                AiRole.System, self.tr("A tool is already running.")))
            return

        self._pendingAgentTool = tool_name
        self._pendingToolSource = "approved"
        self._pendingAutoGroupId = None
        self._pendingToolCallId = tool_call_id

        started = self._agentExecutor.executeAsync(tool_name, params or {})
        if not started:
            # Produce a correlated tool result so the conversation can continue.
            self._onAgentToolFinished(AgentToolResult(
                tool_name, False, self.tr("Failed to start tool execution.")))

    def _onToolRejected(self, tool_name: str, tool_call_id: str):
        # Keep it simple: just record and continue.
        model = self.currentChatModel()

        # If the assistant previously requested a tool via tool_calls, OpenAI-style
        # chat requires that each tool_call_id gets a corresponding tool message.
        if tool_call_id:
            description = self.tr("✗ `{}` rejected").format(tool_name)
            model.addHistory(AiRole.Tool, "Rejected by user",
                             description=description,
                             toolCalls={"tool_call_id": tool_call_id})
            msg = self.tr("User rejected")
            self._doMessageReady(model, AiResponse(
                AiRole.Tool, msg, description=description))
            self._markToolResultComplete(tool_call_id)
        # Only continue when all tool_call_id results are present.
        if not self._awaitingToolResults:
            self._continueAgentConversation(delayMs=0)

    def _autoRejectPendingConfirmationsForNewUserMessage(self) -> bool:
        """Auto-reject pending confirmations before sending a new user message.

        Returns False if we should block sending (e.g. because there are still
        pending READ_ONLY tool results we cannot reject).
        """
        model = self.currentChatModel()
        if model is None:
            return True

        pendingIds = set(self._awaitingToolResults)
        if not pendingIds:
            return True

        # Resolve all pending tool_call_ids so the next request is always valid.
        # - WRITE/DANGEROUS: reject
        # - READ_ONLY: cancel/ignore
        for tcid in list(pendingIds):
            info = self._toolCallMeta.get(tcid, {})
            toolType = info.get("tool_type", ToolType.WRITE)
            toolName = info.get("tool_name", "")

            if toolType == ToolType.READ_ONLY:
                desc = self.tr("✗ `{}` cancelled").format(
                    toolName or self.tr("tool"))
                model.addHistory(
                    AiRole.Tool,
                    "Cancelled by user",
                    description=desc,
                    toolCalls={"tool_call_id": tcid},
                )
                self._doMessageReady(
                    model,
                    AiResponse(AiRole.Tool, self.tr(
                        "Cancelled"), description=desc),
                    collapsed=True,
                )
                self._ignoredToolCallIds.add(tcid)
                self._markToolResultComplete(tcid)
                continue

            # Anything else is treated as requiring confirmation.
            self._chatBot.setToolConfirmationStatus(
                tcid, ConfirmationStatus.REJECTED)
            description = self.tr("✗ `{}` rejected").format(toolName)
            model.addHistory(
                AiRole.Tool,
                "Rejected by user",
                description=description,
                toolCalls={"tool_call_id": tcid},
            )
            self._doMessageReady(
                model,
                AiResponse(AiRole.Tool, self.tr("User rejected"),
                           description=description),
                collapsed=True,
            )
            self._markToolResultComplete(tcid)

        # Stop draining auto tools from the previous prompt.
        self._autoToolQueue.clear()
        self._autoToolGroups.clear()

        # Allow sending immediately.
        self._awaitingToolResults.clear()
        return True

    def _onAgentToolFinished(self, result: AgentToolResult):
        model = self.currentChatModel()
        tool_name = result.tool_name
        ok = result.ok
        output = result.output or ""

        source = self._pendingToolSource
        group_id = self._pendingAutoGroupId
        tool_call_id = self._pendingToolCallId

        self._pendingAgentTool = None
        self._pendingToolSource = None
        self._pendingAutoGroupId = None
        self._pendingToolCallId = None

        # If this tool_call_id was cancelled/ignored, drop late results to avoid
        # duplicate tool outputs and unexpected auto-continues.
        if tool_call_id and tool_call_id in self._ignoredToolCallIds:
            self._ignoredToolCallIds.discard(tool_call_id)
            self._markToolResultComplete(tool_call_id)
            return

        prefix = "✓" if ok else "✗"
        toolDesc = self.tr("{} `{}` output").format(prefix, tool_name)
        toolCalls = {"tool_call_id": tool_call_id} if tool_call_id else None
        model.addHistory(AiRole.Tool, output,
                         description=toolDesc, toolCalls=toolCalls)
        resp = AiResponse(AiRole.Tool, output, description=toolDesc)
        self._doMessageReady(model, resp, collapsed=True)

        # Mark this tool_call_id as having a corresponding tool result.
        self._markToolResultComplete(tool_call_id)

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
                del self._autoToolGroups[group_id]
                # If this batch had pending confirmations, do not continue yet.
                if not auto_continue:
                    return
            else:
                # Continue draining the queue.
                self._startNextAutoToolIfIdle()
                return

        # Continue the agent conversation only when all tool_call_id results exist.
        if self._awaitingToolResults:
            return

        self._continueAgentConversation(delayMs=0)

    def _startNextAutoToolIfIdle(self):
        if self._pendingAgentTool:
            return
        if not self._autoToolQueue:
            return

        tool_name, params, group_id, tool_call_id = self._autoToolQueue.pop(0)
        self._pendingAgentTool = tool_name
        self._pendingToolSource = "auto"
        self._pendingAutoGroupId = group_id
        self._pendingToolCallId = tool_call_id

        uiResponse = self._makeUiToolCallResponse(tool_name, params or {})
        self._chatBot.appendResponse(uiResponse, collapsed=True)
        started = self._agentExecutor.executeAsync(tool_name, params or {})
        if not started:
            # Fall back to a synthetic failure result and keep draining.
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

    @staticmethod
    def _extractDiffFilePaths(diff: str) -> List[str]:
        """Best-effort extraction of changed file paths from a unified diff."""
        if not diff:
            return []
        files: List[str] = []
        seen = set()
        for line in diff.splitlines():
            if not line.startswith("diff --git "):
                continue
            # Format: diff --git a/path b/path
            parts = line.split()
            if len(parts) < 4:
                continue
            b_path = parts[3]
            if b_path.startswith("b/"):
                b_path = b_path[2:]
            if b_path and b_path not in seen:
                seen.add(b_path)
                files.append(b_path)
        return files

    def codeReview(self, commit: Commit):
        repoDir = commitRepoDir(commit)
        commitDiffData: bytes = Git.commitRawDiff(commit.sha1, repoDir=repoDir)
        if not commitDiffData:
            return

        commitDiff = commitDiffData.decode("utf-8", errors="replace")

        subDiffs: List[Tuple[str, str, str]] = []  # (repoLabel, sha1, diff)
        for subCommit in commit.subCommits:
            subRepoDir = commitRepoDir(subCommit)
            subData = Git.commitRawDiff(subCommit.sha1, repoDir=subRepoDir)
            if not subData:
                continue
            subRepoLabel = subCommit.repoDir or "."
            subDiffs.append((subRepoLabel, subCommit.sha1,
                            subData.decode("utf-8", errors="replace")))
        parts = [commitDiff]
        parts.extend([d for _, _, d in subDiffs])
        diff = "\n".join([p for p in parts if p])

        sha1 = commit.sha1
        subject = Git.commitSubject(sha1, repoDir=repoDir).decode(
            "utf-8", errors="replace")

        sceneLines = [
            "type: commit  ",
            f"subject: {subject.strip()}  ",
        ]

        def _appendRepoFileSummary(repoLabel: str, sha1: str, repoDiff: str):
            files = self._extractDiffFilePaths(repoDiff)
            if not files:
                return

            sceneLines.extend([
                "",
                "---",
                f"repo: {repoLabel}  ",
                f"sha1: {sha1}  ",
                f"files_changed:\n{self._makeFileList(files)}",
            ])

        _appendRepoFileSummary((commit.repoDir or ".").replace(
            "\\", "/"), commit.sha1, commitDiff)
        for subRepo, subSha1, subDiff in subDiffs:
            _appendRepoFileSummary(
                subRepo.replace("\\", "/"), subSha1, subDiff)

        scene = "\n".join(sceneLines)

        self._waitForInitialization()
        # create a new conversation if current one is not empty
        curHistory = self._historyPanel.currentHistory()
        if not curHistory or curHistory.messages:
            self._createNewConversation()
        self._extraContext = scene
        self._doRequest(diff, AiChatMode.CodeReview)

    def _makeFileList(self, files: List[str]) -> str:
        l = []
        for file in files:
            file = file.replace('\\', '/')
            l.append(f"- {file}")
        return "\n".join(l)

    def codeReviewForDiff(self, diff: str):
        self._waitForInitialization()

        curHistory = self._historyPanel.currentHistory()
        if not curHistory or curHistory.messages:
            self._createNewConversation()
        self._doRequest(diff, AiChatMode.CodeReview)

    def codeReviewForStagedFiles(self, submodules):
        """Start a code review for staged/local changes across submodules."""
        self._ensureCodeReviewExecutor()
        self._codeReviewDiffs.clear()
        self._extraContext = "type: staged changes (index)\n"
        self._codeReviewExecutor.submit(submodules, self._fetchStagedDiff)

    def _ensureCodeReviewExecutor(self):
        if self._codeReviewExecutor is None:
            self._codeReviewExecutor = SubmoduleExecutor(self)
            self._codeReviewExecutor.finished.connect(
                self._onCodeReviewDiffFetchFinished)

    def _onCodeReviewDiffFetchFinished(self):
        if self._codeReviewDiffs:
            diff = "\n".join(self._codeReviewDiffs)
            self.codeReviewForDiff(diff)

    def _fetchStagedDiff(self, submodule: str, files, cancelEvent: CancelEvent):
        repoDir = fullRepoDir(submodule)
        repoFiles = [toSubmodulePath(submodule, file) for file in files]

        # Send human-readable, repo-disambiguating scene metadata to the UI thread.
        repoLabel = (submodule or ".").replace("\\", "/")
        scene = "\n".join([
            "",
            "---",
            f"repo: {repoLabel}  ",
            f"files_changed:\n{self._makeFileList(repoFiles)}",
        ])
        ApplicationBase.instance().postEvent(self, CodeReviewSceneEvent(scene))
        data: bytes = Git.commitRawDiff(
            Git.LCC_SHA1, repoFiles, repoDir=repoDir)
        if not data:
            logger.warning("AiChat: no diff for %s", repoDir)
            return

        if cancelEvent.isSet():
            return

        diff = data.decode("utf-8", errors="replace")
        ApplicationBase.instance().postEvent(self, DiffAvailableEvent(diff))

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
        # Load chat histories once via the shared store.
        store = ApplicationBase.instance().aiChatHistoryStore()
        curHistory = self._historyPanel.currentHistory()
        store.ensureLoaded()

        # Preserve any unsaved in-memory conversation created before load.
        if curHistory and not store.get(curHistory.historyId):
            self._historyPanel.blockSignals(True)
            self._historyPanel.insertHistoryAtTop(curHistory)
            self._historyPanel.blockSignals(False)

        self._setupModels()
        self._isInitialized = True
        self.initialized.emit()

        # If there is no active empty conversation, create one.
        if not (curHistory and not curHistory.messages):
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

        def isEmptyHistory(h: AiChatHistory) -> bool:
            return h is not None and not h.messages

        def tryActivateHistory(h: AiChatHistory) -> bool:
            self._historyPanel.setCurrentHistory(h.historyId)
            cur = self._historyPanel.currentHistory()
            return cur is not None and cur.historyId == h.historyId

        # If we already have an empty conversation, don't create another one.
        # Just activate/select it and clear the UI.
        historyModel = self._historyPanel.historyModel()
        if historyModel.rowCount() > 0:
            history = historyModel.getHistory(0)
            if isEmptyHistory(history):
                if tryActivateHistory(history):
                    self._clearCurrentChat()
                    self._setEmbeddedRecentListVisible(True)
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
        # If the removed history was currently selected, create a new conversation
        currentHistory = self._historyPanel.currentHistory()
        if not currentHistory or currentHistory.historyId == historyId:
            self._createNewConversation()

        currentHistory = self._historyPanel.currentHistory()

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

        # Rebuild pending tool_call_id state from history.
        self._awaitingToolResults.clear()
        self._toolCallMeta.clear()

        # Rebuild auto-run queue state from history for pending READ_ONLY tool calls.
        self._autoToolQueue.clear()
        self._autoToolGroups.clear()
        self._nextAutoGroupId = 1

        i = 0
        while i < len(messages):
            msg = messages[i]
            role = AiRole.fromString(msg.get('role', 'user'))
            content = msg.get('content', '')
            description = msg.get('description', None)
            toolCalls = msg.get('tool_calls', None)

            model.addHistory(
                role, content, description=description, toolCalls=toolCalls)
            # Don't add tool calls to UI (both for assistant and tool roles)
            if addToChatBot and not toolCalls:
                response = AiResponse(role, content)
                collapsed = (role == AiRole.Tool) or (role == AiRole.System) or \
                    (role == AiRole.Assistant and toolCalls)
                chatbot.appendResponse(response, collapsed=collapsed)

            if role == AiRole.Assistant and isinstance(toolCalls, list) and toolCalls:
                toolCallResult, hasMoreMessages = self._collectToolCallResult(
                    i + 1, messages)

                for tc in toolCalls:
                    if not isinstance(tc, dict):
                        continue
                    tcid = tc.get("id")
                    if not tcid:
                        logger.warning(
                            "Invalid tool call entry in history: missing id")
                        continue

                    func = (tc.get("function") or {})
                    toolName = func.get("name")
                    responseMsg: Dict[str, Any] = toolCallResult.get(tcid)
                    tool = AgentToolRegistry.tool_by_name(
                        toolName) if toolName else None
                    toolType = tool.tool_type if tool else ToolType.WRITE

                    if addToChatBot:
                        uiResponse = self._makeUiToolCallResponse(
                            toolName, func.get("arguments"))
                        collapsed = bool(
                            responseMsg) or toolType == ToolType.READ_ONLY
                        chatbot.appendResponse(uiResponse, collapsed)

                    # Already have result
                    if responseMsg:
                        if addToChatBot:
                            toolContent = responseMsg.get("content", "")
                            toolDesc = responseMsg.get("description", "")
                            response = AiResponse(
                                AiRole.Tool, toolContent, toolDesc)
                            chatbot.appendResponse(response, collapsed=True)
                        continue

                    args = parseToolArguments(func.get("arguments"))

                    # No result found - decide whether to cancel or restore confirmation
                    # If there are more messages after this tool call block, cancel it
                    # (the conversation moved on without executing this tool)
                    if hasMoreMessages or toolType == ToolType.READ_ONLY:
                        cancelDesc = self.tr(
                            "✗ `{}` cancelled").format(toolName)
                        model.addHistory(
                            AiRole.Tool,
                            "Cancelled",
                            description=cancelDesc,
                            toolCalls={"tool_call_id": tcid},
                        )
                        if addToChatBot:
                            response = AiResponse(
                                AiRole.Tool,
                                self.tr("Cancelled"),
                                description=cancelDesc
                            )
                            chatbot.appendResponse(response, collapsed=True)
                        continue

                    # For WRITE/DANGEROUS tools at end of history: restore confirmation UI
                    self._awaitingToolResults.add(tcid)
                    toolDesc = tool.description if tool else self.tr(
                        "Unknown tool requested by model")
                    self._toolCallMeta[tcid] = {
                        "tool_name": toolName or "",
                        "params": args or {},
                        "tool_type": toolType,
                        "tool_desc": toolDesc,
                    }

                    if addToChatBot:
                        if isinstance(args, dict):
                            expl = args.get("explanation", "").strip()
                            if expl:
                                toolDesc = expl
                        chatbot.insertToolConfirmation(
                            toolName=toolName or "",
                            params=args or {},
                            toolDesc=toolDesc,
                            toolType=toolType,
                            toolCallId=tcid,
                        )

            i += 1

        if addToChatBot:
            chatbot.setHighlighterEnabled(True)

    def _collectToolCallResult(self, i: int, messages: List[Dict]) -> Tuple[Dict[str, Dict], bool]:
        """Collect pending tool_call_id values from history starting at index i.
        
        Returns:
            Tuple of (callResult dict, hasMoreMessages bool):
            - callResult: Dict mapping tool_call_id to tool result message
            - hasMoreMessages: True if there are non-tool messages after tool results
        """
        callResult = {}
        while i < len(messages):
            msg = messages[i]
            role = AiRole.fromString(msg.get('role', 'user'))
            if role != AiRole.Tool:
                # Found a non-tool message, so there are more messages after tools
                return callResult, True
            toolCalls = msg.get('tool_calls', None)
            if isinstance(toolCalls, dict):
                tcid = toolCalls.get("tool_call_id")
                if tcid:
                    callResult[tcid] = msg
            i += 1
        # Reached end of messages - no more messages after tool results
        return callResult, False

    def _clearCurrentChat(self):
        """Clear the current chat display and model history"""
        model = self.currentChatModel()
        if model:
            model.clear()
        self._awaitingToolResults.clear()
        self._toolCallMeta.clear()
        self._ignoredToolCallIds.clear()
        self._autoToolQueue.clear()
        self._autoToolGroups.clear()
        self._nextAutoGroupId = 1
        self._codeReviewDiffs.clear()
        self._extraContext = None
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

    def resolveConflictSync(self, repoDir: str, sha1: str, path: str, conflictText: str, extraContext: str = None) -> Tuple[bool, Optional[str]]:
        """Resolve a conflicted file given an excerpt of the working tree file.

        Returns (ok, reason). On success, ok=True and reason=None.
        """
        self._waitForInitialization()
        model = self.currentChatModel()
        if not model:
            return False, "no_model"

        # Always start a new conversation for conflict resolution.
        # To avoid context too long and mixing with previous topics.
        self._createNewConversation()

        context = (
            f"repo_dir: {repoDir}\n"
            f"conflicted_file: {path}\n"
        )

        if sha1:
            context += f"sha1: {sha1}\n"

        self._extraContext = context.rstrip()
        if extraContext:
            self._extraContext += f"\n{extraContext.rstrip()}"

        prompt = RESOLVE_PROMPT.format(
            operation="cherry-pick" if sha1 else "merge",
            conflict=conflictText,
        )

        self._allowWriteTools = True

        loop = QEventLoop()
        done: Dict[str, object] = {"ok": False, "reason": None}

        timer = QTimer()
        timer.setSingleShot(True)
        timer.start(5 * 60 * 1000)

        oldHistoryCount = len(model.history)

        def _lastAssistantTextSince(startIndex: int) -> str:
            # Find the latest assistant message text after startIndex.
            for i in range(len(model.history) - 1, startIndex - 1, -1):
                h = model.history[i]
                if h.role == AiRole.Assistant:
                    if h.message:
                        return h.message
            return ""

        def _finalizeIfIdle():
            # Timeout?
            if timer.remainingTime() <= 0:
                done["ok"] = False
                done["reason"] = "Assistant response timed out"
                model.requestInterruption()
                loop.quit()
                return

            # No new messages yet.
            if len(model.history) == oldHistoryCount:
                return

            # If the assistant explicitly reported failure, honor it.
            response = _lastAssistantTextSince(oldHistoryCount)
            if "QGITC_RESOLVE_FAILED:" in response:
                parts = response.split("QGITC_RESOLVE_FAILED:", 1)
                reason = parts[1].strip() if len(parts) > 1 else ""
                done["ok"] = False
                done["reason"] = reason or "Assistant reported failure"
                loop.quit()
                return

            if "QGITC_RESOLVE_OK" not in response:
                return

            # Verify the working tree file is conflict-marker-free.
            try:
                absPath = os.path.join(repoDir, path)
                with open(absPath, "rb") as f:
                    merged = f.read()
            except Exception as e:
                done["ok"] = False
                done["reason"] = f"read_back_failed: {e}"
                loop.quit()
                return

            if b"<<<<<<<" in merged or b"=======" in merged or b">>>>>>>" in merged:
                done["ok"] = False
                done["reason"] = "conflict_markers_remain"
                loop.quit()
                return

            done["ok"] = True
            done["reason"] = None
            loop.quit()

        def _onNetworkError(errorMsg: str):
            done["ok"] = False
            done["reason"] = errorMsg
            loop.quit()

        timer.timeout.connect(_finalizeIfIdle)

        # Re-check completion whenever the model finishes a generation step or
        # a tool finishes (tools may trigger another continue-only generation).
        model.finished.connect(_finalizeIfIdle)
        model.networkError.connect(_onNetworkError)

        self._doRequest(prompt, AiChatMode.Agent, RESOLVE_SYS_PROMPT)
        loop.exec()

        timer.stop()
        model.finished.disconnect(_finalizeIfIdle)
        model.networkError.disconnect(_onNetworkError)
        self._allowWriteTools = False

        return bool(done.get("ok", False)), done.get("reason")
