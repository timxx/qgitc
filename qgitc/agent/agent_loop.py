# -*- coding: utf-8 -*-

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal

from qgitc.agent.compaction import ConversationCompactor
from qgitc.agent.permissions import PermissionEngine
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ReasoningDelta,
    ToolCallDelta,
)
from qgitc.agent.skills.registry import SkillRegistry
from qgitc.agent.tool import ToolContext
from qgitc.agent.tool_executor import executeToolBlocks
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import (
    AssistantMessage,
    ContentBlock,
    Message,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from qgitc.gitutils import Git

logger = logging.getLogger(__name__)


@dataclass
class QueryParams:
    provider: ModelProvider
    context_window: int = 100000
    max_output_tokens: int = 4096
    skill_registry: Optional[SkillRegistry] = None


class AgentLoop(QThread):
    """Orchestrates the LLM agent loop in a dedicated thread.

    Communicates with the main thread via Qt signals.
    """

    textDelta = Signal(str)
    reasoningDelta = Signal(str)
    toolCallStart = Signal(str, str, dict)        # id, name, input
    # id, name, content, is_error
    toolCallResult = Signal(str, str, str, bool)
    turnComplete = Signal(object)                  # AssistantMessage
    agentFinished = Signal()
    conversationCompacted = Signal(int, int)       # pre, post tokens
    permissionRequired = Signal(str, object, dict)  # id, Tool, input
    errorOccurred = Signal(str)

    def __init__(
        self,
        tool_registry,     # type: ToolRegistry
        permission_engine,  # type: PermissionEngine
        max_turns=25,      # type: int
        system_prompt=None,  # type: str
        parent=None,
    ):
        super().__init__(parent)
        self._tool_registry = tool_registry
        self._permission_engine = permission_engine
        self._max_turns = max_turns
        self._params = None  # type: Optional[QueryParams]
        self._system_prompt = system_prompt

        self._messages = []  # type: List[Message]
        self._abort_flag = False
        self._context_extra_state = {}  # type: Dict[str, Any]

        # Permission wait mechanism
        self._perm_mutex = QMutex()
        self._perm_cond = QWaitCondition()
        self._perm_decisions = {}  # type: Dict[str, bool]

    def submit(self, prompt, params):
        # type: (Union[str, List[ContentBlock]], QueryParams) -> None
        """Submit a prompt and start the agent loop."""
        if isinstance(prompt, str):
            content = [TextBlock(text=prompt)]
        else:
            content = list(prompt)

        if self._system_prompt and len(self._messages) == 0:
            self._messages.append(SystemMessage(content=self._system_prompt))

        self._messages.append(UserMessage(content=content))
        self._params = params
        self._abort_flag = False
        self._perm_decisions.clear()
        self._context_extra_state = {
            "tool_allowed_tools": None,
            "skill_registry": params.skill_registry,
        }
        self.start()

    def approveTool(self, tool_call_id):
        # type: (str) -> None
        """Approve a pending tool execution (called from main thread)."""
        self._perm_mutex.lock()
        self._perm_decisions[tool_call_id] = True
        self._perm_cond.wakeAll()
        self._perm_mutex.unlock()

    def denyTool(self, tool_call_id, message=""):
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

    def setMessages(self, messages):
        # type: (List[Message]) -> None
        """Replace conversation history (call before submit, not while running)."""
        self._messages = list(messages)

    def getSystemPrompt(self):
        # type: () -> Optional[str]
        """Return the system prompt if set."""
        return self._system_prompt

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
        if self._params is None:
            raise ValueError("submit() requires QueryParams")

        params = self._params
        compactor = ConversationCompactor(
            params.provider,
            params.context_window,
            params.max_output_tokens,
        )

        for _ in range(self._max_turns):
            if self._abort_flag:
                return

            # Check compaction
            if compactor.shouldCompact(self._messages):
                result = compactor.compact(self._messages)
                self._messages = [result.boundary, result.summary]
                self.conversationCompacted.emit(
                    result.pre_token_estimate,
                    result.post_token_estimate,
                )

            if self._abort_flag:
                return

            # Stream from provider
            tool_schemas = self._tool_registry.getToolSchemas() or None

            assistant_msg = self._stream_response(
                params.provider,
                tool_schemas,
            )
            if assistant_msg is None:
                return

            self._messages.append(assistant_msg)
            self.turnComplete.emit(assistant_msg)

            if assistant_msg.stop_reason != "tool_use":
                return

            # Check if we need to execute tools
            tool_blocks = [
                b for b in assistant_msg.content
                if isinstance(b, ToolUseBlock)
            ]
            if not tool_blocks:
                return

            # Execute tools
            tool_results = self._execute_tool_blocks(tool_blocks)

            # Always append tool results, even if aborted (might have partial results)
            if tool_results:
                self._messages.append(
                    UserMessage(content=tool_results)
                )

            prompts: List[str] = self._context_extra_state.pop("tool_queued_prompts", [])
            for prompt in prompts:
                self._messages.append(UserMessage(content=[TextBlock(text=prompt)]))

    def _stream_response(self, provider, tool_schemas):
        # type: (ModelProvider, Optional[List[Dict[str, Any]]]) -> Optional[AssistantMessage]
        """Stream from the LLM and accumulate into an AssistantMessage."""
        text_parts = []  # type: List[str]
        reasoning_parts = []  # type: List[str]
        reasoning_data = None  # type: Optional[Dict[str, Any]]
        tool_calls = {}  # type: Dict[str, Dict[str, Any]]
        stop_reason = None  # type: Optional[str]
        usage = None

        try:
            for event in provider.stream(
                messages=self._messages,
                tools=tool_schemas,
            ):
                if self._abort_flag:
                    return None

                if isinstance(event, ContentDelta):
                    text_parts.append(event.text)
                    self.textDelta.emit(event.text)

                elif isinstance(event, ReasoningDelta):
                    if event.text:
                        reasoning_parts.append(event.text)
                        self.reasoningDelta.emit(event.text)
                    if event.reasoning_data:
                        reasoning_data = event.reasoning_data

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
        if reasoning_parts or reasoning_data:
            content.append(ThinkingBlock(
                thinking="".join(reasoning_parts),
                reasoning_data=reasoning_data,
            ))
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
        if self._params is not None:
            self._context_extra_state["skill_registry"] = self._params.skill_registry

        def requestPermission(tool_call_id, tool, tool_input):
            # type: (str, object, Dict[str, Any]) -> bool
            self.permissionRequired.emit(tool_call_id, tool, tool_input)

            self._perm_mutex.lock()
            while (tool_call_id not in self._perm_decisions
                   and not self._abort_flag):
                self._perm_cond.wait(self._perm_mutex)
            self._perm_mutex.unlock()

            if self._abort_flag:
                return False

            return self._perm_decisions.get(tool_call_id, False)

        def onToolStart(tool_call_id, tool_name, tool_input):
            # type: (str, str, Dict[str, Any]) -> None
            self.toolCallStart.emit(tool_call_id, tool_name, tool_input)

        def onToolResult(tool_call_id, tool_name, content, is_error):
            # type: (str, str, str, bool) -> None
            self.toolCallResult.emit(tool_call_id, tool_name, content, is_error)

        context = ToolContext(
            working_directory=Git.REPO_DIR or os.getcwd(),
            abort_requested=lambda: self._abort_flag,
            extra=self._context_extra_state,
        )

        results = executeToolBlocks(
            tool_blocks=tool_blocks,
            registry=self._tool_registry,
            permission_engine=self._permission_engine,
            context=context,
            is_aborted=lambda: self._abort_flag,
            requestPermission=requestPermission,
            onToolStart=onToolStart,
            onToolResult=onToolResult,
        )

        return results
