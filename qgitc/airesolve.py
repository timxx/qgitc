# -*- coding: utf-8 -*-

import os
from threading import Lock
from typing import Dict

from PySide6.QtCore import QObject, QTimer, Signal

from qgitc.agent.permission_presets import createPermissionEngine
from qgitc.agent.tools.resolve_result import ResolveResultTool
from qgitc.llm import AiChatMode
from qgitc.models.prompts import RESOLVE_PROMPT, RESOLVE_SYS_PROMPT
from qgitc.resolutionreport import (
    appendResolutionReportEntry,
    buildResolutionReportEntry,
)


class _ResolveSessionContext(object):
    def __init__(self):
        self._lock = Lock()
        self._status = None
        self._reason = ""

    def setResult(self, status, reason):
        with self._lock:
            self._status = status
            self._reason = reason or ""

    def result(self):
        with self._lock:
            if not self._status:
                return None
            return {
                "status": self._status,
                "reason": self._reason,
            }


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
        from qgitc.aichatwidget import AiChatWidget  # Avoid circular import
        self._widget: AiChatWidget = widget
        self._repoDir = repoDir
        self._sha1 = sha1
        self._path = path
        self._conflictText = conflictText
        self._context = context
        self._reportFile = reportFile

        self._done = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._oldPermissionEngine = None

        self._resolveContext = _ResolveSessionContext()

    def start(self):
        w = self._widget
        w._waitForInitialization()

        model = w.currentChatModel()
        if not model:
            self._finish(False, "no_model")
            return
        else:
            model.requestInterruption()

        # Always start a new conversation for conflict resolution.
        w._createNewConversation()

        contextText = (self._context or "").strip() or None
        w._injectedContext = contextText

        prompt = RESOLVE_PROMPT.format(
            operation="cherry-pick" if self._sha1 else "merge",
            conflict=self._conflictText,
        )

        w._resetAgentLoop()
        w._ensureAgentLoop(RESOLVE_SYS_PROMPT)

        self._oldPermissionEngine = w._permissionEngine
        w._agentLoop._permission_engine = createPermissionEngine(
            3)  # AllAuto
        w._agentLoop.finished.connect(self._onAgentFinished)
        w._agentLoop.errorOccurred.connect(self._onError)

        w._toolRegistry.register(ResolveResultTool(self._resolveContext))

        w._doRequest(prompt, AiChatMode.Agent, parseSlashCommand=False)

        self._timer.timeout.connect(self._onTimeout)
        self._timer.start(5 * 60 * 1000)

    def abort(self):
        self._widget._onButtonStop()

    def _onAgentFinished(self):
        result = self._resolveContext.result()
        ok, reason = self._validateResolveOutcome(result)
        self._finish(ok, reason)
        self._restoreAgent()

    def _onError(self, errorMsg):
        self._finish(False, errorMsg)

    def _onTimeout(self):
        self._finish(False, "Assistant response timed out")
        self.abort()

    def _validateResolveOutcome(self, result: Dict[str, str]):
        if not result:
            return False, "No resolve result tool call recorded"

        status = result.get("status")
        reason = result.get("reason", "")
        if status == "failed":
            return False, reason or "Assistant reported failure"
        if status != "ok":
            return False, "Invalid resolve result status"

        # Verify file is conflict-marker-free
        try:
            absPath = os.path.join(self._repoDir, self._path)
            with open(absPath, "rb") as f:
                merged = f.read()
        except Exception as e:
            return False, f"read_back_failed: {e}"

        if b"<<<<<<<" in merged or b"=======" in merged or b">>>>>>>" in merged:
            return False, "conflict_markers_remain"

        return True, reason or "Assistant reported success"

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
        self.finished.emit(ok, reason)

    def _restoreAgent(self):
        agent = self._widget._agentLoop
        if not agent:
            return
        agent._permission_engine = self._oldPermissionEngine
        agent.finished.disconnect(self._onAgentFinished)
        agent.errorOccurred.disconnect(self._onError)
        self._widget._toolRegistry.unregister("resolve_result")
