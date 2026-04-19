# -*- coding: utf-8 -*-

import unittest
from typing import Any, Dict, Iterator, List, Optional

from PySide6.QtCore import QCoreApplication, QElapsedTimer
from PySide6.QtTest import QSignalSpy

from qgitc.agent.agent_loop import AgentLoop, QueryParams
from qgitc.agent.permissions import PermissionEngine
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ReasoningDelta,
    StreamEvent,
    ToolCallDelta,
)
from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tool_executor import TOOL_ABORTED_MESSAGE, TOOL_SKIPPED_MESSAGE
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import AssistantMessage, TextBlock, ThinkingBlock, UserMessage
from tests.base import TestBase


def waitFor(app, condition, timeout=5000):
    # type: (QCoreApplication, Any, int) -> None
    """Pump processEvents until condition() returns True or timeout."""
    timer = QElapsedTimer()
    timer.start()
    while not condition() and timer.elapsed() < timeout:
        app.processEvents()


def _spy_texts(spy):
    # type: (QSignalSpy) -> str
    """Concatenate all text arguments from a textDelta signal spy."""
    parts = []  # type: List[str]
    for i in range(spy.count()):
        parts.append(spy.at(i)[0])
    return "".join(parts)


# ── Test Providers ──────────────────────────────────────────────────


class SimpleProvider(ModelProvider):
    """Yields a fixed text response then completes."""

    def __init__(self):
        self.last_system_prompt = None

    def stream(self, messages, tools=None,
               model=None, max_tokens=4096):
        # type: (...) -> Iterator[StreamEvent]
        yield ContentDelta(text="Hello from LLM")
        yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        # type: (...) -> int
        return 10


class ReasoningProvider(ModelProvider):
    """Yields reasoning, then text, then completes."""

    def stream(self, messages, tools=None,
               model=None, max_tokens=4096):
        # type: (...) -> Iterator[StreamEvent]
        yield ReasoningDelta(
            text="Let me think about this...",
            reasoning_data={"id": "rs_123", "encrypted_content": "enc=="},
        )
        yield ContentDelta(text="Hello from LLM")
        yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        # type: (...) -> int
        return 10


class ToolCallProvider(ModelProvider):
    """First call yields a tool call, second call yields text."""

    def __init__(self):
        self._call_count = 0

    def stream(self, messages, tools=None,
               model=None, max_tokens=4096):
        # type: (...) -> Iterator[StreamEvent]
        self._call_count += 1
        if self._call_count == 1:
            yield ToolCallDelta(
                id="call_1",
                name="echo",
                arguments_delta='{"text":"ping"}',
            )
            yield MessageComplete(stop_reason="tool_use")
        else:
            yield ContentDelta(text="Tool returned: pong")
            yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        # type: (...) -> int
        return 10


class TwoReadOnlyToolCallsProvider(ModelProvider):
    """First call yields two tool calls, second call yields text."""

    def __init__(self):
        self._call_count = 0

    def stream(self, messages, tools=None,
               model=None, max_tokens=4096):
        # type: (...) -> Iterator[StreamEvent]
        self._call_count += 1
        if self._call_count == 1:
            yield ToolCallDelta(
                id="c1",
                name="sleep_echo",
                arguments_delta='{"text":"first","delay":0.05}',
            )
            yield ToolCallDelta(
                id="c2",
                name="sleep_echo",
                arguments_delta='{"text":"second","delay":0.01}',
            )
            yield MessageComplete(stop_reason="tool_use")
        else:
            yield ContentDelta(text="done")
            yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        # type: (...) -> int
        return 10


class AskPermissionToolCallProvider(ModelProvider):
    """First call yields a write tool call, second call yields text."""

    def __init__(self):
        self._call_count = 0

    @property
    def call_count(self):
        # type: () -> int
        return self._call_count

    def stream(self, messages, tools=None,
               model=None, max_tokens=4096):
        # type: (...) -> Iterator[StreamEvent]
        self._call_count += 1
        if self._call_count == 1:
            yield ToolCallDelta(
                id="ask_1",
                name="write_echo",
                arguments_delta='{"text":"ping"}',
            )
            yield MessageComplete(stop_reason="tool_use")
        else:
            yield ContentDelta(text="continuation after tool")
            yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        # type: (...) -> int
        return 10


