# -*- coding: utf-8 -*-

import json
import os
import typing
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
    QMenu,
    QScrollBar,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from qgitc.agentmachine import AgentToolMachine, AggressiveStrategy, DefaultStrategy
from qgitc.agenttoolexecutor import AgentToolExecutor
from qgitc.agenttools import (
    AgentTool,
    AgentToolRegistry,
    AgentToolResult,
    ToolType,
    parseToolArguments,
)
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
from qgitc.uitoolexecutor import UiToolExecutor

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
        widget: "AiChatWidget",
        repoDir: str,
        sha1: str,
        path: str,
        conflictText: str,
        context: str = None,
        reportFile: str = None,
        parent: QObject = None,
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
        self._savedStrategy = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)

        self._model = None
        self._oldHistoryCount = 0

    def start(self):
        w = self._widget
        w._waitForInitialization()

        model = w.currentChatModel()
        if not model:
            self._finish(False, "no_model")
            return

        # Always start a new conversation for conflict resolution.
        w._createNewConversation()

        # Context should be supplied by the caller (e.g. embedded context provider
        # or ResolveContext.context). Avoid synthesizing duplicate repo/file
        # lines here.
        w._injectedContext = (self._context or "").strip() or None

        prompt = RESOLVE_PROMPT.format(
            operation="cherry-pick" if self._sha1 else "merge",
            conflict=self._conflictText,
        )

        self._savedStrategy = w._toolMachine._strategy
        w._toolMachine.setStrategy(AggressiveStrategy())

        self._model = model
        self._oldHistoryCount = len(model.history)

        self._timer.timeout.connect(self._onTimeout)
        self._timer.start(5 * 60 * 1000)

        model.finished.connect(self._checkDone)
        model.networkError.connect(self._onNetworkError)
        model.serviceUnavailable.connect(
            lambda: self._finish(False, "service_unavailable"))
        # Tools can also trigger another continue-only generation.
        w._agentExecutor.toolFinished.connect(self._checkDone)

        w._doRequest(prompt, AiChatMode.Agent, RESOLVE_SYS_PROMPT)

    def abort(self):
        if self._model:
            self._model.requestInterruption()

    def _lastAssistantTextSince(self, startIndex: int) -> str:
        model = self._model
        if model is None:
            return ""
        for i in range(len(model.history) - 1, startIndex - 1, -1):
            h = model.history[i]
            if h.role == AiRole.Assistant and h.message:
                return h.message
        return ""

    def _onTimeout(self):
        model = self._model
        if model is not None:
            model.requestInterruption()
        self._finish(False, "Assistant response timed out")

    def _onNetworkError(self, errorMsg: str):
        self._finish(False, errorMsg)

    @staticmethod
    def _parseFinalResolveMessage(text: str) -> Tuple[Optional[str], str]:
        """Parse the final assistant message.

        Expected unified format:
          QGITC_RESOLVE_OK|QGITC_RESOLVE_FAILED\n\n<detail>
        Returns (status, detail) where status is 'ok'|'failed'|None.
        """
        if not text:
            return None, ""

        # AI may not always follow the format strictly
        # we have to search for the markers.
        pos = text.find("QGITC_RESOLVE_OK")
        if pos != -1:
            detail = text[pos+len("QGITC_RESOLVE_OK"):]
            # Strip leading newlines but preserve intended formatting.
            # Expected format: marker\n\ndetail, so we skip up to 2 leading \n.
            detail = detail.lstrip('\n')
            return "ok", detail

        pos = text.find("QGITC_RESOLVE_FAILED")
        if pos != -1:
            detail = text[pos+len("QGITC_RESOLVE_FAILED"):]
            detail = detail.lstrip('\n')
            return "failed", detail

        return None, ""

    def _checkDone(self, *args):
        if self._done:
            return

        model = self._model
        if model is None:
            return

        # No new messages yet.
        if len(model.history) == self._oldHistoryCount:
            return

        response = self._lastAssistantTextSince(self._oldHistoryCount)

        status, detail = self._parseFinalResolveMessage(response)
        if status == "failed":
            self._finish(False, detail or "Assistant reported failure")
            return

        if status != "ok":
            return

        # Verify the working tree file is conflict-marker-free.
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

    def _disconnect(self):
        model = self._model
        if model is not None:
            model.finished.disconnect(self._checkDone)
            model.networkError.disconnect(self._onNetworkError)
        self._widget._agentExecutor.toolFinished.disconnect(self._checkDone)
        self._timer.timeout.disconnect(self._onTimeout)

    def _finish(self, ok: bool, reason: object):
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
                    reason=reason
                )
                appendResolutionReportEntry(self._reportFile, entry)
            except Exception:
                # Reporting must never break the resolve flow.
                pass

        self._disconnect()
        self._timer.stop()

        # Restore tool permission.
        self._widget._toolMachine.setStrategy(self._savedStrategy)

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
        self._agentExecutor = AgentToolExecutor(self)
        self._agentExecutor.toolFinished.connect(self._onAgentToolFinished)
        self._uiToolExecutor = UiToolExecutor(self)
        self._uiToolExecutor.toolFinished.connect(self._onAgentToolFinished)

        # Create tool orchestration machine
        self._toolMachine = AgentToolMachine(
            strategy=DefaultStrategy(),
            toolLookupFn=self._toolByName,
            maxConcurrent=4,
            parent=self)
        self._toolMachine.toolExecutionRequested.connect(self._onExecuteTool)
        self._toolMachine.userConfirmationNeeded.connect(
            self._onToolConfirmationNeeded)
        self._toolMachine.toolExecutionCancelled.connect(
            self._onToolExecutionCancelled)
        self._toolMachine.agentContinuationReady.connect(self._onContinueAgent)

        # Code review diff collection (staged/local changes)
        self._codeReviewExecutor: Optional[SubmoduleExecutor] = None
        self._codeReviewDiffs: List[str] = []
        self._injectedContext: str = None

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
        model = self.currentChatModel()
        return model is not None and model.isRunning()

    def isHistoryReady(self) -> bool:
        """True once history has been loaded and the widget is initialized."""
        return bool(self._isInitialized)

    def isBusyForCodeReview(self) -> bool:
        """True if starting a dock-based code review would be disruptive."""
        if self.isGenerating():
            return True
        return self._toolMachine.taskInProgress()

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

        model = self.currentChatModel()
        isNewConversation = (model is None) or (not model.history)

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

        model.responseAvailable.connect(self._onMessageReady)
        model.reasoningFinished.connect(self._onReasoningFinished)
        model.finished.connect(self._onResponseFinish)
        model.serviceUnavailable.connect(self._onServiceUnavailable)
        model.networkError.connect(self._onNetworkError)
        model.modelsReady.connect(self._onModelsReady)

        return model

    def queryClose(self):
        if self._titleGenerator:
            self._titleGenerator.cancel()

        if self._agentExecutor:
            self._agentExecutor.shutdown()

        if self._uiToolExecutor:
            self._uiToolExecutor.shutdown()

        for i in range(self._contextPanel.cbBots.count()):
            model = self._contextPanel.cbBots.itemData(i)
            if not isinstance(model, AiModelBase):
                continue
            if model.isRunning():
                model.requestInterruption()
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

        # If the user types a new message while there are pending tool confirmations,
        # treat them as rejected to keep the conversation history consistent.
        # (Otherwise, switching chats / continuing can lose the confirmation UI and
        # later requests may lack required tool results.)
        if self._toolMachine.hasPendingResults():
            self._toolMachine.rejectPendingResults()

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
        if self._toolMachine.hasPendingResults():
            return

        # Wait until the model has finished recording the assistant tool_calls
        # message; otherwise sending tool messages with tool_call_id can 400.
        if model.isRunning():
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
        params.tools = self._availableOpenAiTools()
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

        # Keep title generation based on the user's original prompt (no injected context).
        titleSeed = (params.sys_prompt + "\n" +
                     prompt) if params.sys_prompt else prompt

        injectedContext = self._injectedContext

        if chatMode == AiChatMode.Agent:
            params.tools = self._availableOpenAiTools()
            params.tool_choice = "auto"

            # Don't add system prompt if there is already one
            if not sysPrompt and (len(model.history) == 0 or not collapsed):
                provider = self.contextProvider()
                overridePrompt = provider.agentSystemPrompt() if provider is not None else None
                params.sys_prompt = overridePrompt or AGENT_SYS_PROMPT
        elif chatMode == AiChatMode.CodeReview:
            # Code review can also use tools to fetch missing context.
            # (Models that don't support tool calls will simply ignore them.)
            params.tools = self._availableOpenAiTools()
            params.tool_choice = "auto"
            params.sys_prompt = sysPrompt or CODE_REVIEW_SYS_PROMPT
            params.prompt = CODE_REVIEW_PROMPT.format(
                diff=params.prompt)

        provider = self.contextProvider()
        if not collapsed:
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

            if contextText and not self._historyHasSameContext(model.history, contextText):
                params.prompt = f"<context>\n{contextText.rstrip()}\n</context>\n\n" + \
                    params.prompt

        if params.sys_prompt and not self._historyHasSameSystemPrompt(model.history, params.sys_prompt):
            self._doMessageReady(model, AiResponse(
                AiRole.System, params.sys_prompt), True)
        else:
            params.sys_prompt = None

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

    def _onMessageReady(self, response: AiResponse):
        # tool-only responses can have empty message.
        if not response.message and not response.reasoning and not response.tool_calls:
            return

        model: AiModelBase = self.sender()
        if response.reasoning:
            reasoningResponse = AiResponse(
                AiRole.Assistant, response.reasoning, description=self.tr("🧠 Reasoning"))
            reasoningResponse.is_delta = response.is_delta
            reasoningResponse.first_delta = response.first_delta
            self._doMessageReady(model, reasoningResponse)

        self._doMessageReady(model, response)

    def _onReasoningFinished(self):
        # Collapse the most recently displayed reasoning block (if any).
        self._chatBot.collapseLatestReasoningBlock()

    # ========== Tool Machine Signal Handlers ==========

    def _onExecuteTool(self, toolCallId: str, toolName: str, params: dict):
        """Handler for when machine requests tool execution."""
        # Display the tool call
        uiResponse = self._makeUiToolCallResponse(toolName, params or {})
        self._chatBot.appendResponse(uiResponse, collapsed=True)

        # Execute it
        started = self._executeToolAsync(toolName, params or {}, toolCallId)
        if not started:
            # Synthetic failure
            self._onAgentToolFinished(AgentToolResult(
                toolName, False, self.tr("Failed to start tool execution."), toolCallId=toolCallId))

    def _onToolConfirmationNeeded(self, toolCallId: str, toolName: str,
                                  params: dict, toolDesc: str, toolType: ToolType):
        """Handler for when machine needs user confirmation for a tool."""

        # Display confirmation UI
        uiResponse = self._makeUiToolCallResponse(toolName, params)
        self._chatBot.appendResponse(uiResponse)

        self._chatBot.insertToolConfirmation(
            toolName=toolName,
            params=params,
            toolDesc=toolDesc or self.tr("Unknown tool requested by model"),
            toolType=toolType,
            toolCallId=toolCallId,
        )

    def _onToolExecutionCancelled(self, toolCallId: str, toolName: str, toolType: ToolType):
        """Handler for when tool execution is cancelled."""
        model = self.currentChatModel()
        if model is None:
            return

        if toolType != ToolType.READ_ONLY:
            self._chatBot.setToolConfirmationStatus(
                toolCallId, ConfirmationStatus.REJECTED)
        description = self.tr("✗ `{}` skipped").format(toolName)
        model.addHistory(
            AiRole.Tool,
            SKIP_TOOL,
            description=description,
            toolCalls={"tool_call_id": toolCallId},
        )
        self._doMessageReady(
            model,
            AiResponse(AiRole.Tool, SKIP_TOOL,
                       description=description),
            collapsed=True,
        )

    def _onContinueAgent(self):
        """Handler for when machine is ready for agent to continue."""
        # Machine signals when ready - continue immediately
        self._continueAgentConversation(delayMs=0)

    def _doMessageReady(self, model: AiModelBase, response: AiResponse, collapsed=False):
        index = self._contextPanel.cbBots.findData(model)

        assert (index != -1)
        messages: AiChatbot = self._chatBot
        if response.message or response.role == AiRole.Tool:
            messages.appendResponse(response, collapsed)

        # If the assistant produced tool calls, delegate to the tool machine.
        if response.role == AiRole.Assistant and response.tool_calls:
            self._toolMachine.processToolCalls(response.tool_calls)

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
            tool = self._toolByName(args[0])
            fallbackName = args[0]
        else:
            tool = args[0]
            fallbackName = "unknown"

        if tool:
            toolType = tool.toolType
            toolName = tool.name
        else:
            toolType = ToolType.DANGEROUS
            toolName = fallbackName

        icon = self._getToolIcon(toolType)
        title = self.tr("{} run `{}`").format(icon, toolName)

        if isinstance(args[1], str):
            body = args[1]
        else:
            body = json.dumps(args[1], ensure_ascii=False)
        return AiResponse(AiRole.Tool, body, title)

    def _providerUiTools(self) -> List[AgentTool]:
        provider = self.contextProvider()
        if provider is None:
            return []

        return provider.uiTools() or []

    def _toolByName(self, toolName: str) -> Optional[AgentTool]:
        if not toolName:
            return None
        for t in self._providerUiTools():
            if t.name == toolName:
                return t
        return AgentToolRegistry.tool_by_name(toolName)

    def _availableOpenAiTools(self) -> List[Dict[str, Any]]:
        tools = list(AgentToolRegistry.openai_tools())
        for t in self._providerUiTools():
            tools.append(t.to_openai_tool())
        return tools

    def _executeToolAsync(self, toolName: str, params: dict, toolCallId: Optional[str] = None) -> bool:
        provider = self.contextProvider()

        # Provider-defined UI tools run on the UI thread.
        if toolName and toolName.startswith("ui_") and provider is not None:
            for t in self._providerUiTools():
                if t.name == toolName:
                    return self._uiToolExecutor.executeAsync(toolName, params or {}, provider, toolCallId)

            # If a ui_ tool is requested but isn't available, fail fast.
            self._onAgentToolFinished(AgentToolResult(
                toolName, False, self.tr("UI tool not available in this context."), toolCallId=toolCallId))
            return True

        # Non-UI tools run in the background executor.
        return self._agentExecutor.executeAsync(toolName, params or {}, toolCallId)

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

    def _onToolApproved(self, toolName: str, params: dict, toolCallId: str):
        self._toolMachine.approveToolExecution(toolName, params, toolCallId)

    def _onToolRejected(self, toolName: str, toolCallId: str):
        self._toolMachine.rejectToolExecution(toolName, toolCallId)

    def _onAgentToolFinished(self, result: AgentToolResult):
        model = self.currentChatModel()
        toolName = result.toolName
        ok = result.ok
        output = result.output or ""
        toolCallId = result.toolCallId

        prefix = "✓" if ok else "✗"
        toolDesc = self.tr("{} `{}` output").format(prefix, toolName)
        toolCalls = {"tool_call_id": toolCallId} if toolCallId else None
        model.addHistory(AiRole.Tool, output,
                         description=toolDesc, toolCalls=toolCalls)
        resp = AiResponse(AiRole.Tool, output, description=toolDesc)
        self._doMessageReady(model, resp, collapsed=True)

        self._toolMachine.onToolFinished(result)

    def _onServiceUnavailable(self):
        messages: AiChatbot = self._chatBot
        messages.appendServiceUnavailable()
        self._updateStatus()

    def _onNetworkError(self, errorMsg: str):
        messages: AiChatbot = self._chatBot
        messages.appendServiceUnavailable(errorMsg)
        self._updateStatus()

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

        model = self.currentChatModel()
        if model is not None and model.isRunning():
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

        self._toolMachine.reset()

        def _addReasoning(reasoning: str):
            if reasoning:
                reasoningResponse = AiResponse(
                    AiRole.Assistant, reasoning, description=self.tr("🧠 Reasoning"))
                chatbot.appendResponse(reasoningResponse, collapsed=True)

        i = 0
        while i < len(messages):
            msg = messages[i]
            role = AiRole.fromString(msg.get('role', 'user'))
            content = msg.get('content', '')
            reasoning = msg.get('reasoning', None)
            description = msg.get('description', None)
            toolCalls = msg.get('tool_calls', None)
            reasoningData = msg.get('reasoning_data', None)

            model.addHistory(role, content, description=description,
                             toolCalls=toolCalls, reasoning=reasoning,
                             reasoningData=reasoningData)
            # Don't add tool calls to UI (both for assistant and tool roles)
            if addToChatBot and not toolCalls:
                _addReasoning(reasoning)
                response = AiResponse(role, content)
                collapsed = (role == AiRole.Tool) or (role == AiRole.System) or \
                    (role == AiRole.Assistant and toolCalls)
                chatbot.appendResponse(response, collapsed=collapsed)

            if role == AiRole.Assistant and isinstance(toolCalls, list) and toolCalls:
                toolCallResult, hasMoreMessages = self._collectToolCallResult(
                    i + 1, messages)

                if addToChatBot:
                    _addReasoning(reasoning)
                    if content:
                        response = AiResponse(role, content)
                        chatbot.appendResponse(response, collapsed=False)

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
                    tool = self._toolByName(toolName)
                    toolType = tool.toolType if tool else ToolType.WRITE

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
                    self._toolMachine.addAwaitingToolResult(tcid, tool)
                    if addToChatBot:
                        if isinstance(args, dict):
                            expl = args.get("explanation", "").strip()
                            if expl:
                                toolDesc = expl
                            else:
                                toolDesc = tool.description if tool else self.tr(
                                    "Unknown tool requested by model")
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
