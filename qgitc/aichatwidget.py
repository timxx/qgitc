# -*- coding: utf-8 -*-

import json
import os
from typing import Any, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import (
    QEvent,
    QEventLoop,
    QObject,
    QPoint,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QScrollBar,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from qgitc.agent import (
    AgentLoop,
    AiModelBaseAdapter,
    QueryParams,
    SkillRegistry,
    ToolRegistry,
    UiTool,
    UiToolDispatcher,
    create_permission_engine,
    history_dicts_to_messages,
    load_skill_registry,
    messages_to_history_dicts,
    register_builtin_tools,
)
from qgitc.agent.tool import ToolType
from qgitc.agent.types import TextBlock
from qgitc.aichatbot import AiChatbot
from qgitc.aichatcontextpanel import AiChatContextPanel
from qgitc.aichatcontextprovider import AiChatContextProvider
from qgitc.aichathistory import AiChatHistory
from qgitc.aichathistorypanel import AiChatHistoryPanel
from qgitc.aichattitlegenerator import AiChatTitleGenerator
from qgitc.aitoolconfirmation import ConfirmationStatus
from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.coloredicontoolbutton import ColoredIconToolButton
from qgitc.common import (
    Commit,
    commitRepoDir,
    dataDirPath,
    fullRepoDir,
    logger,
    toSubmodulePath,
)
from qgitc.elidedlabel import ElidedLabel
from qgitc.gitutils import Git
from qgitc.llm import (
    AiChatMode,
    AiModelBase,
    AiModelCapabilities,
    AiModelFactory,
    AiParameters,
    AiResponse,
    AiRole,
)
from qgitc.llmprovider import AiModelDescriptor, AiModelProvider
from qgitc.models.prompts import (
    AGENT_SYS_PROMPT,
    CODE_REVIEW_PROMPT,
    CODE_REVIEW_SYS_PROMPT,
    RESOLVE_PROMPT,
    RESOLVE_SYS_PROMPT,
)
from qgitc.preferences import Preferences
from qgitc.resolutionreport import (
    appendResolutionReportEntry,
    buildResolutionReportEntry,
)
from qgitc.submoduleexecutor import SubmoduleExecutor

SKIP_TOOL = "The user chose to skip the tool call, they want to proceed without running it"


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


class ResolveConflictJob(QObject):
    finished = Signal(bool, object)  # ok, reason

    def __init__(
        self,
        widget,
        repoDir,
        sha1,
        path,
        conflictText,
        context=None,
        reportFile=None,
        parent=None,
    ):
        super().__init__(parent or widget)
        self._widget = widget
        self._repoDir = repoDir
        self._sha1 = sha1
        self._path = path
        self._conflictText = conflictText
        self._context = context
        self._reportFile = reportFile

        self._done = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._agentLoop = None

    def start(self):
        w = self._widget
        w._waitForInitialization()

        model = w.currentChatModel()
        if not model:
            self._finish(False, "no_model")
            return

        # Always start a new conversation for conflict resolution.
        w._createNewConversation()

        contextText = (self._context or "").strip() or None
        w._injectedContext = contextText

        prompt = RESOLVE_PROMPT.format(
            operation="cherry-pick" if self._sha1 else "merge",
            conflict=self._conflictText,
        )

        # Build full prompt with context
        fullPrompt = prompt
        if contextText:
            fullPrompt = f"<context>\n{contextText.rstrip()}\n</context>\n\n" + prompt

        # Create own AgentLoop with all-auto permissions
        caps = w._getModelCapabilities(model)
        settings = ApplicationBase.instance().settings()
        adapter = AiModelBaseAdapter(
            model,
            w._contextPanel.currentModelId(),
            max_tokens=(caps.max_output_tokens if model.isLocal() else None),
            temperature=settings.llmTemperature(),
            chat_mode=AiChatMode.Agent,
        )
        toolRegistry = ToolRegistry()
        register_builtin_tools(toolRegistry)
        allAutoEngine = create_permission_engine(3)  # AllAuto
        self._agentLoop = AgentLoop(
            tool_registry=toolRegistry,
            permission_engine=allAutoEngine,
            parent=self,
        )
        params = QueryParams(
            provider=adapter,
            system_prompt=RESOLVE_SYS_PROMPT,
            context_window=caps.context_window,
            max_output_tokens=caps.max_output_tokens,
        )

        # Connect rendering signals to widget
        self._agentLoop.textDelta.connect(w._onAgentTextDelta)
        self._agentLoop.reasoningDelta.connect(w._onAgentReasoningDelta)
        self._agentLoop.toolCallStart.connect(w._onAgentToolCallStart)
        self._agentLoop.toolCallResult.connect(w._onAgentToolCallResult)
        self._agentLoop.agentFinished.connect(self._onAgentFinished)
        self._agentLoop.errorOccurred.connect(self._onError)

        self._timer.timeout.connect(self._onTimeout)
        self._timer.start(5 * 60 * 1000)

        # Display messages in chatbot
        w._chatBot.appendResponse(AiResponse(AiRole.User, fullPrompt))
        w._chatBot.appendResponse(
            AiResponse(AiRole.System, RESOLVE_SYS_PROMPT), True)

        # UI state
        w._contextPanel.btnSend.setVisible(False)
        w._contextPanel.btnStop.setVisible(True)
        w._setGenerating(True)

        self._agentLoop.submit(fullPrompt, params)

    def abort(self):
        if self._agentLoop:
            self._agentLoop.abort()

    def _onAgentFinished(self):
        if self._done:
            return
        self._checkDone()

    def _onError(self, errorMsg):
        self._finish(False, errorMsg)

    def _onTimeout(self):
        if self._agentLoop:
            self._agentLoop.abort()
        self._finish(False, "Assistant response timed out")

    def _checkDone(self):
        if self._done:
            return
        if self._agentLoop is None:
            return

        response = self._lastAssistantText()
        status, detail = self._parseFinalResolveMessage(response)

        if status == "failed":
            self._finish(False, detail or "Assistant reported failure")
            return

        if status != "ok":
            self._finish(False, "No resolve status marker found")
            return

        # Verify file is conflict-marker-free
        try:
            absPath = os.path.join(self._repoDir, self._path)
            with open(absPath, "rb") as f:
                merged = f.read()
        except Exception as e:
            self._finish(False, f"read_back_failed: {e}")
            return

        if b"<<<<<<<" in merged or b"=======" in merged or b">>>>>>>" in merged:
            self._finish(False, "conflict_markers_remain")
            return

        self._finish(True, detail or "Assistant reported success")

    def _lastAssistantText(self):
        if self._agentLoop is None:
            return ""
        from qgitc.agent.types import AssistantMessage as AMsg
        from qgitc.agent.types import TextBlock as TBlk
        for msg in reversed(self._agentLoop.messages()):
            if isinstance(msg, AMsg):
                parts = [b.text for b in msg.content if isinstance(b, TBlk)]
                if parts:
                    return "".join(parts)
        return ""

    @staticmethod
    def _parseFinalResolveMessage(text):
        if not text:
            return None, ""
        pos = text.find("QGITC_RESOLVE_OK")
        if pos != -1:
            detail = text[pos + len("QGITC_RESOLVE_OK"):].lstrip('\n')
            return "ok", detail
        pos = text.find("QGITC_RESOLVE_FAILED")
        if pos != -1:
            detail = text[pos + len("QGITC_RESOLVE_FAILED"):].lstrip('\n')
            return "failed", detail
        return None, ""

    def _finish(self, ok, reason):
        if self._done:
            return
        self._done = True

        if self._reportFile:
            try:
                entry = buildResolutionReportEntry(
                    repoDir=self._repoDir,
                    path=self._path,
                    sha1=self._sha1,
                    operation="cherry-pick" if self._sha1 else "merge",
                    ok=ok,
                    reason=reason,
                )
                appendResolutionReportEntry(self._reportFile, entry)
            except Exception:
                pass

        self._timer.stop()
        if self._agentLoop:
            self._agentLoop.abort()
            self._agentLoop.wait(3000)

        self._widget._updateStatus()
        self.finished.emit(ok, reason)


class AiChatWidget(QWidget):

    initialized = Signal()
    chatTitleReady = Signal()
    modelStateChanged = Signal(bool)

    def __init__(self, parent=None, embedded=False, hideHistoryPanel=False):
        super().__init__(parent)

        self._embedded = embedded
        self._hideHistoryPanel = hideHistoryPanel

        self._conversationHeader = None
        self._btnBackToNewConversation = None
        self._conversationTitleLabel = None
        self._historyPopupMenu = None
        self._historyPopupPanel = None

        if not embedded:
            mainLayout = QHBoxLayout(self)
            mainLayout.setContentsMargins(4, 4, 4, 4)
            mainLayout.setSpacing(4)
            self.splitter = QSplitter(Qt.Horizontal, self)
            mainLayout.addWidget(self.splitter)

        self._setupHistoryPanel()
        self._setupChatPanel()

        self._titleGenerator: AiChatTitleGenerator = None
        self._uiToolDispatcher = UiToolDispatcher(self)
        self._uiToolDispatcher.set_handler(self._executeUiToolHandler)

        settings = ApplicationBase.instance().settings()
        self._permissionEngine = create_permission_engine(
            settings.toolExecutionStrategy())
        settings.toolExecutionStrategyChanged.connect(
            self._onToolExecutionStrategyChanged)

        self._agentLoop = None  # type: Optional[AgentLoop]
        self._toolRegistry = None  # type: Optional[ToolRegistry]
        self._skillRegistry = None  # type: Optional[SkillRegistry]
        self._firstTextDelta = True
        self._firstReasoningDelta = True

        # Code review diff collection (staged/local changes)
        self._codeReviewExecutor: Optional[SubmoduleExecutor] = None
        self._codeReviewDiffs: List[str] = []
        self._injectedContext: str = None
        self._restrictedToolNames: Optional[List[str]] = None

        self._isInitialized = False
        QTimer.singleShot(100, self._onDelayInit)

    def _setGenerating(self, generating: bool):
        # we should connect model, but we have many models
        self.modelStateChanged.emit(generating)

    def event(self, event: QEvent):
        if event.type() == DiffAvailableEvent.Type:
            if event.diff:
                self._codeReviewDiffs.append(event.diff)
            return True
        if event.type() == CodeReviewSceneEvent.Type:
            if event.scene_line:
                if not self._injectedContext:
                    self._injectedContext = event.scene_line
                else:
                    self._injectedContext += "\n" + event.scene_line
            return True
        return super().event(event)

    def isGenerating(self) -> bool:
        """True if the current model is actively generating a response."""
        return self._agentLoop is not None and self._agentLoop.isRunning()

    def isHistoryReady(self) -> bool:
        """True once history has been loaded and the widget is initialized."""
        return bool(self._isInitialized)

    def isBusyForCodeReview(self) -> bool:
        """True if starting a dock-based code review would be disruptive."""
        return self.isGenerating()

    def queryAgent(self, prompt: str, contextText: str = None, sysPrompt: str = None, toolNames: List[str] = None):
        """Send a query to the AI chat in Agent mode.

        This creates a new conversation if the current one is not empty,
        and sends the prompt in Agent mode which enables tool calls.

        Args:
            prompt: The user prompt to send
            contextText: Optional context text to inject into the conversation
            sysPrompt: Optional system prompt to use for this request
            toolNames: Optional list of tool names to restrict to (if None, all tools are available)
        """
        self._waitForInitialization()

        # Create a new conversation if current one is not empty
        curHistory = self._historyPanel.currentHistory()
        if not curHistory or curHistory.messages:
            self._createNewConversation()

        # Set context if provided
        if contextText:
            self._injectedContext = contextText

        # Set tool restrictions if provided
        self._restrictedToolNames = toolNames

        # Send the request in Agent mode via the new architecture
        self._doRequest(prompt, AiChatMode.Agent, sysPrompt=sysPrompt)

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
        if self._hideHistoryPanel:
            self._historyPanel.setVisible(False)

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

            # Embedded mode: conversation header (back + title) shown when a
            # non-empty conversation is active.
            self._conversationHeader = QWidget(self)
            headerLayout = QHBoxLayout(self._conversationHeader)
            headerLayout.setContentsMargins(0, 0, 0, 0)
            headerLayout.setSpacing(0)

            backIcon = QIcon(dataDirPath() + "/icons/arrow-back.svg")
            self._btnBackToNewConversation = ColoredIconToolButton(
                backIcon, QSize(16, 16), self._conversationHeader)
            self._btnBackToNewConversation.setFixedSize(QSize(20, 20))
            self._btnBackToNewConversation.setToolTip(
                self.tr("Go Back"))
            self._btnBackToNewConversation.clicked.connect(
                self.onNewChatRequested)
            headerLayout.addWidget(self._btnBackToNewConversation)

            self._conversationTitleLabel = ElidedLabel(
                self._conversationHeader)
            self._conversationTitleLabel.setClickable(True)
            self._conversationTitleLabel.setToolTip(
                self.tr("Pick Conversation"))
            self._conversationTitleLabel.clicked.connect(
                self._showHistoryPopup)
            headerLayout.addWidget(self._conversationTitleLabel, 1)

            headerLayout.addStretch(0)
            layout.addWidget(self._conversationHeader)
            layout.addSpacing(4)
            self._conversationHeader.setVisible(False)

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

    def _ensureHistoryPopup(self):
        if self._historyPopupMenu is not None:
            return

        store = ApplicationBase.instance().aiChatHistoryStore()

        self._historyPopupMenu = QMenu(self)
        self._historyPopupMenu.setObjectName("AiChatHistoryPopupMenu")
        self._historyPopupMenu.aboutToHide.connect(self._onHistoryPopupClosed)

        action = QWidgetAction(self._historyPopupMenu)
        panel = AiChatHistoryPanel(store, self._historyPopupMenu)
        panel.setCompactMode(False)
        panel.setMaxVisibleRows(8)
        panel.setSelectionMode(QAbstractItemView.SingleSelection)
        panel.requestNewChat.connect(self._onPopupNewChatRequested)
        panel.historyActivated.connect(self._onPopupHistorySelected)
        panel.setMinimumWidth(360)

        action.setDefaultWidget(panel)
        self._historyPopupMenu.addAction(action)
        self._historyPopupPanel = panel

    def _onHistoryPopupClosed(self):
        # Reset filter for next open, but keep whichever history is selected.
        if self._historyPopupPanel is not None:
            self._historyPopupPanel.clearFilter(preserveSelection=True)

    def _showHistoryPopup(self):
        if not self._embedded or self._hideHistoryPanel:
            return

        # Only show when a conversation title header is visible.
        if not self._conversationHeader or not self._conversationHeader.isVisible():
            return

        self._ensureHistoryPopup()

        cur = self._historyPanel.currentHistory()
        if cur is not None:
            self._historyPopupPanel.setCurrentHistory(cur.historyId)

        anchor = self._conversationTitleLabel
        pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        self._historyPopupMenu.popup(pos)

    def _onPopupHistorySelected(self, chatHistory: AiChatHistory):
        if not chatHistory:
            return

        # Activate via the main (embedded) panel so existing logic runs.
        self._historyPanel.setCurrentHistory(chatHistory.historyId)
        if self._historyPopupMenu is not None:
            self._historyPopupMenu.hide()

    def _onPopupNewChatRequested(self):
        self.onNewChatRequested()
        if self._historyPopupMenu is not None:
            self._historyPopupMenu.hide()

    def _updateEmbeddedConversationHeader(self):
        if not self._embedded or self._hideHistoryPanel:
            return
        if not self._conversationHeader:
            return

        isNewConversation = (self._agentLoop is None) or (not self._agentLoop.messages())

        self._conversationHeader.setVisible(not isNewConversation)
        if isNewConversation:
            return

        cur = self._historyPanel.currentHistory()
        title = (cur.title or "").strip() if cur else ""
        display = title if title else self.tr("New Conversation")
        self._conversationTitleLabel.setText(display)

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
        descriptors: List[AiModelDescriptor] = AiModelProvider.models()
        settings = ApplicationBase.instance().settings()
        defaultModelKey = settings.defaultLlmModel()
        currentModelIndex = -1

        self._contextPanel.cbBots.blockSignals(True)
        self._contextPanel.cbBots.clear()

        for i, desc in enumerate(descriptors):
            self._contextPanel.cbBots.addItem(desc.name, desc)
            if desc.modelKey == defaultModelKey:
                currentModelIndex = i

        if currentModelIndex != -1:
            self._contextPanel.cbBots.setCurrentIndex(currentModelIndex)

        self._contextPanel.cbBots.blockSignals(False)

        # Ensure the selected model is instantiated immediately so downstream
        # code always sees a real AiModelBase instance.
        self._ensureCurrentModelInstantiated()
        self._onModelChanged(self._contextPanel.cbBots.currentIndex())

    def _ensureCurrentModelInstantiated(self) -> Optional[AiModelBase]:
        index = self._contextPanel.cbBots.currentIndex()
        return self._ensureModelInstantiatedAt(index)

    def _ensureModelInstantiatedAt(self, index: int) -> Optional[AiModelBase]:
        if index < 0:
            return None

        data = self._contextPanel.cbBots.itemData(index)
        if isinstance(data, AiModelBase):
            return data

        if not isinstance(data, AiModelDescriptor):
            return None

        settings = ApplicationBase.instance().settings()
        modelId = settings.defaultLlmModelId(data.modelKey)
        model = AiModelProvider.createSpecificModel(
            data.modelKey, modelId=modelId, parent=self)

        # Replace descriptor with the live model instance.
        cb = self._contextPanel.cbBots
        cb.setItemData(index, model)

        model.modelsReady.connect(self._onModelsReady)

        return model

    def queryClose(self):
        if self._titleGenerator:
            self._titleGenerator.cancel()

        models: List[AiModelBase] = []
        for i in range(self._contextPanel.cbBots.count()):
            model = self._contextPanel.cbBots.itemData(i)
            if isinstance(model, AiModelBase):
                models.append(model)

        # Unblock any in-flight provider stream before waiting on AgentLoop.
        for model in models:
            if model.isRunning():
                model.requestInterruption()

        self._resetAgentLoop()

        for model in models:
            model.cleanup()

        if self._codeReviewExecutor:
            self._codeReviewExecutor.cancel()
            self._codeReviewExecutor = None
            self._codeReviewDiffs.clear()
        self._injectedContext = None

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
        if self._agentLoop is not None:
            self._agentLoop.abort()

    def _doRequest(self, prompt: str, chatMode: AiChatMode, sysPrompt: str = None, collapsed=False):
        self._disableAutoScroll = False

        model = self.currentChatModel()
        if model is None:
            return
        loop = self._ensureAgentLoop()
        params = self._buildQueryParams(chatMode, sysPrompt)
        effectiveSysPrompt = params.system_prompt

        isNewConversation = len(loop.messages()) == 0

        injectedContext = self._injectedContext

        if chatMode == AiChatMode.CodeReview:
            prompt = CODE_REVIEW_PROMPT.format(diff=prompt)

        # Build context
        fullPrompt = prompt
        if not collapsed:
            provider = self.contextProvider()
            selectedIds = self._contextPanel.selectedContextIds() if provider is not None else []
            contextText = provider.buildContextText(
                selectedIds) if provider is not None else ""

            if injectedContext:
                merged = (contextText or "").strip()
                if merged:
                    merged += "\n\n" + injectedContext
                else:
                    merged = injectedContext
                contextText = merged

            if contextText:
                fullPrompt = f"<context>\n{contextText.rstrip()}\n</context>\n\n" + prompt

        # Keep title generation based on the user's original prompt (no injected context).
        titleSeed = (effectiveSysPrompt + "\n" +
                     prompt) if effectiveSysPrompt else prompt

        # System prompts are not persisted as messages in the loop, so render
        # once per conversation to avoid repeating the same prompt every turn.
        if effectiveSysPrompt and isNewConversation:
            self._chatBot.appendResponse(
                AiResponse(AiRole.System, effectiveSysPrompt), collapsed=True)

        # Show user message in chatbot
        self._chatBot.appendResponse(
            AiResponse(AiRole.User, fullPrompt), collapsed=collapsed)

        self._contextPanel.btnSend.setVisible(False)
        self._contextPanel.btnStop.setVisible(True)
        self._historyPanel.setEnabled(False)
        self._contextPanel.cbBots.setEnabled(False)
        self._contextPanel.setFocus()

        # Reset delta flags for the new response
        self._firstTextDelta = True
        self._firstReasoningDelta = True

        # Submit to agent loop (this starts the background thread)
        loop.submit(fullPrompt, params)
        self._setGenerating(True)

        # Clear tool restrictions after the request is sent
        self._restrictedToolNames = None

        if isNewConversation and not ApplicationBase.instance().testing and titleSeed:
            self._generateChatTitle(
                self._historyPanel.currentHistory().historyId, titleSeed)

        self._updateChatHistoryModel(model)
        self._setEmbeddedRecentListVisible(False)

    @staticmethod
    def _historyHasSameSystemPrompt(history, sp: str) -> bool:
        if not sp:
            return False

        for h in history:
            if h.role != AiRole.System:
                continue
            if h.message == sp:
                return True

        return False

    @staticmethod
    def _historyHasSameSystemPromptInMessages(messages, sp):
        if not sp:
            return False
        from qgitc.agent.types import SystemMessage as SysMsg
        for msg in messages:
            if isinstance(msg, SysMsg) and msg.content == sp:
                return True
        return False

    @staticmethod
    def _historyHasSameContext(history, contextText: str) -> bool:
        if not contextText:
            return False

        target = f"<context>\n{contextText.rstrip()}\n</context>"
        for h in history:
            if h.role != AiRole.User:
                continue
            if h.message and h.message.startswith(target):
                return True

        return False


    def _makeUiToolCallResponse(self, toolName: str, args: Union[str, dict]):
        tool = self._toolRegistry.get(toolName) if self._toolRegistry else None
        if tool:
            if tool.is_destructive():
                toolType = ToolType.DANGEROUS
            elif tool.is_read_only():
                toolType = ToolType.READ_ONLY
            else:
                toolType = ToolType.WRITE
        else:
            toolType = ToolType.DANGEROUS

        icon = self._getToolIcon(toolType)
        title = self.tr("{} run `{}`").format(
            icon, toolName or "unknown")

        if isinstance(args, str):
            body = args
        else:
            body = json.dumps(args, ensure_ascii=False)
        return AiResponse(AiRole.Tool, body, title)

    def _providerUiTools(self):
        provider = self.contextProvider()
        if provider is None:
            return []

        return provider.uiTools() or []

    def _buildToolRegistry(self):
        registry = ToolRegistry()
        register_builtin_tools(registry)
        for tool in self._providerUiTools():
            if isinstance(tool, UiTool):
                tool.set_dispatcher(self._uiToolDispatcher)
            registry.register(tool)
        return registry

    def _executeUiToolHandler(self, toolName, params):
        provider = self.contextProvider()
        if provider is None:
            return False, "No context provider"
        return provider.executeUiTool(toolName, params)

    def _ensureAgentLoop(self):
        if self._agentLoop is not None:
            return self._agentLoop
        self._toolRegistry = self._buildToolRegistry()
        loop = AgentLoop(
            tool_registry=self._toolRegistry,
            permission_engine=self._permissionEngine,
            parent=self,
        )
        self._connectAgentLoop(loop)
        self._agentLoop = loop
        return loop

    def _getModelCapabilities(self, model):
        if model is None:
            return AiModelCapabilities()

        modelId = model.modelId or model.name
        return model.getModelCapabilities(modelId)

    def _buildSystemPrompt(self, chatMode: AiChatMode, sysPrompt: str = None):
        effectiveSysPrompt = sysPrompt
        if chatMode == AiChatMode.Agent and not sysPrompt:
            provider = self.contextProvider()
            overridePrompt = provider.agentSystemPrompt() if provider is not None else None
            effectiveSysPrompt = overridePrompt or AGENT_SYS_PROMPT
        elif chatMode == AiChatMode.CodeReview:
            effectiveSysPrompt = sysPrompt or CODE_REVIEW_SYS_PROMPT
        return effectiveSysPrompt

    def _buildQueryParams(self, chatMode: AiChatMode, sysPrompt: str = None):
        settings = ApplicationBase.instance().settings()
        model = self.currentChatModel()
        if model is None:
            raise ValueError("No chat model selected")
        caps = self._getModelCapabilities(model)
        temperature = settings.llmTemperature()
        adapter = AiModelBaseAdapter(
            model,
            self._contextPanel.currentModelId(),
            max_tokens=(caps.max_output_tokens if model.isLocal() else None),
            temperature=temperature,
            chat_mode=chatMode,
        )
        return QueryParams(
            provider=adapter,
            system_prompt=self._buildSystemPrompt(chatMode, sysPrompt),
            context_window=caps.context_window,
            max_output_tokens=caps.max_output_tokens,
            skill_registry=self._ensureSkillRegistry(),
        )

    def _ensureSkillRegistry(self):
        # type: () -> SkillRegistry
        if self._skillRegistry is None:
            self._skillRegistry = load_skill_registry(cwd=self._repoDir or ".")
        return self._skillRegistry

    def _connectAgentLoop(self, loop):
        loop.textDelta.connect(self._onAgentTextDelta)
        loop.reasoningDelta.connect(self._onAgentReasoningDelta)
        loop.toolCallStart.connect(self._onAgentToolCallStart)
        loop.toolCallResult.connect(self._onAgentToolCallResult)
        loop.turnComplete.connect(self._onAgentTurnComplete)
        loop.agentFinished.connect(self._onAgentFinished)
        loop.permissionRequired.connect(self._onAgentPermissionRequired)
        loop.errorOccurred.connect(self._onAgentError)

    def _disconnectAgentLoop(self):
        if self._agentLoop is None:
            return
        loop = self._agentLoop
        loop.textDelta.disconnect(self._onAgentTextDelta)
        loop.reasoningDelta.disconnect(self._onAgentReasoningDelta)
        loop.toolCallStart.disconnect(self._onAgentToolCallStart)
        loop.toolCallResult.disconnect(self._onAgentToolCallResult)
        loop.turnComplete.disconnect(self._onAgentTurnComplete)
        loop.agentFinished.disconnect(self._onAgentFinished)
        loop.permissionRequired.disconnect(self._onAgentPermissionRequired)
        loop.errorOccurred.disconnect(self._onAgentError)

    def _resetAgentLoop(self):
        if self._agentLoop is not None:
            self._agentLoop.abort()
            self._agentLoop.wait(3000)
            self._disconnectAgentLoop()
            self._agentLoop = None
            self._toolRegistry = None

    def _onAgentTextDelta(self, text):
        response = AiResponse(AiRole.Assistant, text)
        response.is_delta = True
        response.first_delta = self._firstTextDelta
        self._firstTextDelta = False
        self._chatBot.appendResponse(response)
        if not self._disableAutoScroll:
            sb = self._chatBot.verticalScrollBar()
            self._adjustingSccrollbar = True
            sb.setValue(sb.maximum())
            self._adjustingSccrollbar = False

    def _onAgentReasoningDelta(self, text):
        response = AiResponse(
            AiRole.Assistant, text,
            description=self.tr("🧠 Reasoning"),
        )
        response.is_delta = True
        response.first_delta = self._firstReasoningDelta
        self._firstReasoningDelta = False
        self._chatBot.appendResponse(response)

    def _onAgentToolCallStart(self, toolCallId, toolName, params):
        uiResponse = self._makeUiToolCallResponse(toolName, params)
        self._chatBot.appendResponse(uiResponse, collapsed=True)
        if not self._disableAutoScroll:
            sb = self._chatBot.verticalScrollBar()
            self._adjustingSccrollbar = True
            sb.setValue(sb.maximum())
            self._adjustingSccrollbar = False

    def _onAgentToolCallResult(self, toolCallId, content, isError):
        prefix = "✓" if not isError else "✗"
        desc = self.tr("{} tool output").format(prefix)
        response = AiResponse(AiRole.Tool, content, description=desc)
        self._chatBot.appendResponse(response, collapsed=True)

    def _onAgentTurnComplete(self, assistantMsg):
        self._saveChatHistoryFromLoop()
        # Reset delta flags for the next turn
        self._firstTextDelta = True
        self._firstReasoningDelta = True

    def _onAgentFinished(self):
        self._saveChatHistoryFromLoop()
        self._updateStatus()
        self._chatBot.collapseLatestReasoningBlock()

    def _onAgentPermissionRequired(self, toolCallId, tool, inputData):
        toolName = tool.name if hasattr(tool, 'name') else str(tool)
        if tool.is_destructive():
            toolType = ToolType.DANGEROUS
        elif tool.is_read_only():
            toolType = ToolType.READ_ONLY
        else:
            toolType = ToolType.WRITE

        uiResponse = self._makeUiToolCallResponse(toolName, inputData)
        self._chatBot.appendResponse(uiResponse)

        expl = inputData.get("explanation", "").strip() if isinstance(inputData, dict) else ""
        desc = expl if expl else (tool.description if hasattr(tool, 'description') else "")
        self._chatBot.insertToolConfirmation(
            toolName=toolName,
            params=inputData,
            toolDesc=desc,
            toolType=toolType,
            toolCallId=toolCallId,
        )

    def _onAgentError(self, errorMsg):
        self._chatBot.appendServiceUnavailable(errorMsg)

    def _saveChatHistoryFromLoop(self):
        if self._agentLoop is None:
            return
        chatHistory = self._historyPanel.currentHistory()
        if not chatHistory:
            return
        store = ApplicationBase.instance().aiChatHistoryStore()
        model = self.currentChatModel()
        modelKey = AiModelFactory.modelKey(model) if model else None
        modelId = (model.modelId or model.name) if model else None
        updated = store.updateFromMessages(
            chatHistory.historyId,
            self._agentLoop.messages(),
            modelKey=modelKey,
            modelId=modelId,
        )
        if updated:
            self._historyPanel.setCurrentHistory(updated.historyId)

    def _onToolExecutionStrategyChanged(self, strategyValue: int):
        """Handle tool execution strategy change."""
        self._permissionEngine = create_permission_engine(strategyValue)

    def _updateStatus(self):
        self._contextPanel.btnSend.setVisible(True)
        self._contextPanel.btnStop.setVisible(False)
        self._historyPanel.setEnabled(True)
        self._contextPanel.cbBots.setEnabled(True)
        focus = ApplicationBase.instance().focusWidget()
        if not (isinstance(focus, QLineEdit) or isinstance(focus, QPlainTextEdit)):
            self._contextPanel.setFocus()
        self._setGenerating(False)

    def _onToolApproved(self, toolName: str, params: dict, toolCallId: str):
        if self._agentLoop is not None:
            self._agentLoop.approve_tool(toolCallId)

    def _onToolRejected(self, toolName: str, toolCallId: str):
        if self._agentLoop is not None:
            self._chatBot.setToolConfirmationStatus(
                toolCallId, ConfirmationStatus.REJECTED)
            self._agentLoop.deny_tool(toolCallId)

    def _onModelChanged(self, index: int):
        model = self._ensureModelInstantiatedAt(index)
        if model is None:
            return
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

        if self.isGenerating():
            sb: QScrollBar = self.messages.verticalScrollBar()
            self._disableAutoScroll = sb.value() != sb.maximum()

    @property
    def messages(self) -> AiChatbot:
        return self._chatBot

    def currentChatModel(self) -> AiModelBase:
        data = self._contextPanel.cbBots.currentData()
        if isinstance(data, AiModelBase):
            return data
        # Lazily instantiate if needed.
        return self._ensureCurrentModelInstantiated()

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
        self._injectedContext = scene
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
        self._injectedContext = "type: staged changes (index)"
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
        self._updateEmbeddedConversationHeader()

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
        self._updateEmbeddedConversationHeader()

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
            self._setEmbeddedRecentListVisible(True)
            return

        self._loadMessagesFromHistory(chatHistory.messages)
        self._setEmbeddedRecentListVisible(False)

        sb = self.messages.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _loadMessagesFromHistory(self, historyDicts: List[Dict], addToChatBot=True):
        """Load messages from history dicts into the agent loop and chatbot."""
        if not historyDicts:
            return

        agentMessages = history_dicts_to_messages(historyDicts)

        # Set messages on agent loop (will be created on next submit)
        loop = self._ensureAgentLoop()
        loop.set_messages(agentMessages)

        if not addToChatBot:
            return

        chatbot = self.messages
        chatbot.setHighlighterEnabled(False)

        for msg in historyDicts:
            role = AiRole.fromString(msg.get('role', 'user'))
            content = msg.get('content', '')
            reasoning = msg.get('reasoning', None)
            toolCalls = msg.get('tool_calls', None)
            description = msg.get('description', None)

            if reasoning:
                reasoningResponse = AiResponse(
                    AiRole.Assistant, reasoning,
                    description=self.tr("🧠 Reasoning"))
                chatbot.appendResponse(reasoningResponse, collapsed=True)

            if role == AiRole.Assistant and isinstance(toolCalls, list) and toolCalls:
                # Show text content if present
                if content:
                    chatbot.appendResponse(
                        AiResponse(role, content), collapsed=False)
                # Show each tool call
                for tc in toolCalls:
                    if not isinstance(tc, dict):
                        continue
                    func = (tc.get("function") or {})
                    toolName = func.get("name")
                    uiResponse = self._makeUiToolCallResponse(
                        toolName, func.get("arguments"))
                    chatbot.appendResponse(uiResponse, collapsed=True)
            elif role == AiRole.Tool:
                # Show tool result
                response = AiResponse(role, content, description=description)
                chatbot.appendResponse(response, collapsed=True)
            else:
                # System, User, or plain Assistant
                collapsed = (role == AiRole.Tool) or (role == AiRole.System)
                chatbot.appendResponse(
                    AiResponse(role, content), collapsed=collapsed)

        chatbot.setHighlighterEnabled(True)

    def _clearCurrentChat(self):
        """Clear the current chat display and reset agent loop"""
        self._resetAgentLoop()
        self._codeReviewDiffs.clear()
        self._injectedContext = None
        self.messages.clear()

    def _setEmbeddedRecentListVisible(self, visible: bool):
        if not self._embedded or self._hideHistoryPanel:
            return

        if visible:
            visible = self._historyPanel.historyModel().rowCount() > 0
        self._historyPanel.setVisible(visible)
        self._updateEmbeddedConversationHeader()

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

        # Refresh embedded header if this is the currently active conversation.
        cur = self._historyPanel.currentHistory()
        if cur and cur.historyId == historyId:
            self._updateEmbeddedConversationHeader()

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

    def resolveFileAsync(
        self,
        repoDir: str,
        sha1: str,
        path: str,
        conflictText: str,
        context: str = None,
        reportFile: Optional[str] = None,
    ) -> ResolveConflictJob:
        job = ResolveConflictJob(
            self,
            repoDir=repoDir,
            sha1=sha1,
            path=path,
            conflictText=conflictText,
            context=context,
            reportFile=reportFile,
        )
        QTimer.singleShot(0, job.start)
        return job
