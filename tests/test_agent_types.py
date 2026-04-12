# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.types import (
    AssistantMessage,
    ContentBlock,
    Message,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    UserMessage,
)


class TestTextBlock(unittest.TestCase):
    def test_creation_and_field_access(self):
        block = TextBlock(text="hello")
        self.assertEqual(block.text, "hello")

    def test_default(self):
        block = TextBlock()
        self.assertEqual(block.text, "")


class TestToolUseBlock(unittest.TestCase):
    def test_creation_and_field_access(self):
        block = ToolUseBlock(id="t1", name="read", input={"path": "/tmp"})
        self.assertEqual(block.id, "t1")
        self.assertEqual(block.name, "read")
        self.assertEqual(block.input, {"path": "/tmp"})

    def test_defaults(self):
        block = ToolUseBlock()
        self.assertEqual(block.id, "")
        self.assertEqual(block.name, "")
        self.assertEqual(block.input, {})


class TestToolResultBlock(unittest.TestCase):
    def test_creation_and_field_access(self):
        block = ToolResultBlock(tool_use_id="t1", content="ok", is_error=False)
        self.assertEqual(block.tool_use_id, "t1")
        self.assertEqual(block.content, "ok")
        self.assertFalse(block.is_error)

    def test_is_error_default(self):
        block = ToolResultBlock(tool_use_id="t1", content="ok")
        self.assertFalse(block.is_error)

    def test_is_error_true(self):
        block = ToolResultBlock(tool_use_id="t1", content="fail", is_error=True)
        self.assertTrue(block.is_error)


class TestThinkingBlock(unittest.TestCase):
    def test_creation_and_field_access(self):
        block = ThinkingBlock(thinking="let me think")
        self.assertEqual(block.thinking, "let me think")

    def test_default(self):
        block = ThinkingBlock()
        self.assertEqual(block.thinking, "")


class TestUsage(unittest.TestCase):
    def test_defaults(self):
        usage = Usage()
        self.assertEqual(usage.input_tokens, 0)
        self.assertEqual(usage.output_tokens, 0)
        self.assertEqual(usage.cache_creation_input_tokens, 0)
        self.assertEqual(usage.cache_read_input_tokens, 0)

    def test_custom_values(self):
        usage = Usage(
            input_tokens=100,
            output_tokens=200,
            cache_creation_input_tokens=50,
            cache_read_input_tokens=25,
        )
        self.assertEqual(usage.input_tokens, 100)
        self.assertEqual(usage.output_tokens, 200)
        self.assertEqual(usage.cache_creation_input_tokens, 50)
        self.assertEqual(usage.cache_read_input_tokens, 25)


class TestContentBlockUnion(unittest.TestCase):
    def test_text_block_isinstance(self):
        block = TextBlock(text="hi")
        # ContentBlock is a Union type alias; check against concrete types
        self.assertIsInstance(block, (TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock))

    def test_tool_use_block_isinstance(self):
        block = ToolUseBlock(id="t1", name="read", input={})
        self.assertIsInstance(block, (TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock))

    def test_tool_result_block_isinstance(self):
        block = ToolResultBlock(tool_use_id="t1", content="ok")
        self.assertIsInstance(block, (TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock))

    def test_thinking_block_isinstance(self):
        block = ThinkingBlock(thinking="hmm")
        self.assertIsInstance(block, (TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock))


class TestUserMessage(unittest.TestCase):
    def test_auto_uuid_and_timestamp(self):
        msg = UserMessage(content=[TextBlock(text="hi")])
        self.assertTrue(len(msg.uuid) > 0)
        self.assertTrue(len(msg.timestamp) > 0)

    def test_unique_uuids(self):
        msg1 = UserMessage()
        msg2 = UserMessage()
        self.assertNotEqual(msg1.uuid, msg2.uuid)

    def test_content_access(self):
        blocks = [TextBlock(text="a"), TextBlock(text="b")]
        msg = UserMessage(content=blocks)
        self.assertEqual(len(msg.content), 2)
        self.assertEqual(msg.content[0].text, "a")

    def test_with_tool_result_content(self):
        result = ToolResultBlock(tool_use_id="t1", content="output", is_error=False)
        msg = UserMessage(content=[result])
        self.assertEqual(len(msg.content), 1)
        self.assertIsInstance(msg.content[0], ToolResultBlock)
        self.assertEqual(msg.content[0].tool_use_id, "t1")
        self.assertEqual(msg.content[0].content, "output")


class TestAssistantMessage(unittest.TestCase):
    def test_auto_uuid_and_timestamp(self):
        msg = AssistantMessage(content=[TextBlock(text="reply")])
        self.assertTrue(len(msg.uuid) > 0)
        self.assertTrue(len(msg.timestamp) > 0)

    def test_optional_defaults(self):
        msg = AssistantMessage()
        self.assertIsNone(msg.model)
        self.assertIsNone(msg.stop_reason)
        self.assertIsNone(msg.usage)

    def test_with_usage(self):
        usage = Usage(input_tokens=10, output_tokens=20)
        msg = AssistantMessage(
            content=[TextBlock(text="done")],
            model="claude-3",
            stop_reason="end_turn",
            usage=usage,
        )
        self.assertEqual(msg.model, "claude-3")
        self.assertEqual(msg.stop_reason, "end_turn")
        self.assertEqual(msg.usage.input_tokens, 10)
        self.assertEqual(msg.usage.output_tokens, 20)


class TestSystemMessage(unittest.TestCase):
    def test_auto_uuid_and_timestamp(self):
        msg = SystemMessage(subtype="init", content="starting")
        self.assertTrue(len(msg.uuid) > 0)
        self.assertTrue(len(msg.timestamp) > 0)

    def test_compact_metadata_default(self):
        msg = SystemMessage(subtype="init", content="starting")
        self.assertIsNone(msg.compact_metadata)

    def test_with_compact_metadata(self):
        meta = {"key": "value"}
        msg = SystemMessage(subtype="compact", content="data", compact_metadata=meta)
        self.assertEqual(msg.compact_metadata, {"key": "value"})


class TestMessageUnion(unittest.TestCase):
    def test_user_message_isinstance(self):
        msg = UserMessage()
        self.assertIsInstance(msg, (UserMessage, AssistantMessage, SystemMessage))

    def test_assistant_message_isinstance(self):
        msg = AssistantMessage()
        self.assertIsInstance(msg, (UserMessage, AssistantMessage, SystemMessage))

    def test_system_message_isinstance(self):
        msg = SystemMessage(subtype="init", content="hi")
        self.assertIsInstance(msg, (UserMessage, AssistantMessage, SystemMessage))


if __name__ == "__main__":
    unittest.main()
