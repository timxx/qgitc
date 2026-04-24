# -*- coding: utf-8 -*-

import unittest
from typing import Iterator, List

from qgitc.agent.aimodel_adapter import AiModelBaseAdapter
from qgitc.agent.compaction import (
    CompactionResult,
    ConversationCompactor,
    _formatCompactSummary,
    _getCompactPrompt,
    microcompactMessages,
    roughEstimateTokens,
)
from qgitc.agent.provider import ContentDelta, MessageComplete, StreamEvent
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

# ── roughEstimateTokens ──────────────────────────────────────────────

class TestRoughEstimateTokens(unittest.TestCase):
    def test_empty_returns_zero(self):
        self.assertEqual(roughEstimateTokens([]), 0)

    def test_text_block(self):
        # 40 chars → ceil(40/4 * 4/3) = ceil(13.33) = 14 tokens
        msgs = [UserMessage(content=[TextBlock(text="a" * 40)])]
        result = roughEstimateTokens(msgs)
        self.assertEqual(result, 14)

    def test_tool_result_block(self):
        msgs = [UserMessage(content=[
            ToolResultBlock(tool_use_id="t1", content="x" * 120)
        ])]
        result = roughEstimateTokens(msgs)
        # 120/4 * 4/3 = 40
        self.assertEqual(result, 40)

    def test_thinking_block(self):
        msgs = [AssistantMessage(content=[
            ThinkingBlock(thinking="t" * 60)
        ])]
        result = roughEstimateTokens(msgs)
        # 60/4 * 4/3 = 20
        self.assertEqual(result, 20)

    def test_tool_use_block_counts_name_and_input(self):
        msgs = [AssistantMessage(content=[
            ToolUseBlock(id="x", name="read_file", input={"path": "/a"})
        ])]
        result = roughEstimateTokens(msgs)
        self.assertGreater(result, 0)

    def test_system_message_counts(self):
        msgs = [SystemMessage(content="s" * 40)]
        result = roughEstimateTokens(msgs)
        self.assertEqual(result, 14)

    def test_multiple_messages_sum(self):
        msgs = [
            UserMessage(content=[TextBlock(text="a" * 40)]),
            AssistantMessage(content=[TextBlock(text="b" * 40)]),
        ]
        single = roughEstimateTokens([UserMessage(content=[TextBlock(text="a" * 40)])])
        total = roughEstimateTokens(msgs)
        self.assertEqual(total, single * 2)


# ── _getCompactPrompt ────────────────────────────────────────────────

class TestGetCompactPrompt(unittest.TestCase):
    def test_contains_no_tools_preamble(self):
        prompt = _getCompactPrompt()
        self.assertIn("Do NOT call any tools", prompt)

    def test_contains_all_nine_sections(self):
        prompt = _getCompactPrompt()
        for section in [
            "Primary Request",
            "Key Technical Concepts",
            "Files and Code",
            "Errors and fixes",
            "Problem Solving",
            "user messages",
            "Pending Tasks",
            "Current Work",
            "Next Step",
        ]:
            self.assertIn(section, prompt,
                          msg="Section '{}' not found in prompt".format(section))

    def test_contains_analysis_instruction(self):
        prompt = _getCompactPrompt()
        self.assertIn("<analysis>", prompt)

    def test_contains_summary_instruction(self):
        prompt = _getCompactPrompt()
        self.assertIn("<summary>", prompt)

    def test_contains_no_tools_trailer(self):
        prompt = _getCompactPrompt()
        self.assertIn("REMINDER", prompt)
        self.assertIn("plain text", prompt)


# ── _formatCompactSummary ────────────────────────────────────────────

