# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.message_convert import (
    history_dicts_to_messages,
    messages_to_history_dicts,
)
from qgitc.agent.types import (
    AssistantMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


class TestMessagesToHistoryDicts(unittest.TestCase):

    def test_user_text_message(self):
        msgs = [UserMessage(content=[TextBlock(text="Hello")])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(len(dicts), 1)
        self.assertEqual(dicts[0]["role"], "user")
        self.assertEqual(dicts[0]["content"], "Hello")
        self.assertIsNone(dicts[0].get("tool_calls"))

    def test_assistant_text_message(self):
        msgs = [AssistantMessage(content=[TextBlock(text="Hi there")])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(dicts[0]["role"], "assistant")
        self.assertEqual(dicts[0]["content"], "Hi there")

    def test_assistant_with_reasoning(self):
        msgs = [AssistantMessage(content=[
            ThinkingBlock(thinking="Let me think..."),
            TextBlock(text="Answer"),
        ])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(dicts[0]["content"], "Answer")
        self.assertEqual(dicts[0]["reasoning"], "Let me think...")

    def test_assistant_tool_call(self):
        msgs = [AssistantMessage(content=[
            TextBlock(text="I'll check"),
            ToolUseBlock(id="call_1", name="git_status", input={"untracked": True}),
        ])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(dicts[0]["content"], "I'll check")
        tc = dicts[0]["tool_calls"]
        self.assertIsInstance(tc, list)
        self.assertEqual(len(tc), 1)
        self.assertEqual(tc[0]["id"], "call_1")
        self.assertEqual(tc[0]["function"]["name"], "git_status")

    def test_tool_result_message(self):
        msgs = [UserMessage(content=[
            ToolResultBlock(tool_use_id="call_1", content="output", is_error=False),
        ])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(dicts[0]["role"], "tool")
        self.assertEqual(dicts[0]["content"], "output")
        self.assertEqual(dicts[0]["tool_calls"], {"tool_call_id": "call_1"})

    def test_system_message(self):
        msgs = [SystemMessage(subtype="system", content="You are helpful")]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(dicts[0]["role"], "system")
        self.assertEqual(dicts[0]["content"], "You are helpful")

    def test_multiple_tool_results_expand(self):
        msgs = [UserMessage(content=[
            ToolResultBlock(tool_use_id="c1", content="out1"),
            ToolResultBlock(tool_use_id="c2", content="out2"),
        ])]
        dicts = messages_to_history_dicts(msgs)
        self.assertEqual(len(dicts), 2)
        self.assertEqual(dicts[0]["role"], "tool")
        self.assertEqual(dicts[0]["tool_calls"], {"tool_call_id": "c1"})
        self.assertEqual(dicts[1]["tool_calls"], {"tool_call_id": "c2"})


class TestHistoryDictsToMessages(unittest.TestCase):

    def test_user_message(self):
        dicts = [{"role": "user", "content": "Hello"}]
        msgs = history_dicts_to_messages(dicts)
        self.assertEqual(len(msgs), 1)
        self.assertIsInstance(msgs[0], UserMessage)
        self.assertEqual(msgs[0].content[0].text, "Hello")

    def test_assistant_message(self):
        dicts = [{"role": "assistant", "content": "Hi there"}]
        msgs = history_dicts_to_messages(dicts)
        self.assertIsInstance(msgs[0], AssistantMessage)
        self.assertEqual(msgs[0].content[0].text, "Hi there")

    def test_assistant_with_reasoning(self):
        dicts = [{"role": "assistant", "content": "Answer", "reasoning": "Let me think..."}]
        msgs = history_dicts_to_messages(dicts)
        self.assertIsInstance(msgs[0], AssistantMessage)
        blocks = msgs[0].content
        thinking_blocks = [b for b in blocks if isinstance(b, ThinkingBlock)]
        text_blocks = [b for b in blocks if isinstance(b, TextBlock)]
        self.assertEqual(len(thinking_blocks), 1)
        self.assertEqual(thinking_blocks[0].thinking, "Let me think...")
        self.assertEqual(text_blocks[0].text, "Answer")

    def test_assistant_with_tool_calls(self):
        dicts = [{
            "role": "assistant",
            "content": "Checking",
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "git_status", "arguments": '{"untracked": true}'},
            }],
        }]
        msgs = history_dicts_to_messages(dicts)
        blocks = msgs[0].content
        text_blocks = [b for b in blocks if isinstance(b, TextBlock)]
        tool_blocks = [b for b in blocks if isinstance(b, ToolUseBlock)]
        self.assertEqual(text_blocks[0].text, "Checking")
        self.assertEqual(tool_blocks[0].id, "call_1")
        self.assertEqual(tool_blocks[0].name, "git_status")
        self.assertEqual(tool_blocks[0].input, {"untracked": True})

    def test_tool_result(self):
        dicts = [{
            "role": "tool",
            "content": "output text",
            "tool_calls": {"tool_call_id": "call_1"},
        }]
        msgs = history_dicts_to_messages(dicts)
        self.assertIsInstance(msgs[0], UserMessage)
        self.assertIsInstance(msgs[0].content[0], ToolResultBlock)
        self.assertEqual(msgs[0].content[0].tool_use_id, "call_1")
        self.assertEqual(msgs[0].content[0].content, "output text")

    def test_system_message(self):
        dicts = [{"role": "system", "content": "You are helpful"}]
        msgs = history_dicts_to_messages(dicts)
        self.assertIsInstance(msgs[0], SystemMessage)
        self.assertEqual(msgs[0].content, "You are helpful")

    def test_roundtrip(self):
        original = [
            UserMessage(content=[TextBlock(text="Hello")]),
            AssistantMessage(content=[
                ThinkingBlock(thinking="Hmm"),
                TextBlock(text="Answer"),
                ToolUseBlock(id="c1", name="git_status", input={}),
            ]),
            UserMessage(content=[
                ToolResultBlock(tool_use_id="c1", content="clean"),
            ]),
            AssistantMessage(content=[TextBlock(text="All good")]),
        ]
        dicts = messages_to_history_dicts(original)
        restored = history_dicts_to_messages(dicts)
        dicts2 = messages_to_history_dicts(restored)
        self.assertEqual(dicts, dicts2)


if __name__ == "__main__":
    unittest.main()
