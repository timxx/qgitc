# -*- coding: utf-8 -*-

import json
import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal

from qgitc.agent.compaction import ConversationCompactor
from qgitc.agent.permissions import (
    PermissionAllow,
    PermissionAsk,
    PermissionDeny,
    PermissionEngine,
)
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ReasoningDelta,
    ToolCallDelta,
)
from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import (
    AssistantMessage,
    Message,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

logger = logging.getLogger(__name__)


class AgentLoop(QThread):
    """Orchestrates the LLM agent loop in a dedicated thread.

    Communicates with the main thread via Qt signals.
    """

    textDelta = Signal(str)
    reasoningDelta = Signal(str)
    toolCallStart = Signal(str, str, dict)        # id, name, input
    toolCallResult = Signal(str, str, bool)        # id, content, is_error
    turnComplete = Signal(object)                  # AssistantMessage
    agentFinished = Signal()
    conversationCompacted = Signal(int, int)       # pre, post tokens
    permissionRequired = Signal(str, object, dict)  # id, Tool, input
    errorOccurred = Signal(str)

    def __init__(
        self,
        provider,          # type: ModelProvider
        tool_registry,     # type: ToolRegistry
        permission_engine,  # type: PermissionEngine
        compactor,         # type: ConversationCompactor
        system_prompt="",  # type: str
        max_turns=25,      # type: int
        parent=None,
    ):
        super().__init__(parent)
        self._provider = provider
        self._tool_registry = tool_registry
        self._permission_engine = permission_engine
        self._compactor = compactor
        self._system_prompt = system_prompt
        self._max_turns = max_turns

        self._messages = []  # type: List[Message]
        self._abort_flag = False

        # Permission wait mechanism
        self._perm_mutex = QMutex()
        self._perm_cond = QWaitCondition()
        self._perm_decisions = {}  # type: Dict[str, bool]

    def submit(self, prompt, context_blocks=None):
        # type: (str, Optional[list]) -> None
        """Submit a prompt and start the agent loop."""
        content = []
        if context_blocks:
            for block in context_blocks:
                content.append(block)
        content.append(TextBlock(text=prompt))
        self._messages.append(UserMessage(content=content))
        self._abort_flag = False
        self._perm_decisions.clear()
        self.start()

    def approve_tool(self, tool_call_id):
        # type: (str) -> None
        """Approve a pending tool execution (called from main thread)."""
        self._perm_mutex.lock()
        self._perm_decisions[tool_call_id] = True
        self._perm_cond.wakeAll()
        self._perm_mutex.unlock()

    def deny_tool(self, tool_call_id, message=""):
        # type: (str, str) -> None
        """Deny a pending tool execution (called from main thread)."""
        self._perm_mutex.lock()
        self._perm_decisions[tool_call_id] = False
        self._perm_cond.wakeAll()
        self._perm_mutex.unlock()

    def abort(self):
        # type: () -> None
        """Signal the agent loop to stop."""
        self._abort_flag = True
        # Wake any waiting permission check
        self._perm_mutex.lock()
        self._perm_cond.wakeAll()
        self._perm_mutex.unlock()

    def messages(self):
        # type: () -> List[Message]
        """Return a copy of the conversation history (thread-safe)."""
        return list(self._messages)

    def run(self):
        # type: () -> None
        """Main agent loop -- runs in a dedicated thread."""
        try:
            self._run_loop()
        except Exception as e:
            logger.exception("Agent loop error")
            self.errorOccurred.emit(str(e))
        finally:
            self.agentFinished.emit()

    def _run_loop(self):
        # type: () -> None
        for _turn in range(self._max_turns):
            if self._abort_flag:
                return

            # Check compaction
            if self._compactor.should_compact(self._messages):
                result = self._compactor.compact(self._messages)
                self._messages = [result.boundary, result.summary]
                self.conversationCompacted.emit(
                    result.pre_token_estimate,
                    result.post_token_estimate,
                )

            if self._abort_flag:
                return

            # Stream from provider
            tool_schemas = self._tool_registry.get_tool_schemas() or None
            assistant_msg = self._stream_response(tool_schemas)
            if assistant_msg is None:
                return

            self._messages.append(assistant_msg)
            self.turnComplete.emit(assistant_msg)

            # Check if we need to execute tools
            tool_blocks = [
                b for b in assistant_msg.content
                if isinstance(b, ToolUseBlock)
            ]
            if assistant_msg.stop_reason != "tool_use" or not tool_blocks:
                return

            # Execute tools
            tool_results = self._execute_tool_blocks(tool_blocks)
            if tool_results is None:
                return  # aborted

            self._messages.append(
                UserMessage(content=tool_results)
            )

    def _stream_response(self, tool_schemas):
        # type: (Optional[List[Dict[str, Any]]]) -> Optional[AssistantMessage]
        """Stream from the LLM and accumulate into an AssistantMessage."""
        text_parts = []  # type: List[str]
        reasoning_parts = []  # type: List[str]
        tool_calls = {}  # type: Dict[str, Dict[str, Any]]
        stop_reason = None  # type: Optional[str]
        usage = None

        try:
            for event in self._provider.stream(
                messages=self._messages,
                system_prompt=self._system_prompt or None,
                tools=tool_schemas,
            ):
                if self._abort_flag:
                    return None

                if isinstance(event, ContentDelta):
                    text_parts.append(event.text)
                    self.textDelta.emit(event.text)

                elif isinstance(event, ReasoningDelta):
                    reasoning_parts.append(event.text)
                    self.reasoningDelta.emit(event.text)

                elif isinstance(event, ToolCallDelta):
                    if event.id not in tool_calls:
                        tool_calls[event.id] = {
                            "name": event.name,
                            "arguments_parts": [],
                        }
                    tc = tool_calls[event.id]
                    if event.name and not tc["name"]:
                        tc["name"] = event.name
                    tc["arguments_parts"].append(event.arguments_delta)

                elif isinstance(event, MessageComplete):
                    stop_reason = event.stop_reason
                    usage = event.usage

        except Exception as e:
            logger.exception("Provider stream error")
            self.errorOccurred.emit(str(e))
            return None

        # Build content blocks
        content = []  # type: List[Any]
        if text_parts:
            content.append(TextBlock(text="".join(text_parts)))
        for tc_id, tc_data in tool_calls.items():
            args_str = "".join(tc_data["arguments_parts"])
            try:
                args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                args = {}
            content.append(ToolUseBlock(
                id=tc_id, name=tc_data["name"], input=args,
            ))

        return AssistantMessage(
            content=content,
            stop_reason=stop_reason,
            usage=usage,
        )

    def _execute_tool_blocks(self, tool_blocks):
        # type: (List[ToolUseBlock]) -> Optional[List[ToolResultBlock]]
        """Execute tool calls, respecting permissions."""
        results = []  # type: List[ToolResultBlock]
        for block in tool_blocks:
            if self._abort_flag:
                return None

            tool = self._tool_registry.get(block.name)
            if tool is None:
                results.append(ToolResultBlock(
                    tool_use_id=block.id,
                    content="Unknown tool: {}".format(block.name),
                    is_error=True,
                ))
                self.toolCallResult.emit(
                    block.id,
                    "Unknown tool: {}".format(block.name),
                    True,
                )
                continue

            # Permission check
            perm = self._permission_engine.check(tool, block.input)
            if isinstance(perm, PermissionDeny):
                results.append(ToolResultBlock(
                    tool_use_id=block.id,
                    content=perm.message,
                    is_error=True,
                ))
                self.toolCallResult.emit(block.id, perm.message, True)
                continue

            if isinstance(perm, PermissionAsk):
                self.permissionRequired.emit(block.id, tool, block.input)

                # Wait for user decision
                self._perm_mutex.lock()
                while (block.id not in self._perm_decisions
                       and not self._abort_flag):
                    self._perm_cond.wait(self._perm_mutex)
                self._perm_mutex.unlock()

                if self._abort_flag:
                    return None

                if not self._perm_decisions.get(block.id, False):
                    results.append(ToolResultBlock(
                        tool_use_id=block.id,
                        content="Tool execution denied by user",
                        is_error=True,
                    ))
                    self.toolCallResult.emit(
                        block.id, "Tool execution denied by user", True)
                    continue

            # Execute
            self.toolCallStart.emit(block.id, block.name, block.input)
            ctx = ToolContext(
                working_directory=".",
                abort_requested=lambda: self._abort_flag,
            )
            try:
                result = tool.execute(block.input, ctx)
            except Exception as e:
                logger.exception("Tool execution error: %s", block.name)
                result = ToolResult(content=str(e), is_error=True)

            results.append(ToolResultBlock(
                tool_use_id=block.id,
                content=result.content,
                is_error=result.is_error,
            ))
            self.toolCallResult.emit(
                block.id, result.content, result.is_error)

        return results