class TestFormatCompactSummary(unittest.TestCase):
    def test_passthrough_plain_text(self):
        text = "Just a plain summary."
        self.assertEqual(_formatCompactSummary(text), text)

    def test_strips_analysis_block(self):
        text = "<analysis>secret thoughts</analysis>\n<summary>real content</summary>"
        result = _formatCompactSummary(text)
        self.assertNotIn("<analysis>", result)
        self.assertNotIn("secret thoughts", result)

    def test_extracts_summary_block(self):
        text = "<analysis>thoughts</analysis>\n<summary>the answer</summary>"
        result = _formatCompactSummary(text)
        self.assertIn("the answer", result)
        self.assertNotIn("<summary>", result)

    def test_summary_prefixed_with_header(self):
        text = "<summary>the answer</summary>"
        result = _formatCompactSummary(text)
        self.assertTrue(result.startswith("Summary:"))

    def test_collapses_extra_blank_lines(self):
        text = "line1\n\n\n\nline2"
        result = _formatCompactSummary(text)
        self.assertNotIn("\n\n\n", result)

    def test_returns_trimmed(self):
        text = "  \n\n  content  \n\n  "
        result = _formatCompactSummary(text)
        self.assertEqual(result, result.strip())

    def test_summary_with_windows_path(self):
        text = r"<summary>Edited C:\Users\foo\bar.py</summary>"
        result = _formatCompactSummary(text)
        self.assertIn(r"C:\Users\foo\bar.py", result)
        self.assertTrue(result.startswith("Summary:"))

    def test_unclosed_summary_tag_is_cleaned(self):
        # If LLM is truncated, the closing tag may be absent
        text = "<summary>truncated content"
        result = _formatCompactSummary(text)
        self.assertNotIn("<summary>", result)


class FakeSummaryProvider(AiModelBaseAdapter):
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


# ── should_compact ───────────────────────────────────────────────────

class TestShouldCompact(unittest.TestCase):
    def test_returns_false_for_empty(self):
        provider = FakeSummaryProvider()
        compactor = ConversationCompactor(provider,
                                          context_window=100000,
                                          max_output_tokens=4096)
        self.assertFalse(compactor.shouldCompact([]))

    def test_returns_false_when_under_threshold(self):
        provider = FakeSummaryProvider()
        # effective = 100000 - min(4096, 20000) = 95904
        # threshold = 95904 - 13000 = 82904 tokens
        # "hello" = 5 chars -> ~2 tokens, well under
        compactor = ConversationCompactor(provider,
                                          context_window=100000,
                                          max_output_tokens=4096)
        msgs = [UserMessage(content=[TextBlock(text="hello")])]
        self.assertFalse(compactor.shouldCompact(msgs))

    def test_returns_true_when_over_threshold(self):
        provider = FakeSummaryProvider()
        # context=50000, max_out=4096
        # effective = 50000 - min(4096, 20000) = 45904
        # threshold = 45904 - 13000 = 32904 tokens
        # 100000 chars -> ceil(100000/4 * 4/3) = ceil(33333.33) = 33334 > 32904
        compactor = ConversationCompactor(provider,
                                          context_window=50000,
                                          max_output_tokens=4096)
        msgs = [UserMessage(content=[TextBlock(text="a" * 100000)])]
        self.assertTrue(compactor.shouldCompact(msgs))

    def test_max_output_tokens_capped_at_20000(self):
        provider = FakeSummaryProvider()
        # max_output_tokens=100000 -> capped to 20000
        # effective = 200000 - 20000 = 180000
        # threshold = 180000 - 13000 = 167000 tokens
        compactor = ConversationCompactor(provider,
                                          context_window=200000,
                                          max_output_tokens=100000)
        # 400000 chars -> ceil(400000/4 * 4/3) = ceil(133333.33) = 133334 tokens (under 167000)
        msgs = [UserMessage(content=[TextBlock(text="a" * 400000)])]
        self.assertFalse(compactor.shouldCompact(msgs))
        # 600000 chars -> ceil(600000/4 * 4/3) = ceil(200000.0) = 200000 tokens (over 167000)
        msgs2 = [UserMessage(content=[TextBlock(text="a" * 600000)])]
        self.assertTrue(compactor.shouldCompact(msgs2))


# ── compact ──────────────────────────────────────────────────────────