class MultipleToolsWithDelaysProvider(ModelProvider):
    """Yields multiple concurrent tools with different delays."""

    def __init__(self):
        self._call_count = 0

    def stream(self, messages, tools=None,
               model=None, max_tokens=4096):
        # type: (...) -> Iterator[StreamEvent]
        self._call_count += 1
        if self._call_count == 1:
            # First tool: quick read-only (finishes fast)
            yield ToolCallDelta(
                id="multi_1",
                name="sleep_echo",
                arguments_delta='{"text":"first","delay":0.01}',
            )
            # Second tool: slower read-only (medium delay)
            yield ToolCallDelta(
                id="multi_2",
                name="sleep_echo",
                arguments_delta='{"text":"second","delay":0.1}',
            )
            # Third tool: write tool (requires permission)
            yield ToolCallDelta(
                id="multi_3",
                name="write_echo",
                arguments_delta='{"text":"third"}',
            )
            yield MessageComplete(stop_reason="tool_use")
        else:
            yield ContentDelta(text="all tools completed")
            yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        # type: (...) -> int
        return 10


class ErrorProvider(ModelProvider):
    """Raises an exception from stream()."""

    def stream(self, messages, tools=None,
               model=None, max_tokens=4096):
        # type: (...) -> Iterator[StreamEvent]
        _ = (messages, tools, model, max_tokens)
        raise RuntimeError("connection dropped")
        yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        # type: (...) -> int
        return 10


# ── Test Tool ───────────────────────────────────────────────────────


class EchoTool(Tool):
    name = "echo"
    description = "Echoes back a fixed response"

    def is_read_only(self):
        # type: () -> bool
        return True

    def execute(self, input_data, context):
        # type: (Dict[str, Any], ToolContext) -> ToolResult
        return ToolResult(content="pong")

    def input_schema(self):
        # type: () -> Dict[str, Any]
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
        }


class SleepEchoTool(Tool):
    name = "sleep_echo"
    description = "Returns supplied text after an optional delay"

    def is_read_only(self):
        # type: () -> bool
        return True

    def execute(self, input_data, context):
        # type: (Dict[str, Any], ToolContext) -> ToolResult
        import time

        time.sleep(float(input_data.get("delay", 0)))
        return ToolResult(content=str(input_data.get("text", "")))

    def input_schema(self):
        # type: () -> Dict[str, Any]
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "delay": {"type": "number"},
            },
        }


class WriteEchoTool(Tool):
    name = "write_echo"
    description = "Echoes supplied text as a write tool"

    def execute(self, input_data, context):
        # type: (Dict[str, Any], ToolContext) -> ToolResult
        return ToolResult(content=str(input_data.get("text", "")))

    def input_schema(self):
        # type: () -> Dict[str, Any]
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
        }


# ── Helpers ─────────────────────────────────────────────────────────


def _make_loop(provider, registry=None):
    # type: (ModelProvider, Optional[ToolRegistry]) -> AgentLoop
    if registry is None:
        registry = ToolRegistry()
    engine = PermissionEngine()
    return AgentLoop(tool_registry=registry, permission_engine=engine)


def _make_params(provider):
    # type: (ModelProvider) -> QueryParams
    return QueryParams(
        provider=provider,
        context_window=100000,
        max_output_tokens=4096,
    )


# ── Simple Tests ────────────────────────────────────────────────────


