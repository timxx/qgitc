# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

from qgitc.agenttoolexecutor import AgentToolResult
from qgitc.aichatcontextprovider import AiChatContextProvider


class UiToolExecutor(QObject):
    """Executes provider-defined UI tools on the Qt UI thread.

    This executor is asynchronous (non-blocking) but does not use background
    threads. It schedules work onto the UI event loop and emits a toolFinished
    signal with an AgentToolResult.
    """

    toolFinished = Signal(object)  # AgentToolResult

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._inflight: bool = False
        self._pending: Optional[Tuple[str,
                                      Dict[str, Any], AiChatContextProvider]] = None

    def executeAsync(self, toolName: str, params: Dict[str, Any], provider: AiChatContextProvider) -> bool:
        if self._inflight:
            return False
        if not provider:
            self.toolFinished.emit(AgentToolResult(
                toolName, False, "No context provider."))
            return True

        self._inflight = True
        self._pending = (toolName, params or {}, provider)
        QTimer.singleShot(0, self._executePending)
        return True

    def shutdown(self):
        self._pending = None
        self._inflight = False

    def _executePending(self):
        pending = self._pending
        self._pending = None

        if not pending:
            self._inflight = False
            return

        toolName, params, provider = pending
        try:
            ok, output = provider.executeUiTool(toolName, params or {})
            result = AgentToolResult(toolName, bool(ok), str(output or ""))
        except Exception as e:
            result = AgentToolResult(
                toolName, False, f"UI tool execution failed: {e}")

        self._inflight = False
        self.toolFinished.emit(result)
