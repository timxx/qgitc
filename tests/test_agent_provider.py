# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ReasoningDelta,
    StreamEvent,
    ToolCallDelta,
)
from qgitc.agent.types import Message, TextBlock, Usage, UserMessage


class FakeProvider(ModelProvider):
    """Concrete implementation for testing the ABC."""

    def __init__(self, events=None, token_count=0):
        self._events = events or []
        self._token_count = token_count

    def stream(self, messages, tools=None,
               model=None, max_tokens=4096):
        for event in self._events:
            yield event

    def count_tokens(self, messages, system_prompt=None, tools=None):
        return self._token_count


class TestContentDelta(unittest.TestCase):
    def test_creation_and_field_access(self):
        delta = ContentDelta(text="hello")
        self.assertEqual(delta.text, "hello")

    def test_isinstance(self):
        delta = ContentDelta(text="hi")
        self.assertIsInstance(delta, ContentDelta)


class TestReasoningDelta(unittest.TestCase):
    def test_creation_and_field_access(self):
        delta = ReasoningDelta(text="thinking...")
        self.assertEqual(delta.text, "thinking...")

    def test_isinstance(self):
        delta = ReasoningDelta(text="hmm")
        self.assertIsInstance(delta, ReasoningDelta)


class TestToolCallDelta(unittest.TestCase):
    def test_creation_and_field_access(self):
        delta = ToolCallDelta(id="tc1", name="read_file",
                              arguments_delta='{"path":')
        self.assertEqual(delta.id, "tc1")
        self.assertEqual(delta.name, "read_file")
        self.assertEqual(delta.arguments_delta, '{"path":')

    def test_isinstance(self):
        delta = ToolCallDelta(id="tc1", name="read_file",
                              arguments_delta="")
        self.assertIsInstance(delta, ToolCallDelta)


class TestMessageComplete(unittest.TestCase):
    def test_creation_without_usage(self):
        mc = MessageComplete(stop_reason="end_turn")
        self.assertEqual(mc.stop_reason, "end_turn")
        self.assertIsNone(mc.usage)

    def test_creation_with_usage(self):
        usage = Usage(input_tokens=100, output_tokens=200)
        mc = MessageComplete(stop_reason="end_turn", usage=usage)
        self.assertEqual(mc.stop_reason, "end_turn")
        self.assertEqual(mc.usage.input_tokens, 100)
        self.assertEqual(mc.usage.output_tokens, 200)

    def test_isinstance(self):
        mc = MessageComplete(stop_reason="end_turn")
        self.assertIsInstance(mc, MessageComplete)


class TestStreamEventUnion(unittest.TestCase):
    """StreamEvent is a Union type alias; check each concrete type."""

    _concrete_types = (ContentDelta, ReasoningDelta, ToolCallDelta,
                       MessageComplete)

    def test_content_delta_isinstance(self):
        event = ContentDelta(text="hi")
        self.assertIsInstance(event, self._concrete_types)

    def test_reasoning_delta_isinstance(self):
        event = ReasoningDelta(text="hmm")
        self.assertIsInstance(event, self._concrete_types)

    def test_tool_call_delta_isinstance(self):
        event = ToolCallDelta(id="t1", name="x", arguments_delta="")
        self.assertIsInstance(event, self._concrete_types)

    def test_message_complete_isinstance(self):
        event = MessageComplete(stop_reason="stop")
        self.assertIsInstance(event, self._concrete_types)


class TestModelProviderAbstract(unittest.TestCase):
    def test_cannot_instantiate(self):
        with self.assertRaises(TypeError):
            ModelProvider()


class TestFakeProvider(unittest.TestCase):
    def test_stream_yields_correct_events(self):
        events = [
            ContentDelta(text="Hello"),
            ContentDelta(text=" world"),
            ToolCallDelta(id="tc1", name="read_file",
                          arguments_delta='{"path": "/tmp"}'),
            MessageComplete(stop_reason="end_turn",
                            usage=Usage(input_tokens=10,
                                        output_tokens=20)),
        ]
        provider = FakeProvider(events=events)
        messages = [UserMessage(content=[TextBlock(text="hi")])]
        result = list(provider.stream(messages))
        self.assertEqual(len(result), 4)
        self.assertIsInstance(result[0], ContentDelta)
        self.assertEqual(result[0].text, "Hello")
        self.assertIsInstance(result[1], ContentDelta)
        self.assertEqual(result[1].text, " world")
        self.assertIsInstance(result[2], ToolCallDelta)
        self.assertEqual(result[2].name, "read_file")
        self.assertIsInstance(result[3], MessageComplete)
        self.assertEqual(result[3].stop_reason, "end_turn")
        self.assertEqual(result[3].usage.input_tokens, 10)

    def test_stream_empty(self):
        provider = FakeProvider(events=[])
        result = list(provider.stream([]))
        self.assertEqual(result, [])

    def test_count_tokens_returns_expected_value(self):
        provider = FakeProvider(token_count=42)
        messages = [UserMessage(content=[TextBlock(text="test")])]
        self.assertEqual(provider.count_tokens(messages), 42)

    def test_count_tokens_zero(self):
        provider = FakeProvider(token_count=0)
        self.assertEqual(provider.count_tokens([]), 0)

    def test_stream_with_optional_params(self):
        events = [MessageComplete(stop_reason="max_tokens")]
        provider = FakeProvider(events=events)
        messages = [UserMessage(content=[TextBlock(text="hi")])]
        result = list(provider.stream(
            messages,
            tools=[{"name": "read", "description": "Read a file"}],
            model="claude-3",
            max_tokens=1024,
        ))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].stop_reason, "max_tokens")

    def test_count_tokens_with_optional_params(self):
        provider = FakeProvider(token_count=99)
        messages = [UserMessage(content=[TextBlock(text="hi")])]
        result = provider.count_tokens(
            messages,
            system_prompt="Be concise.",
            tools=[{"name": "search"}],
        )
        self.assertEqual(result, 99)


if __name__ == "__main__":
    unittest.main()
