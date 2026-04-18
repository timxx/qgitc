# -*- coding: utf-8 -*-

import os

from PySide6.QtCore import QObject, QTimer, Signal

from qgitc.agent.agent_loop import AgentLoop, QueryParams
from qgitc.agent.aimodel_adapter import AiModelBaseAdapter
from qgitc.agent.permission_presets import create_permission_engine
from qgitc.agent.tool_registration import register_builtin_tools
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.applicationbase import ApplicationBase
from qgitc.llm import AiChatMode, AiResponse, AiRole
from qgitc.models.prompts import RESOLVE_PROMPT, RESOLVE_SYS_PROMPT
from qgitc.resolutionreport import (
    appendResolutionReportEntry,
    buildResolutionReportEntry,
)


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
            system_prompt=RESOLVE_SYS_PROMPT,
            parent=self,
        )
        params = QueryParams(
            provider=adapter,
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
