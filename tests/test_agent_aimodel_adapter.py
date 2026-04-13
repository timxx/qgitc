# -*- coding: utf-8 -*-

import unittest
from typing import Any, List, Optional, Tuple

from PySide6.QtCore import QTimer

from qgitc.agent.aimodel_adapter import AiModelBaseAdapter
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ReasoningDelta,
    ToolCallDelta,
)
from qgitc.agent.types import TextBlock, UserMessage
from qgitc.llm import AiChatMode, AiModelBase, AiParameters, AiResponse, AiRole
from tests.base import TestBase


class FakeAiModel(AiModelBase):
    """A fake AiModelBase that emits pre-configured AiResponse objects."""

    def __init__(self, responses, parent=None):
        # type: (List[AiResponse], Optional[Any]) -> None
        super().__init__("http://fake", model="fake", parent=parent)
        self._responses = responses
        self._index = 0
        self.last_params = None  # type: Optional[AiParameters]

    def queryAsync(self, params):
        # type: (AiParameters) -> None
        self.last_params = params
        self._index = 0
        QTimer.singleShot(10, self._emitNext)

    def _emitNext(self):
        # type: () -> None
        if self._index < len(self._responses):
            self.responseAvailable.emit(self._responses[self._index])
            self._index += 1
            if self._index < len(self._responses):
                QTimer.singleShot(10, self._emitNext)
            else:
                QTimer.singleShot(10, self._emitFinished)
        else:
            self._emitFinished()

    def _emitFinished(self):
        # type: () -> None
        self.finished.emit()

    def models(self):
        # type: () -> List[Tuple[str, str]]
        return [("fake", "Fake")]

    def supportsToolCalls(self, modelId="fake"):
        # type: (str) -> bool
        return True


class TestStreamTextResponse(TestBase):

    def doCreateRepo(self):
        pass

    def test_stream_text_response(self):
        responses = [
            AiResponse(
                role=AiRole.Assistant,
                message="Hello",
                is_delta=True,
                first_delta=True,
            ),
            AiResponse(
                role=AiRole.Assistant,
                message=" world",
                is_delta=True,
                first_delta=False,
            ),
        ]
        model = FakeAiModel(responses)
        adapter = AiModelBaseAdapter(
            model=model,
            modelId="fake",
            max_tokens=4096,
            temperature=0.0,
            chat_mode=AiChatMode.Chat,
        )

        messages = [UserMessage(content=[TextBlock(text="Hi")])]
        events = list(adapter.stream(messages))

        # Should have 2 ContentDelta + 1 MessageComplete
        self.assertEqual(len(events), 3)
        self.assertIsInstance(events[0], ContentDelta)
        self.assertEqual(events[0].text, "Hello")
        self.assertIsInstance(events[1], ContentDelta)
        self.assertEqual(events[1].text, " world")
        self.assertIsInstance(events[2], MessageComplete)
        self.assertEqual(events[2].stop_reason, "end_turn")


class TestStreamToolCallResponse(TestBase):

    def doCreateRepo(self):
        pass

    def test_stream_tool_call_response(self):
        responses = [
            AiResponse(
                role=AiRole.Assistant,
                message="Let me read that file.",
                is_delta=True,
                first_delta=True,
            ),
            AiResponse(
                role=AiRole.Assistant,
                is_delta=False,
                first_delta=False,
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "/tmp/test.txt"}',
                    },
                }],
            ),
        ]
        model = FakeAiModel(responses)
        adapter = AiModelBaseAdapter(
            model=model,
            modelId="fake",
            max_tokens=4096,
            temperature=0.0,
            chat_mode=AiChatMode.Agent,
        )

        messages = [UserMessage(
            content=[TextBlock(text="Read /tmp/test.txt")])]
        events = list(adapter.stream(messages))

        # ContentDelta, ToolCallDelta, MessageComplete
        self.assertEqual(len(events), 3)
        self.assertIsInstance(events[0], ContentDelta)
        self.assertEqual(events[0].text, "Let me read that file.")
        self.assertIsInstance(events[1], ToolCallDelta)
        self.assertEqual(events[1].id, "call_123")
        self.assertEqual(events[1].name, "read_file")
        self.assertEqual(events[1].arguments_delta,
                         '{"path": "/tmp/test.txt"}')
        self.assertIsInstance(events[2], MessageComplete)
        self.assertEqual(events[2].stop_reason, "tool_use")