class ErrorOnNthCallProvider(AiModelBaseAdapter):
    """Provider that raises an error for the first N calls, then succeeds."""

    def __init__(self, fail_count, error_msg, success_text="Summary."):
        # type: (int, str, str) -> None
        self._fail_count = fail_count
        self._error_msg = error_msg
        self._success_text = success_text
        self._call_count = 0

    def stream(self, messages, tools=None, model=None, max_tokens=4096):
        self._call_count += 1
        if self._call_count <= self._fail_count:
            raise RuntimeError(self._error_msg)
        yield ContentDelta(text=self._success_text)
        yield MessageComplete(stop_reason="end_turn",
                              usage=Usage(input_tokens=10, output_tokens=5))


class TestCompact(unittest.TestCase):
    def _make_compactor(self, provider):
        return ConversationCompactor(provider,
                                     context_window=100000,
                                     max_output_tokens=4096)

    def test_raises_on_empty(self):
        compactor = self._make_compactor(FakeSummaryProvider())
        with self.assertRaises(ValueError):
            compactor.compact([])

    def test_returns_correct_types(self):
        compactor = self._make_compactor(FakeSummaryProvider("Summary text."))
        msgs = [
            UserMessage(content=[TextBlock(text="Please help me.")]),
            AssistantMessage(content=[TextBlock(text="Sure, how?")]),
        ]
        result = compactor.compact(msgs)
        self.assertIsInstance(result, CompactionResult)
        self.assertIsInstance(result.boundary, SystemMessage)
        self.assertIsInstance(result.summary, UserMessage)

    def test_boundary_has_compact_subtype(self):
        compactor = self._make_compactor(FakeSummaryProvider("Summary."))
        msgs = [UserMessage(content=[TextBlock(text="test")])]
        result = compactor.compact(msgs)
        self.assertEqual(result.boundary.subtype, "compact_boundary")

    def test_summary_starts_with_continuation_framing(self):
        compactor = self._make_compactor(FakeSummaryProvider("Key points here."))
        msgs = [UserMessage(content=[TextBlock(text="test")])]
        result = compactor.compact(msgs)
        text = result.summary.content[0].text
        self.assertTrue(
            text.startswith("This session is being continued"),
            msg="Expected continuation framing, got: {}".format(text[:80])
        )

    def test_summary_contains_provider_output(self):
        compactor = self._make_compactor(FakeSummaryProvider("The user asked X."))
        msgs = [UserMessage(content=[TextBlock(text="help")])]
        result = compactor.compact(msgs)
        text = result.summary.content[0].text
        self.assertIn("The user asked X.", text)

    def test_pre_greater_than_post_tokens(self):
        compactor = self._make_compactor(FakeSummaryProvider("Short."))
        msgs = [
            UserMessage(content=[TextBlock(text="a" * 1000)]),
            AssistantMessage(content=[TextBlock(text="b" * 1000)]),
        ]
        result = compactor.compact(msgs)
        self.assertGreater(result.pre_token_estimate, result.post_token_estimate)

    def test_non_ptl_error_raises_immediately(self):
        # Error message doesn't match PTL keywords -> should not retry
        provider = ErrorOnNthCallProvider(
            fail_count=1,
            error_msg="network connection timeout",
        )
        compactor = self._make_compactor(provider)
        msgs = [UserMessage(content=[TextBlock(text="test")])]
        with self.assertRaises(RuntimeError):
            compactor.compact(msgs)
        self.assertEqual(provider._call_count, 1)

    def test_empty_summary_raises(self):
        class EmptyProvider(AiModelBaseAdapter):
            def __init__(self):
                pass

            def stream(self, messages, tools=None, model=None, max_tokens=4096):
                yield MessageComplete(stop_reason="end_turn",
                                      usage=Usage(input_tokens=5, output_tokens=0))
        compactor = self._make_compactor(EmptyProvider())
        msgs = [UserMessage(content=[TextBlock(text="test")])]
        with self.assertRaises(RuntimeError):
            compactor.compact(msgs)


_CLEARED = "[Old tool result content cleared]"

# ── microcompactMessages ─────────────────────────────────────────────