class TestAgentLoopSimple(TestBase):

    def setUp(self):
        super().setUp()
        self.provider = SimpleProvider()
        self.loop = _make_loop(self.provider)
        self.params = _make_params(self.provider)

    def tearDown(self):
        self.loop.abort()
        self.loop.wait(3000)
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_simple_text_response(self):
        text_spy = QSignalSpy(self.loop.textDelta)
        finished_spy = QSignalSpy(self.loop.agentFinished)
        turn_spy = QSignalSpy(self.loop.turnComplete)

        self.loop.submit("Hello", self.params)
        waitFor(self.app, lambda: finished_spy.count() > 0)

        # textDelta should have been emitted with "Hello from LLM"
        self.assertGreater(text_spy.count(), 0)
        texts = _spy_texts(text_spy)
        self.assertEqual(texts, "Hello from LLM")

        # turnComplete emitted exactly once
        self.assertEqual(turn_spy.count(), 1)

    def test_messages_accumulate(self):
        finished_spy = QSignalSpy(self.loop.agentFinished)

        self.loop.submit("Hello", self.params)
        waitFor(self.app, lambda: finished_spy.count() > 0)

        msgs = self.loop.messages()
        self.assertEqual(len(msgs), 2)
        self.assertIsInstance(msgs[0], UserMessage)
        self.assertIsInstance(msgs[1], AssistantMessage)

    def test_submit_accepts_content_blocks(self):
        finished_spy = QSignalSpy(self.loop.agentFinished)

        self.loop.submit([TextBlock(text="Hello")], self.params)
        waitFor(self.app, lambda: finished_spy.count() > 0)

        msgs = self.loop.messages()
        self.assertEqual(len(msgs), 2)
        self.assertIsInstance(msgs[0], UserMessage)
        self.assertEqual(msgs[0].content[0].text, "Hello")

    def test_abort(self):
        self.loop.submit("Hello", self.params)
        self.loop.abort()
        self.loop.wait(3000)
        self.assertFalse(self.loop.isRunning())


class TestAgentLoopReasoning(TestBase):

    def setUp(self):
        super().setUp()
        self.provider = ReasoningProvider()
        self.loop = _make_loop(self.provider)
        self.params = _make_params(self.provider)

    def tearDown(self):
        self.loop.abort()
        self.loop.wait(3000)
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_reasoning_is_stored_in_assistant_message(self):
        finished_spy = QSignalSpy(self.loop.agentFinished)
        turn_spy = QSignalSpy(self.loop.turnComplete)
        reasoning_spy = QSignalSpy(self.loop.reasoningDelta)

        self.loop.submit("Hello", self.params)
        waitFor(self.app, lambda: finished_spy.count() > 0)

        self.assertEqual(reasoning_spy.count(), 1)
        self.assertEqual(reasoning_spy.at(0)[0], "Let me think about this...")
        self.assertEqual(turn_spy.count(), 1)

        assistant_msg = turn_spy.at(0)[0]
        thinking_blocks = [
            block for block in assistant_msg.content
            if isinstance(block, ThinkingBlock)
        ]
        self.assertEqual(len(thinking_blocks), 1)
        self.assertEqual(thinking_blocks[0].thinking, "Let me think about this...")
        self.assertEqual(
            thinking_blocks[0].reasoning_data,
            {"id": "rs_123", "encrypted_content": "enc=="},
        )


# ── Tool Execution Tests ────────────────────────────────────────────