class TestStreamReasoning(TestBase):

    def doCreateRepo(self):
        pass

    def test_stream_reasoning(self):
        responses = [
            AiResponse(
                role=AiRole.Assistant,
                reasoning="Let me think about this...",
                is_delta=True,
                first_delta=True,
            ),
            AiResponse(
                role=AiRole.Assistant,
                message="The answer is 42.",
                is_delta=True,
                first_delta=False,
            ),
        ]
        model = FakeAiModel(responses)
        adapter = AiModelBaseAdapter(
            model=model,
            modelId="fake",
            max_tokens=4096,
            temperature=0.0,
            chat_mode=AiChatMode.Chat,
        )

        messages = [UserMessage(
            content=[TextBlock(text="What is the answer?")])]
        events = list(adapter.stream(messages))

        # ReasoningDelta, ContentDelta, MessageComplete
        self.assertEqual(len(events), 3)
        self.assertIsInstance(events[0], ReasoningDelta)
        self.assertEqual(events[0].text, "Let me think about this...")
        self.assertIsInstance(events[1], ContentDelta)
        self.assertEqual(events[1].text, "The answer is 42.")
        self.assertIsInstance(events[2], MessageComplete)
        self.assertEqual(events[2].stop_reason, "end_turn")


class TestStreamParameters(TestBase):

    def doCreateRepo(self):
        pass

    def test_constructor_threads_temperature_and_max_tokens(self):
        model = FakeAiModel([])
        adapter = AiModelBaseAdapter(
            model=model,
            modelId="fake",
            max_tokens=1234,
            temperature=0.7,
            chat_mode=AiChatMode.Chat,
        )

        messages = [UserMessage(content=[TextBlock(text="Hi")])]
        list(adapter.stream(messages))

        self.assertIsNotNone(model.last_params)
        self.assertEqual(model.last_params.temperature, 0.7)
        self.assertEqual(model.last_params.max_tokens, 1234)
        self.assertTrue(model.last_params.continue_only)

    def test_stream_rejects_legacy_kwargs(self):
        model = FakeAiModel([])
        adapter = AiModelBaseAdapter(
            model=model,
            modelId="fake",
            max_tokens=321,
            temperature=0.2,
            chat_mode=AiChatMode.Chat,
        )

        messages = [UserMessage(content=[TextBlock(text="Hi")])]
        with self.assertRaises(TypeError):
            list(adapter.stream(messages, model="legacy", max_tokens=9999))

    def test_stream_twice_no_duplicate_event_leakage(self):
        responses = [
            AiResponse(
                role=AiRole.Assistant,
                message="only-once",
                is_delta=True,
                first_delta=True,
            ),
        ]
        model = FakeAiModel(responses)
        adapter = AiModelBaseAdapter(
            model=model,
            modelId="fake",
            max_tokens=100,
            temperature=0.0,
            chat_mode=AiChatMode.Chat,
        )

        messages = [UserMessage(content=[TextBlock(text="Hi")])]
        events_first = list(adapter.stream(messages))
        events_second = list(adapter.stream(messages))

        self.assertEqual(len(events_first), 2)
        self.assertEqual(len(events_second), 2)
        self.assertIsInstance(events_first[0], ContentDelta)
        self.assertIsInstance(events_second[0], ContentDelta)
        self.assertEqual(events_first[0].text, "only-once")
        self.assertEqual(events_second[0].text, "only-once")
        self.assertIsInstance(events_first[1], MessageComplete)
        self.assertIsInstance(events_second[1], MessageComplete)

    def test_max_tokens_none_remains_unset(self):
        model = FakeAiModel([])
        adapter = AiModelBaseAdapter(
            model=model,
            modelId="fake",
            max_tokens=None,
            temperature=0.0,
            chat_mode=AiChatMode.Chat,
        )

        messages = [UserMessage(content=[TextBlock(text="Hi")])]
        list(adapter.stream(messages))

        self.assertIsNotNone(model.last_params)
        self.assertIsNone(getattr(model.last_params, "max_tokens", None))

    def test_tools_omitted_when_not_agent_mode(self):
        model = FakeAiModel([])
        adapter = AiModelBaseAdapter(
            model=model,
            modelId="fake",
            max_tokens=100,
            temperature=0.0,
            chat_mode=AiChatMode.Chat,
        )

        messages = [UserMessage(content=[TextBlock(text="Hi")])]
        tools = [{"type": "function", "function": {"name": "read_file"}}]
        list(adapter.stream(messages, tools=tools))

        self.assertIsNotNone(model.last_params)
        self.assertFalse(hasattr(model.last_params, "tools") and model.last_params.tools)
        self.assertFalse(hasattr(model.last_params, "tool_choice") and model.last_params.tool_choice)

    def test_tools_preserved_when_agent_mode(self):
        model = FakeAiModel([])
        adapter = AiModelBaseAdapter(
            model=model,
            modelId="fake",
            max_tokens=100,
            temperature=0.0,
            chat_mode=AiChatMode.Agent,
        )

        messages = [UserMessage(content=[TextBlock(text="Hi")])]
        tools = [{"type": "function", "function": {"name": "read_file"}}]
        list(adapter.stream(messages, tools=tools))

        self.assertIsNotNone(model.last_params)
        self.assertEqual(model.last_params.tools, tools)
        self.assertEqual(model.last_params.tool_choice, "auto")


if __name__ == "__main__":
    unittest.main()