class TestMicrocompactMessages(unittest.TestCase):
    def _make_history(self, old_result_content, recent_result_content="short"):
        """Build a minimal history with one old tool result and one recent.

        Structure:
          [0] UserMessage("hi")
          [1] AssistantMessage([ToolUseBlock(id="old1")])
          [2] UserMessage([ToolResultBlock(id="old1", content=old_result_content)])
          [3] AssistantMessage([ToolUseBlock(id="new1")])
          [4] UserMessage([ToolResultBlock(id="new1", content=recent_result_content)])
        """
        return [
            UserMessage(content=[TextBlock(text="hi")]),
            AssistantMessage(content=[
                ToolUseBlock(id="old1", name="read_file", input={})
            ]),
            UserMessage(content=[
                ToolResultBlock(tool_use_id="old1", content=old_result_content)
            ]),
            AssistantMessage(content=[
                ToolUseBlock(id="new1", name="read_file", input={})
            ]),
            UserMessage(content=[
                ToolResultBlock(tool_use_id="new1", content=recent_result_content)
            ]),
        ]

    def test_short_results_untouched(self):
        msgs = self._make_history("short content")
        result = microcompactMessages(msgs, thresholdChars=5000)
        old_result = result[2].content[0]
        self.assertEqual(old_result.content, "short content")

    def test_long_old_result_cleared(self):
        msgs = self._make_history("x" * 6000)
        result = microcompactMessages(msgs, thresholdChars=5000)
        old_result = result[2].content[0]
        self.assertEqual(old_result.content, _CLEARED)

    def test_recent_result_not_cleared(self):
        # Even if the recent result is long, it's protected
        msgs = self._make_history("x" * 6000, recent_result_content="y" * 6000)
        result = microcompactMessages(msgs, thresholdChars=5000)
        recent_result = result[4].content[0]
        self.assertEqual(recent_result.content, "y" * 6000)

    def test_exactly_at_threshold_untouched(self):
        msgs = self._make_history("x" * 5000)
        result = microcompactMessages(msgs, thresholdChars=5000)
        old_result = result[2].content[0]
        self.assertEqual(old_result.content, "x" * 5000)

    def test_one_over_threshold_cleared(self):
        msgs = self._make_history("x" * 5001)
        result = microcompactMessages(msgs, thresholdChars=5000)
        old_result = result[2].content[0]
        self.assertEqual(old_result.content, _CLEARED)

    def test_does_not_mutate_input(self):
        msgs = self._make_history("x" * 6000)
        original_content = msgs[2].content[0].content
        microcompactMessages(msgs, thresholdChars=5000)
        self.assertEqual(msgs[2].content[0].content, original_content)

    def test_empty_messages_returns_empty(self):
        result = microcompactMessages([], thresholdChars=5000)
        self.assertEqual(result, [])

    def test_no_assistant_messages_cutoff_at_zero(self):
        # With no AssistantMessages, cutoff_index = 0, all msgs are "protected"
        # (index >= 0 is everything), so nothing gets cleared
        msgs = [
            UserMessage(content=[
                ToolResultBlock(tool_use_id="t1", content="x" * 6000)
            ])
        ]
        result = microcompactMessages(msgs, thresholdChars=5000)
        # Nothing cleared because all messages are at index >= 0 (protected)
        self.assertEqual(result[0].content[0].content, "x" * 6000)

    def test_one_assistant_message_cutoff_at_its_index(self):
        # One AssistantMessage at index 1 → cutoff = 1
        # UserMessage at index 0 is old (< 1), UserMessage at index 2 is protected (>= 1)
        msgs = [
            UserMessage(content=[
                ToolResultBlock(tool_use_id="t0", content="x" * 6000)
            ]),
            AssistantMessage(content=[TextBlock(text="ok")]),
            UserMessage(content=[
                ToolResultBlock(tool_use_id="t2", content="y" * 6000)
            ]),
        ]
        result = microcompactMessages(msgs, thresholdChars=5000)
        self.assertEqual(result[0].content[0].content, _CLEARED)  # old
        self.assertEqual(result[2].content[0].content, "y" * 6000)  # protected

    def test_returns_same_object_when_no_changes(self):
        msgs = self._make_history("short content")  # under threshold
        result = microcompactMessages(msgs, thresholdChars=5000)
        self.assertIs(result, msgs)


if __name__ == "__main__":
    unittest.main()
