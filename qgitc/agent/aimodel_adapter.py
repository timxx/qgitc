# -*- coding: utf-8 -*-

import json
import queue
from typing import Any, Dict, Iterator, List, Optional

from PySide6.QtCore import QCoreApplication, QObject, Qt, QThread, Signal

from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ReasoningDelta,
    StreamEvent,
    ToolCallDelta,
)
from qgitc.agent.types import (
    AssistantMessage,
    Message,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    UserMessage,
)
from qgitc.llm import AiChatMode, AiModelBase, AiParameters, AiResponse, AiRole


class _QueryDispatcher(QObject):
    queryRequested = Signal(object)


class AiModelBaseAdapter(ModelProvider):
    """Bridges the signal-driven AiModelBase to the iterator-based ModelProvider."""

    def __init__(self, model, modelId, max_tokens=None, temperature=0.1, chat_mode=AiChatMode.Agent):
        # type: (AiModelBase, str, Optional[int], float, AiChatMode) -> None
        self._model = model
        self._modelId = modelId
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._chat_mode = chat_mode
        self._queryDispatcher = _QueryDispatcher()
        self._queryDispatcher.queryRequested.connect(
            self._model.queryAsync, Qt.ConnectionType.QueuedConnection)

    def _startQueryOnModelThread(self, params):
        # type: (AiParameters) -> None
        modelThread = self._model.thread()
        if modelThread is None or QThread.currentThread() is modelThread:
            self._model.queryAsync(params)
            return

        # Ensure model network operations are created on the model owner's thread.
        self._queryDispatcher.queryRequested.emit(params)

    def stream(
        self,
        messages,          # type: List[Message]
        tools=None,        # type: Optional[List[Dict[str, Any]]]
    ):
        # type: (...) -> Iterator[StreamEvent]
        event_queue = queue.Queue()  # type: queue.Queue[StreamEvent]
        finished_flag = [False]
        has_tool_calls = [False]
        network_error = [None]  # type: List[Optional[str]]
        usage = Usage()

        def _on_response(response):
            # type: (AiResponse) -> None
            if response.reasoning or response.reasoningData:
                event_queue.put(ReasoningDelta(
                    text=response.reasoning or "",
                    reasoning_data=response.reasoningData,
                ))
            if response.message:
                event_queue.put(ContentDelta(text=response.message))
            if response.tool_calls:
                has_tool_calls[0] = True
                for tc in response.tool_calls:
                    func = tc.get("function", {})
                    event_queue.put(ToolCallDelta(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments_delta=func.get("arguments", ""),
                    ))
            if response.usage:
                usage.input_tokens += response.usage.inputTokens
                usage.output_tokens += response.usage.outputTokens

        def _on_finished():
            # type: () -> None
            finished_flag[0] = True

        def _on_network_error(errorMsg):
            # type: (str) -> None
            network_error[0] = errorMsg
            finished_flag[0] = True

        def _on_service_unavailable():
            # type: () -> None
            _on_network_error("")

        self._model.responseAvailable.connect(_on_response)
        self._model.finished.connect(_on_finished)
        self._model.networkError.connect(_on_network_error)
        self._model.serviceUnavailable.connect(_on_service_unavailable)

        try:
            # Build history from messages
            self._model.clear()
            for msg in messages:
                if isinstance(msg, UserMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            self._model.addHistory(AiRole.User, block.text)
                        elif isinstance(block, ToolResultBlock):
                            self._model.addHistory(
                                AiRole.Tool,
                                block.content,
                                toolCalls={"tool_call_id": block.tool_use_id},
                            )
                elif isinstance(msg, AssistantMessage):
                    text_parts = []  # type: List[str]
                    tool_calls = []  # type: List[Dict[str, Any]]
                    reasoning_text = None  # type: Optional[str]
                    reasoning_data = None
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            tool_calls.append({
                                "id": block.id,
                                "type": "function",
                                "function": {
                                    "name": block.name,
                                    "arguments": json.dumps(block.input),
                                },
                            })
                        elif isinstance(block, ThinkingBlock):
                            reasoning_text = block.thinking
                            reasoning_data = block.reasoning_data
                    text = "".join(text_parts)
                    kwargs = {}
                    if reasoning_text:
                        kwargs["reasoning"] = reasoning_text
                    if reasoning_data:
                        kwargs["reasoningData"] = reasoning_data
                    if tool_calls:
                        kwargs["toolCalls"] = tool_calls
                    self._model.addHistory(AiRole.Assistant, text, **kwargs)
                elif isinstance(msg, SystemMessage):
                    self._model.addHistory(AiRole.System, msg.content)

            # Build parameters
            params = AiParameters()
            params.stream = True
            params.continue_only = True
            params.chat_mode = self._chat_mode
            params.temperature = self._temperature
            params.model = self._modelId
            if self._max_tokens is not None:
                params.max_tokens = self._max_tokens
            if self._chat_mode == AiChatMode.Agent and tools:
                params.tools = tools
                params.tool_choice = "auto"

            # Start async query on the model's owner thread.
            self._startQueryOnModelThread(params)

            # Pump event loop until finished
            while not finished_flag[0]:
                QCoreApplication.processEvents()
                if network_error[0] is not None:
                    raise RuntimeError(network_error[0])
                while not event_queue.empty():
                    yield event_queue.get_nowait()

            # Drain remaining events
            while not event_queue.empty():
                yield event_queue.get_nowait()

            if network_error[0] is not None:
                raise RuntimeError(network_error[0])

            # Yield final completion event
            stop_reason = "tool_use" if has_tool_calls[0] else "end_turn"
            if usage.input_tokens == 0 and usage.output_tokens == 0:
                # If the model didn't provide usage info, estimate it based on the input messages.
                usage.input_tokens = self.countTokens(messages, tools=tools)
            yield MessageComplete(stop_reason=stop_reason, usage=usage)

        finally:
            self._model.responseAvailable.disconnect(_on_response)
            self._model.finished.disconnect(_on_finished)
            self._model.networkError.disconnect(_on_network_error)
            self._model.serviceUnavailable.disconnect(_on_service_unavailable)

    def countTokens(
        self,
        messages,          # type: List[Message]
        system_prompt=None,  # type: Optional[str]
        tools=None,        # type: Optional[List[Dict[str, Any]]]
    ):
        # type: (...) -> int
        total_chars = 0
        tokens = 0
        for msg in messages:
            if (isinstance(msg, AssistantMessage) and msg.usage and
                    (msg.usage.input_tokens > 0 or msg.usage.output_tokens > 0)):
                tokens += msg.usage.input_tokens + msg.usage.output_tokens
                continue

            if isinstance(msg, (UserMessage, AssistantMessage)):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        total_chars += len(block.text)
                    elif isinstance(block, ToolResultBlock):
                        total_chars += len(block.content)
            elif isinstance(msg, SystemMessage):
                total_chars += len(msg.content)

        if system_prompt:
            total_chars += len(system_prompt)

        return tokens if tokens > 0 else total_chars // 4
