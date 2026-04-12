# -*- coding: utf-8 -*-

import os
import unittest

from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tools.git_status import GitStatusTool


class TestGitStatusTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitStatusTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_status")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("properties", schema)
        self.assertEqual(schema["properties"], {})
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema_format(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertIn("function", schema)
        func = schema["function"]
        self.assertEqual(func["name"], "git_status")
        self.assertEqual(func["description"], self.tool.description)
        self.assertEqual(func["parameters"], self.tool.input_schema())

    def test_execute_in_git_repo(self):
        context = ToolContext(
            working_directory=os.getcwd(),
            abort_requested=lambda: False,
        )
        result = self.tool.execute({}, context)
        self.assertIsInstance(result, ToolResult)
        self.assertFalse(result.is_error)
        self.assertIsInstance(result.content, str)

    def test_execute_in_nonexistent_dir(self):
        context = ToolContext(
            working_directory="/nonexistent/path/xyz",
            abort_requested=lambda: False,
        )
        result = self.tool.execute({}, context)
        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.is_error)


if __name__ == "__main__":
    unittest.main()