class TestAgentLoopToolExecution(TestBase):

    def setUp(self):
        super().setUp()
        self.registry = ToolRegistry()
        self.registry.register(EchoTool())
        self.provider = ToolCallProvider()
        self.loop = _make_loop(self.provider, registry=self.registry)
        self.params = _make_params(self.provider)

    def tearDown(self):
        self.loop.abort()
        self.loop.wait(3000)
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_tool_call_and_continuation(self):
        finished_spy = QSignalSpy(self.loop.agentFinished)
        tool_start_spy = QSignalSpy(self.loop.toolCallStart)
        tool_result_spy = QSignalSpy(self.loop.toolCallResult)
        text_spy = QSignalSpy(self.loop.textDelta)

        self.loop.submit("Please echo", self.params)
        waitFor(self.app, lambda: finished_spy.count() > 0)

        # Tool was called
        self.assertEqual(tool_start_spy.count(), 1)
        self.assertEqual(tool_start_spy.at(0)[1], "echo")  # tool name

        # Tool result was returned
        self.assertEqual(tool_result_spy.count(), 1)
        self.assertEqual(tool_result_spy.at(0)[0], "call_1")  # tool_call_id

        # Final text response after tool
        self.assertGreater(text_spy.count(), 0)

    def test_messages_include_tool_round(self):
        finished_spy = QSignalSpy(self.loop.agentFinished)

        self.loop.submit("Please echo", self.params)
        waitFor(self.app, lambda: finished_spy.count() > 0)

        msgs = self.loop.messages()
        # UserMessage, AssistantMessage(tool_use), UserMessage(tool_result),
        # AssistantMessage(text)
        self.assertEqual(len(msgs), 4)

    def test_two_read_only_tool_calls_emit_two_results_in_order(self):
        registry = ToolRegistry()
        registry.register(SleepEchoTool())
        provider = TwoReadOnlyToolCallsProvider()
        loop = _make_loop(provider, registry=registry)
        params = _make_params(provider)

        finished_spy = QSignalSpy(loop.agentFinished)
        callresult_spy = QSignalSpy(loop.toolCallResult)
        events = []

        loop.toolCallStart.connect(lambda call_id, name, data: events.append(("start", call_id)))
        loop.toolCallResult.connect(lambda call_id, name, content, is_error: events.append(("result", call_id, content, is_error)))

        loop.submit("Run two tools", params)
        waitFor(self.app, lambda: finished_spy.count()
                > 0 and callresult_spy.count() >= 2)
        waitFor(self.app, lambda: sum(
            1 for e in events if e[0] == "result") >= 2)

        result_events = [e for e in events if e[0] == "result"]
        self.assertEqual([e[1] for e in result_events], ["c1", "c2"])
        self.assertEqual([e[2] for e in result_events], ["first", "second"])
        self.assertFalse(result_events[0][3])
        self.assertFalse(result_events[1][3])

        self.assertGreaterEqual(len(events), 4)
        self.assertEqual(events[0], ("start", "c1"))
        self.assertEqual(events[1], ("start", "c2"))
        self.assertEqual(events[2][0], "result")
        self.assertEqual(events[2][1], "c1")
        self.assertEqual(events[3][0], "result")
        self.assertEqual(events[3][1], "c2")

        loop.abort()
        loop.wait(3000)

    def test_permission_ask_user_denied_emits_error_result_once(self):
        registry = ToolRegistry()
        registry.register(WriteEchoTool())
        provider = AskPermissionToolCallProvider()
        loop = _make_loop(provider, registry=registry)
        params = _make_params(provider)

        permission_spy = QSignalSpy(loop.permissionRequired)
        tool_result_spy = QSignalSpy(loop.toolCallResult)
        finished_spy = QSignalSpy(loop.agentFinished)

        loop.permissionRequired.connect(lambda tool_call_id, tool, tool_input: loop.deny_tool(tool_call_id))

        loop.submit("Run write tool", params)
        waitFor(self.app, lambda: finished_spy.count() > 0)

        self.assertEqual(permission_spy.count(), 1)
        self.assertEqual(tool_result_spy.count(), 1)
        self.assertEqual(tool_result_spy.at(0)[0], "ask_1")
        self.assertEqual(tool_result_spy.at(0)[2], TOOL_SKIPPED_MESSAGE)
        self.assertTrue(tool_result_spy.at(0)[3])

        loop.abort()
        loop.wait(3000)

    def test_abort_while_waiting_for_permission_does_not_continue(self):
        registry = ToolRegistry()
        registry.register(WriteEchoTool())
        provider = AskPermissionToolCallProvider()
        loop = _make_loop(provider, registry=registry)
        params = _make_params(provider)

        permission_spy = QSignalSpy(loop.permissionRequired)
        tool_result_spy = QSignalSpy(loop.toolCallResult)
        finished_spy = QSignalSpy(loop.agentFinished)
        text_spy = QSignalSpy(loop.textDelta)

        loop.submit("Run write tool", params)
        waitFor(self.app, lambda: permission_spy.count() > 0)
        loop.abort()
        waitFor(self.app, lambda: finished_spy.count() > 0)

        self.assertEqual(permission_spy.count(), 1)
        self.assertEqual(tool_result_spy.count(), 1)
        self.assertEqual(text_spy.count(), 0)
        self.assertEqual(provider.call_count, 1)

        msgs = loop.messages()
        self.assertEqual(len(msgs), 3)
        self.assertIsInstance(msgs[2], UserMessage)
        self.assertEqual(len(msgs[2].content), 1)
        self.assertEqual(msgs[2].content[0].tool_use_id, "ask_1")
        self.assertEqual(msgs[2].content[0].content, TOOL_ABORTED_MESSAGE)
        self.assertTrue(msgs[2].content[0].is_error)

        loop.wait(3000)

    def test_abort_during_concurrent_tools_preserves_partial_results(self):
        # Comprehensive test: multiple concurrent tools with different states when abort occurs
        registry = ToolRegistry()
        registry.register(SleepEchoTool())
        registry.register(WriteEchoTool())
        provider = MultipleToolsWithDelaysProvider()
        loop = _make_loop(provider, registry=registry)
        params = _make_params(provider)

        permission_spy = QSignalSpy(loop.permissionRequired)
        tool_result_spy = QSignalSpy(loop.toolCallResult)
        finished_spy = QSignalSpy(loop.agentFinished)
        
        # Auto-approve permission requests so all tools can execute
        loop.permissionRequired.connect(lambda tool_call_id, tool, tool_input: loop.approve_tool(tool_call_id))

        loop.submit("Run multiple tools", params)
        # Wait for tools to start executing
        waitFor(self.app, lambda: tool_result_spy.count() >= 1)
        # Abort while some tools are still running
        loop.abort()
        waitFor(self.app, lambda: finished_spy.count() > 0)

        msgs = loop.messages()
        # Must have at least 3 messages: user input, assistant (tool calls), tool results
        self.assertGreaterEqual(len(msgs), 3)
        
        # Last message should be UserMessage with tool results (not dropped even though aborted)
        self.assertIsInstance(msgs[-1], UserMessage)
        
        # Should have at least some tool result blocks from tools that did complete before abort
        tool_results = msgs[-1].content
        self.assertGreater(len(tool_results), 0, "Tool results should be preserved even after abort")
        
        # Each result should be a ToolResultBlock with tool_use_id
        for result_block in tool_results:
            self.assertTrue(hasattr(result_block, 'tool_use_id'))
            self.assertIn(result_block.tool_use_id, ["multi_1", "multi_2", "multi_3"])

        loop.wait(3000)


