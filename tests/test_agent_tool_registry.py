# -*- coding: utf-8 -*-

import unittest

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tool_registry import ToolRegistry


class StubToolA(Tool):
    name = "tool_a"
    description = "Stub tool A"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="a")

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
            },
            "required": ["value"],
        }


class StubToolB(Tool):
    name = "tool_b"
    description = "Stub tool B"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="b")

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }


class TestToolRegistryEmpty(unittest.TestCase):

    def test_empty_list_tools(self):
        registry = ToolRegistry()
        self.assertEqual(registry.list_tools(), [])

    def test_empty_get_tool_schemas(self):
        registry = ToolRegistry()
        self.assertEqual(registry.get_tool_schemas(), [])


class TestToolRegistryRegisterAndGet(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()
        self.tool_a = StubToolA()
        self.tool_b = StubToolB()

    def test_register_and_get(self):
        self.registry.register(self.tool_a)
        result = self.registry.get("tool_a")
        self.assertIs(result, self.tool_a)

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.registry.get("nonexistent"))

    def test_list_tools_returns_all(self):
        self.registry.register(self.tool_a)
        self.registry.register(self.tool_b)
        tools = self.registry.list_tools()
        self.assertEqual(len(tools), 2)
        self.assertIn(self.tool_a, tools)
        self.assertIn(self.tool_b, tools)

    def test_unregister_removes_tool(self):
        self.registry.register(self.tool_a)
        self.registry.unregister("tool_a")
        self.assertIsNone(self.registry.get("tool_a"))
        self.assertEqual(self.registry.list_tools(), [])

    def test_unregister_missing_is_noop(self):
        self.registry.unregister("nonexistent")

    def test_register_overwrites_existing(self):
        self.registry.register(self.tool_a)
        replacement = StubToolA()
        self.registry.register(replacement)
        result = self.registry.get("tool_a")
        self.assertIs(result, replacement)
        self.assertIsNot(result, self.tool_a)
        self.assertEqual(len(self.registry.list_tools()), 1)

    def test_get_tool_schemas(self):
        self.registry.register(self.tool_a)
        self.registry.register(self.tool_b)
        schemas = self.registry.get_tool_schemas()
        self.assertEqual(len(schemas), 2)
        names = {s["function"]["name"] for s in schemas}
        self.assertEqual(names, {"tool_a", "tool_b"})
        for schema in schemas:
            self.assertEqual(schema["type"], "function")
            self.assertIn("function", schema)
            func = schema["function"]
            self.assertIn("name", func)
            self.assertIn("description", func)
            self.assertIn("parameters", func)


if __name__ == "__main__":
    unittest.main()
