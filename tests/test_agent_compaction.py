# -*- coding: utf-8 -*-

import unittest
from typing import Any, Dict, Iterator, List, Optional

from qgitc.agent.compaction import (
    CompactionResult,
    ConversationCompactor,
    _build_summarization_prompt,
    _message_text,
    estimate_tokens,
)
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    StreamEvent,
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


class FakeSummaryProvider(ModelProvider):
    """Provider that yields a fixed summary text as ContentDelta chunks."""

    def __init__(self, summary_text="This is the summary."):
        # type: (str) -> None
        self._summary_text = summary_text

    def stream(self, messages, tools=None,
               model=None, max_tokens=4096):
        # type: (...) -> Iterator[StreamEvent]
        yield ContentDelta(text=self._summary_text)
        yield MessageComplete(stop_reason="end_turn",
                              usage=Usage(input_tokens=10,
                                          output_tokens=5))

    def count_tokens(self, messages, system_prompt=None, tools=None):
        # type: (...) -> int
        return 0


# ── _message_text ────────────────────────────────────────────────────

class TestMessageText(unittest.TestCase):
    def test_text_block(self):
        msg = UserMessage(content=[TextBlock(text="hello world")])
        self.assertEqual(_message_text(msg), "hello world")

    def test_tool_use_block(self):
        msg = AssistantMessage(content=[
            ToolUseBlock(id="t1", name="read_file",
                         input={"path": "/tmp/x"}),
        ])
        result = _message_text(msg)
        self.assertIn("read_file", result)
        self.assertIn("/tmp/x", result)

    def test_tool_result_block(self):
        msg = UserMessage(content=[
            ToolResultBlock(tool_use_id="t1", content="file contents"),
        ])
        self.assertEqual(_message_text(msg), "file contents")

    def test_thinking_block(self):
        msg = AssistantMessage(content=[
            ThinkingBlock(thinking="Let me think..."),
        ])
        self.assertEqual(_message_text(msg), "Let me think...")

    def test_system_message(self):
        msg = SystemMessage(content="You are helpful.")
        self.assertEqual(_message_text(msg), "You are helpful.")

    def test_multiple_blocks(self):
        msg = UserMessage(content=[
            TextBlock(text="hello "),
            TextBlock(text="world"),
        ])
        self.assertEqual(_message_text(msg), "hello world")

    def test_empty_content(self):
        msg = UserMessage(content=[])
        self.assertEqual(_message_text(msg), "")


# ── estimate_tokens ─────────────────────────────────────────────────

class TestEstimateTokens(unittest.TestCase):
    def test_empty_list_returns_zero(self):
        self.assertEqual(estimate_tokens([]), 0)

    def test_single_message(self):
        # "abcdefgh" = 8 chars -> 8 // 4 = 2 tokens
        msg = UserMessage(content=[TextBlock(text="abcdefgh")])
        self.assertEqual(estimate_tokens([msg]), 2)

    def test_multiple_messages_sum_correctly(self):
        # "aaaa" = 4 chars, "bbbbbbbb" = 8 chars -> total 12 // 4 = 3
        msgs = [
            UserMessage(content=[TextBlock(text="aaaa")]),
            AssistantMessage(content=[TextBlock(text="bbbbbbbb")]),
        ]  # type: List[Message]
        self.assertEqual(estimate_tokens(msgs), 3)

    def test_integer_division(self):
        # "abc" = 3 chars -> 3 // 4 = 0
        msg = UserMessage(content=[TextBlock(text="abc")])
        self.assertEqual(estimate_tokens([msg]), 0)


# ── _build_summarization_prompt ──────────────────────────────────────

class TestBuildSummarizationPrompt(unittest.TestCase):
    def test_labels_messages_correctly(self):
        msgs = [
            UserMessage(content=[TextBlock(text="Hi")]),
            AssistantMessage(content=[TextBlock(text="Hello")]),
            SystemMessage(content="Be concise."),
        ]  # type: List[Message]
        prompt = _build_summarization_prompt(msgs)
        self.assertIn("User: Hi", prompt)
        self.assertIn("Assistant: Hello", prompt)
        self.assertIn("System: Be concise.", prompt)

    def test_contains_instruction_prefix(self):
        msgs = [UserMessage(content=[TextBlock(text="test")])]
        prompt = _build_summarization_prompt(msgs)
        self.assertIn("Summarize", prompt)


# ── should_compact ───────────────────────────────────────────────────

