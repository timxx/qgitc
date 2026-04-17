# -*- coding: utf-8 -*-

import unittest
from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tool_executor import _partition_tool_calls
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import ToolUseBlock


class ReadOnlyTool(Tool):
    name = "read_tool"
    description = "Read-only test tool"

    def is_read_only(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="ok")

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class WriteTool(Tool):
    name = "write_tool"
    description = "Write test tool"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="ok")

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class TestPartitionToolCalls(unittest.TestCase):

    def test_partitions_consecutive_read_only_groups(self):
        registry = ToolRegistry()
        registry.register(ReadOnlyTool())
        registry.register(WriteTool())

        blocks = [
            ToolUseBlock(id="1", name="read_tool", input={}),
            ToolUseBlock(id="2", name="read_tool", input={}),
            ToolUseBlock(id="3", name="write_tool", input={}),
            ToolUseBlock(id="4", name="read_tool", input={}),
        ]

        batches = _partition_tool_calls(blocks, registry)

        self.assertEqual(len(batches), 3)
        self.assertTrue(batches[0].is_parallel)
        self.assertEqual([block.id for block in batches[0].blocks], ["1", "2"])
        self.assertFalse(batches[1].is_parallel)
        self.assertEqual([block.id for block in batches[1].blocks], ["3"])
        self.assertTrue(batches[2].is_parallel)
        self.assertEqual([block.id for block in batches[2].blocks], ["4"])

    def test_does_not_merge_consecutive_non_parallel_blocks(self):
        registry = ToolRegistry()
        registry.register(WriteTool())

        blocks = [
            ToolUseBlock(id="1", name="write_tool", input={}),
            ToolUseBlock(id="2", name="write_tool", input={}),
        ]

        batches = _partition_tool_calls(blocks, registry)

        self.assertEqual(len(batches), 2)
        self.assertFalse(batches[0].is_parallel)
        self.assertEqual([block.id for block in batches[0].blocks], ["1"])
        self.assertFalse(batches[1].is_parallel)
        self.assertEqual([block.id for block in batches[1].blocks], ["2"])


if __name__ == "__main__":
    unittest.main()
