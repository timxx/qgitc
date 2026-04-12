# -*- coding: utf-8 -*-

import logging
from typing import Any, Callable, Dict, Optional, Tuple

from PySide6.QtCore import QMutex, QObject, QWaitCondition, Signal, Slot

from qgitc.agent.tool import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class UiToolDispatcher(QObject):
    """Lives on the main thread. Receives tool execution requests from
    background threads and dispatches them to a handler function."""

    _executeRequested = Signal(str, str, dict)  # request_id, tool_name, params

    def __init__(self, parent=None):
        # type: (Optional[QObject]) -> None
        super().__init__(parent)
        self._handler = None  # type: Optional[Callable]
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._results = {}  # type: Dict[str, Tuple[bool, str]]
        self._executeRequested.connect(self._onExecute)

    def set_handler(self, handler):
        # type: (Callable[[str, Dict[str, Any]], Tuple[bool, str]]) -> None
        """Set the handler called on the main thread.

        handler(tool_name, params) -> (ok, output)
        """
        self._handler = handler

    @Slot(str, str, dict)
    def _onExecute(self, request_id, tool_name, params):
        # type: (str, str, dict) -> None
        """Called on main thread via signal-slot connection."""
        ok, output = False, "No handler set"
        if self._handler is not None:
            try:
                ok, output = self._handler(tool_name, params)
            except Exception as e:
                logger.exception("UI tool handler error: %s", tool_name)
                ok, output = False, str(e)

        self._mutex.lock()
        self._results[request_id] = (ok, output)
        self._cond.wakeAll()
        self._mutex.unlock()

    def dispatch_and_wait(self, request_id, tool_name, params):
        # type: (str, str, dict) -> Tuple[bool, str]
        """Called from background thread. Dispatches to main thread and
        blocks until the result is available."""
        self._executeRequested.emit(request_id, tool_name, params)

        self._mutex.lock()
        while request_id not in self._results:
            self._cond.wait(self._mutex)
        result = self._results.pop(request_id)
        self._mutex.unlock()
        return result


class UiTool(Tool):
    """Wraps a context-provider UI tool for use in AgentLoop.

    Execution dispatches to the main thread via UiToolDispatcher.
    """

    def __init__(self, name, description, schema, dispatcher=None):
        # type: (str, str, Dict[str, Any], Optional[UiToolDispatcher]) -> None
        self.name = name
        self.description = description
        self._schema = schema
        self._dispatcher = dispatcher
        self._next_id = 0

    def set_dispatcher(self, dispatcher):
        # type: (UiToolDispatcher) -> None
        self._dispatcher = dispatcher

    def is_read_only(self):
        # type: () -> bool
        return True

    def execute(self, input_data, context):
        # type: (Dict[str, Any], ToolContext) -> ToolResult
        if self._dispatcher is None:
            return ToolResult(
                content="UI tool dispatcher not available",
                is_error=True,
            )
        self._next_id += 1
        request_id = "{}_{}".format(self.name, self._next_id)
        ok, output = self._dispatcher.dispatch_and_wait(
            request_id, self.name, input_data,
        )
        return ToolResult(content=output, is_error=not ok)

    def input_schema(self):
        # type: () -> Dict[str, Any]
        return self._schema
