# -*- coding: utf-8 -*-

import os
import shutil
import unittest
from unittest.mock import patch

from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tools.git_status import GitStatusTool
from qgitc.gitutils import GitProcess


class TestGitStatusTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitStatusTool()
        if not GitProcess.GIT_BIN:
            GitProcess.GIT_BIN = shutil.which("git")

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
        self.assertIn("untracked", schema["properties"])
        self.assertEqual(schema["properties"]["untracked"]["type"], "boolean")
        self.assertTrue(schema["properties"]["untracked"]["default"])
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema_format(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertIn("function", schema)
        func = schema["function"]
        self.assertEqual(func["name"], "git_status")
        self.assertEqual(func["description"], self.tool.description)
        self.assertEqual(func["parameters"], self.tool.input_schema())

    @patch("qgitc.agent.tools.git_status.run_git")
    def test_execute_clean_with_branch(self, mock_run_git):
        mock_run_git.return_value = (True, "## main...origin/main")
        context = ToolContext(
            working_directory="/some/repo",
            abort_requested=lambda: False,
        )
        result = self.tool.execute({}, context)
        self.assertIsInstance(result, ToolResult)
        self.assertFalse(result.is_error)
        self.assertIn("working tree clean", result.content)
        self.assertIn("## main...origin/main", result.content)

    @patch("qgitc.agent.tools.git_status.run_git")
    def test_execute_clean_empty_output(self, mock_run_git):
        mock_run_git.return_value = (True, "")
        context = ToolContext(
            working_directory="/some/repo",
            abort_requested=lambda: False,
        )
        result = self.tool.execute({}, context)
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "working tree clean (no changes).")

    @patch("qgitc.agent.tools.git_status.run_git")
    def test_execute_with_changes(self, mock_run_git):
        mock_run_git.return_value = (True, "## main\n M file.txt")
        context = ToolContext(
            working_directory="/some/repo",
            abort_requested=lambda: False,
        )
        result = self.tool.execute({}, context)
        self.assertFalse(result.is_error)
        self.assertIn(" M file.txt", result.content)
        self.assertNotIn("working tree clean", result.content)

    @patch("qgitc.agent.tools.git_status.run_git")
    def test_execute_failure(self, mock_run_git):
        mock_run_git.return_value = (False, "fatal: not a git repository")
        context = ToolContext(
            working_directory="/nonexistent/path/xyz",
            abort_requested=lambda: False,
        )
        result = self.tool.execute({}, context)
        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.is_error)
        self.assertIn("not a git repository", result.content)

    @patch("qgitc.agent.tools.git_status.run_git")
    def test_execute_untracked_false(self, mock_run_git):
        mock_run_git.return_value = (True, "## main")
        context = ToolContext(
            working_directory="/some/repo",
            abort_requested=lambda: False,
        )
        self.tool.execute({"untracked": False}, context)
        args = mock_run_git.call_args[0][1]
        self.assertIn("--untracked-files=no", args)

    @patch("qgitc.agent.tools.git_status.run_git")
    def test_execute_untracked_default(self, mock_run_git):
        mock_run_git.return_value = (True, "## main")
        context = ToolContext(
            working_directory="/some/repo",
            abort_requested=lambda: False,
        )
        self.tool.execute({}, context)
        args = mock_run_git.call_args[0][1]
        self.assertNotIn("--untracked-files=no", args)

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
