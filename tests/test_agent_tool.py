# -*- coding: utf-8 -*-

import unittest
from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult


class EchoTool(Tool):
    name = "echo"
    description = "Echoes the input message back"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        message = input_data.get("message", "")
        return ToolResult(content=message)

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The message to echo",
                },
            },
            "required": ["message"],
        }


class ReadOnlyTool(Tool):
    name = "read_only"
    description = "A read-only tool"

    def isReadOnly(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="read only result")

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }


class TestToolAbstract(unittest.TestCase):
    def test_cannot_instantiate_abstract_tool(self):
        with self.assertRaises(TypeError):
            Tool()


class TestEchoTool(unittest.TestCase):
    def setUp(self):
        self.tool = EchoTool()
        self.context = ToolContext(
            working_directory="/tmp",
            abort_requested=lambda: False,
        )

    def test_name(self):
        self.assertEqual(self.tool.name, "echo")

    def test_description(self):
        self.assertEqual(self.tool.description, "Echoes the input message back")

    def test_isReadOnly_default(self):
        self.assertFalse(self.tool.isReadOnly())

    def test_isDestructive_default(self):
        self.assertFalse(self.tool.isDestructive())

    def test_execute_returns_correct_result(self):
        result = self.tool.execute({"message": "hello"}, self.context)
        self.assertIsInstance(result, ToolResult)
        self.assertEqual(result.content, "hello")
        self.assertFalse(result.is_error)

    def test_execute_empty_message(self):
        result = self.tool.execute({}, self.context)
        self.assertEqual(result.content, "")
        self.assertFalse(result.is_error)

    def test_inputSchema_valid(self):
        schema = self.tool.inputSchema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("properties", schema)
        self.assertIn("message", schema["properties"])
        self.assertEqual(schema["properties"]["message"]["type"], "string")
        self.assertIn("required", schema)
        self.assertIn("message", schema["required"])

    def test_openaiSchema_format(self):
        schema = self.tool.openaiSchema()
        self.assertEqual(schema["type"], "function")
        self.assertIn("function", schema)
        func = schema["function"]
        self.assertEqual(func["name"], "echo")
        self.assertEqual(func["description"], "Echoes the input message back")
        self.assertEqual(func["parameters"], self.tool.inputSchema())


class TestToolResult(unittest.TestCase):
    def test_default_is_error_false(self):
        result = ToolResult(content="ok")
        self.assertEqual(result.content, "ok")
        self.assertFalse(result.is_error)

    def test_explicit_is_error_true(self):
        result = ToolResult(content="fail", is_error=True)
        self.assertEqual(result.content, "fail")
        self.assertTrue(result.is_error)


class TestToolContext(unittest.TestCase):
    def test_fields_accessible(self):
        ctx = ToolContext(
            working_directory="/home/user",
            abort_requested=lambda: False,
        )
        self.assertEqual(ctx.working_directory, "/home/user")
        self.assertFalse(ctx.abort_requested())

    def test_extra_default_empty_dict(self):
        ctx = ToolContext(
            working_directory="/tmp",
            abort_requested=lambda: False,
        )
        self.assertEqual(ctx.extra, {})

    def test_abort_requested_callable(self):
        aborted = False

        def check_abort():
            return aborted

        ctx = ToolContext(
            working_directory="/tmp",
            abort_requested=check_abort,
        )
        self.assertFalse(ctx.abort_requested())

        aborted = True
        self.assertTrue(ctx.abort_requested())


class TestReadOnlyTool(unittest.TestCase):
    def test_isReadOnly_true(self):
        tool = ReadOnlyTool()
        self.assertTrue(tool.isReadOnly())

    def test_isDestructive_default(self):
        tool = ReadOnlyTool()
        self.assertFalse(tool.isDestructive())

    def test_execute(self):
        tool = ReadOnlyTool()
        ctx = ToolContext(
            working_directory="/tmp",
            abort_requested=lambda: False,
        )
        result = tool.execute({}, ctx)
        self.assertEqual(result.content, "read only result")
        self.assertFalse(result.is_error)


if __name__ == "__main__":
    unittest.main()
