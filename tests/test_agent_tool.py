# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.tool import Tool, ToolContext, ToolResult

from typing import Any, Dict


class EchoTool(Tool):
    name = "echo"
    description = "Echoes the input message back"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        message = input_data.get("message", "")
        return ToolResult(content=message)

    def input_schema(self) -> Dict[str, Any]:
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

    def is_read_only(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="read only result")

    def input_schema(self) -> Dict[str, Any]:
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

    def test_is_read_only_default(self):
        self.assertFalse(self.tool.is_read_only())

    def test_is_destructive_default(self):
        self.assertFalse(self.tool.is_destructive())

    def test_execute_returns_correct_result(self):
        result = self.tool.execute({"message": "hello"}, self.context)
        self.assertIsInstance(result, ToolResult)
        self.assertEqual(result.content, "hello")
        self.assertFalse(result.is_error)

    def test_execute_empty_message(self):
        result = self.tool.execute({}, self.context)
        self.assertEqual(result.content, "")
        self.assertFalse(result.is_error)

    def test_input_schema_valid(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("properties", schema)
        self.assertIn("message", schema["properties"])
        self.assertEqual(schema["properties"]["message"]["type"], "string")
        self.assertIn("required", schema)
        self.assertIn("message", schema["required"])

    def test_openai_schema_format(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertIn("function", schema)
        func = schema["function"]
        self.assertEqual(func["name"], "echo")
        self.assertEqual(func["description"], "Echoes the input message back")
        self.assertEqual(func["parameters"], self.tool.input_schema())


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
    def test_is_read_only_true(self):
        tool = ReadOnlyTool()
        self.assertTrue(tool.is_read_only())

    def test_is_destructive_default(self):
        tool = ReadOnlyTool()
        self.assertFalse(tool.is_destructive())

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