class TestShouldCompact(unittest.TestCase):
    def test_returns_false_for_empty(self):
        provider = FakeSummaryProvider()
        compactor = ConversationCompactor(provider,
                                          context_window=100000,
                                          max_output_tokens=4096)
        self.assertFalse(compactor.should_compact([]))

    def test_returns_false_when_under_threshold(self):
        provider = FakeSummaryProvider()
        # context=100000, max_out=4096, buffer=2000 -> threshold=93904
        # "hello" = 5 chars -> 1 token, well under threshold
        compactor = ConversationCompactor(provider,
                                          context_window=100000,
                                          max_output_tokens=4096)
        msgs = [UserMessage(content=[TextBlock(text="hello")])]
        self.assertFalse(compactor.should_compact(msgs))

    def test_returns_true_when_over_threshold(self):
        provider = FakeSummaryProvider()
        # context=100, max_out=50, buffer=2000 -> threshold = -1950
        # Any non-empty message should exceed that, but let's use a
        # more realistic example:
        # context=100, max_out=10, buffer=20 -> threshold=70 tokens
        # 300 chars -> 75 tokens > 70
        compactor = ConversationCompactor(provider,
                                          context_window=100,
                                          max_output_tokens=10)
        # override buffer for test clarity
        ConversationCompactor.BUFFER_TOKENS = 20
        try:
            msgs = [UserMessage(content=[TextBlock(text="a" * 300)])]
            self.assertTrue(compactor.should_compact(msgs))
        finally:
            ConversationCompactor.BUFFER_TOKENS = 2000


# ── compact ──────────────────────────────────────────────────────────

class TestCompact(unittest.TestCase):
    def test_raises_on_empty(self):
        provider = FakeSummaryProvider()
        compactor = ConversationCompactor(provider,
                                          context_window=100000,
                                          max_output_tokens=4096)
        with self.assertRaises(ValueError):
            compactor.compact([])

    def test_returns_correct_types(self):
        provider = FakeSummaryProvider(summary_text="Summarized convo.")
        compactor = ConversationCompactor(provider,
                                          context_window=100000,
                                          max_output_tokens=4096)
        msgs = [
            UserMessage(content=[TextBlock(text="Please help me.")]),
            AssistantMessage(content=[TextBlock(text="Sure, how?")]),
        ]  # type: List[Message]
        result = compactor.compact(msgs)

        self.assertIsInstance(result, CompactionResult)
        self.assertIsInstance(result.boundary, SystemMessage)
        self.assertIsInstance(result.summary, UserMessage)

    def test_boundary_has_compact_subtype(self):
        provider = FakeSummaryProvider(summary_text="Summary.")
        compactor = ConversationCompactor(provider,
                                          context_window=100000,
                                          max_output_tokens=4096)
        msgs = [UserMessage(content=[TextBlock(text="test")])]
        result = compactor.compact(msgs)
        self.assertEqual(result.boundary.subtype, "compact_boundary")

    def test_summary_starts_with_prefix(self):
        provider = FakeSummaryProvider(summary_text="Key points here.")
        compactor = ConversationCompactor(provider,
                                          context_window=100000,
                                          max_output_tokens=4096)
        msgs = [UserMessage(content=[TextBlock(text="test")])]
        result = compactor.compact(msgs)
        text = result.summary.content[0].text
        self.assertTrue(text.startswith("[Conversation summary]\n"))
        self.assertIn("Key points here.", text)

    def test_pre_greater_than_post_tokens(self):
        # Give it a large input so pre > post
        provider = FakeSummaryProvider(summary_text="Short.")
        compactor = ConversationCompactor(provider,
                                          context_window=100000,
                                          max_output_tokens=4096)
        msgs = [
            UserMessage(content=[TextBlock(text="a" * 1000)]),
            AssistantMessage(content=[TextBlock(text="b" * 1000)]),
        ]  # type: List[Message]
        result = compactor.compact(msgs)
        self.assertGreater(result.pre_token_estimate,
                           result.post_token_estimate)

    def test_summary_contains_provider_output(self):
        provider = FakeSummaryProvider(summary_text="The user asked X.")
        compactor = ConversationCompactor(provider,
                                          context_window=100000,
                                          max_output_tokens=4096)
        msgs = [UserMessage(content=[TextBlock(text="help")])]
        result = compactor.compact(msgs)
        text = result.summary.content[0].text
        self.assertIn("The user asked X.", text)


if __name__ == "__main__":
    unittest.main()
