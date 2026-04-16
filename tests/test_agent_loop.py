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
    StreamEvent,
    ToolCallDelta,
)
from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import AssistantMessage, TextBlock, UserMessage
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