class TestAgentLoopSetMessages(TestBase):

    def setUp(self):
        super().setUp()
        self.provider = SimpleProvider()
        self.loop = _make_loop(self.provider)
        self.params = _make_params(self.provider)

    def tearDown(self):
        self.loop.abort()
        self.loop.wait(3000)
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_set_messages(self):
        msgs = [
            UserMessage(content=[TextBlock(text="Hello")]),
            AssistantMessage(content=[TextBlock(text="Hi")]),
        ]
        self.loop.set_messages(msgs)
        result = self.loop.messages()
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], UserMessage)
        self.assertIsInstance(result[1], AssistantMessage)

    def test_set_messages_copies(self):
        msgs = [UserMessage(content=[TextBlock(text="Hello")])]
        self.loop.set_messages(msgs)
        msgs.append(UserMessage(content=[TextBlock(text="World")]))
        self.assertEqual(len(self.loop.messages()), 1)


class TestAgentLoopErrors(TestBase):

    def setUp(self):
        super().setUp()
        self.provider = ErrorProvider()
        self.loop = _make_loop(self.provider)
        self.params = _make_params(self.provider)

    def tearDown(self):
        self.loop.abort()
        self.loop.wait(3000)
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_provider_exception_emits_errorOccurred(self):
        error_spy = QSignalSpy(self.loop.errorOccurred)
        finished_spy = QSignalSpy(self.loop.agentFinished)

        self.loop.submit("Hello", self.params)
        waitFor(self.app, lambda: finished_spy.count() > 0)

        self.assertEqual(error_spy.count(), 1)
        self.assertIn("connection dropped", error_spy.at(0)[0])


if __name__ == "__main__":
    unittest.main()
