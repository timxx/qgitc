# -*- coding: utf-8 -*-

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

from qgitc.agenttoolexecutor import AgentToolResult
from qgitc.aichatcontextprovider import AiChatContextProvider


class UiToolExecutor(QObject):
    """Executes provider-defined UI tools on the Qt UI thread.

    This executor is asynchronous (non-blocking) but does not use background
    threads. It schedules work onto the UI event loop and emits a toolFinished
    signal with an AgentToolResult.
    
    Supports tracking multiple pending calls via toolCallId.
    """

    toolFinished = Signal(object)  # AgentToolResult

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._inflight: Dict[str, Tuple[str,
                                        Dict[str, Any], AiChatContextProvider]] = {}

    def executeAsync(self, toolName: str, params: Dict[str, Any], provider: AiChatContextProvider, toolCallId: Optional[str] = None) -> bool:
        """Execute a UI tool asynchronously on the Qt event loop.
        
        Args:
            toolName: Name of the UI tool to execute
            params: Tool parameters
            provider: Context provider that can execute UI tools
            toolCallId: Optional unique identifier for tracking
            
        Returns:
            True if the tool was queued for execution
        """
        # Generate a unique ID if not provided
        if not toolCallId:
            toolCallId = str(uuid.uuid4())

        if not provider:
            self.toolFinished.emit(AgentToolResult(
                toolName, False, "No context provider.", toolCallId=toolCallId))
            return True

        self._inflight[toolCallId] = (toolName, params or {}, provider)
        QTimer.singleShot(0, lambda: self._executePending(toolCallId))
        return True

    def shutdown(self):
        """Shutdown the executor and clear all pending tasks."""
        self._inflight.clear()

    def _executePending(self, toolCallId: str):
        """Execute a pending UI tool task."""
        pending = self._inflight.pop(toolCallId, None)

        if not pending:
            return

        toolName, params, provider = pending
        try:
            ok, output = provider.executeUiTool(toolName, params or {})
            result = AgentToolResult(toolName, bool(ok), str(
                output or ""), toolCallId=toolCallId)
        except Exception as e:
            result = AgentToolResult(
                toolName, False, f"UI tool execution failed: {e}", toolCallId=toolCallId)

        self.toolFinished.emit(result)
