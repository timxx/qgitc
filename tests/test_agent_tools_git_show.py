# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tools.git_show import GitShowTool
from qgitc.agent.tools.git_show_file import GitShowFileTool
from qgitc.agent.tools.git_show_index_file import GitShowIndexFileTool
from qgitc.agent.tools.git_blame import GitBlameTool


def _make_context(working_directory="/fake/repo"):
    return ToolContext(
        working_directory=working_directory,
        abort_requested=lambda: False,
    )


# ---------------------------------------------------------------------------
# GitShowTool
# ---------------------------------------------------------------------------

class TestGitShowTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitShowTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_show")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("rev", schema["properties"])
        self.assertIn("rev", schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "git_show")

    def test_missing_rev(self):
        result = self.tool.execute({}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("rev", result.content)

    @patch("qgitc.agent.tools.git_show.run_git")
    def test_success(self, mock_run_git):
        mock_run_git.return_value = (True, "commit abc123\nAuthor: Test\n\nSome message")
        result = self.tool.execute({"rev": "abc123"}, _make_context())
        self.assertFalse(result.is_error)
        self.assertIn("abc123", result.content)
        mock_run_git.assert_called_once_with("/fake/repo", ["show", "abc123"])

    @patch("qgitc.agent.tools.git_show.run_git")
    def test_failure(self, mock_run_git):
        mock_run_git.return_value = (False, "fatal: bad object abc")
        result = self.tool.execute({"rev": "abc"}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("fatal", result.content)


# ---------------------------------------------------------------------------
# GitShowFileTool
# ---------------------------------------------------------------------------

class TestGitShowFileTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitShowFileTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_show_file")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("rev", schema["required"])
        self.assertIn("path", schema["required"])
        self.assertIn("startLine", schema["properties"])
        self.assertIn("endLine", schema["properties"])
        self.assertFalse(schema["additionalProperties"])

    def test_missing_rev(self):
        result = self.tool.execute({"path": "foo.py"}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("rev", result.content)

    def test_missing_path(self):
        result = self.tool.execute({"rev": "HEAD"}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("path", result.content)

    @patch("qgitc.agent.tools.git_show_file.run_git")
    def test_success_full_file(self, mock_run_git):
        mock_run_git.return_value = (True, "line1\nline2\nline3\nline4")
        result = self.tool.execute(
            {"rev": "HEAD", "path": "foo.py"}, _make_context()
        )
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "line1\nline2\nline3\nline4")
        mock_run_git.assert_called_once_with(
            "/fake/repo", ["show", "HEAD:foo.py"]
        )

    @patch("qgitc.agent.tools.git_show_file.run_git")
    def test_success_with_line_range(self, mock_run_git):
        mock_run_git.return_value = (True, "line1\nline2\nline3\nline4")
        result = self.tool.execute(
            {"rev": "HEAD", "path": "foo.py", "startLine": 2, "endLine": 3},
            _make_context(),
        )
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "line2\nline3")

    @patch("qgitc.agent.tools.git_show_file.run_git")
    def test_success_with_start_line_only(self, mock_run_git):
        mock_run_git.return_value = (True, "line1\nline2\nline3\nline4")
        result = self.tool.execute(
            {"rev": "HEAD", "path": "foo.py", "startLine": 3},
            _make_context(),
        )
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "line3\nline4")

    @patch("qgitc.agent.tools.git_show_file.run_git")
    def test_success_with_end_line_only(self, mock_run_git):
        mock_run_git.return_value = (True, "line1\nline2\nline3\nline4")
        result = self.tool.execute(
            {"rev": "HEAD", "path": "foo.py", "endLine": 2},
            _make_context(),
        )
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "line1\nline2")

    @patch("qgitc.agent.tools.git_show_file.run_git")
    def test_failure(self, mock_run_git):
        mock_run_git.return_value = (False, "fatal: path 'missing' does not exist")
        result = self.tool.execute(
            {"rev": "HEAD", "path": "missing"}, _make_context()
        )
        self.assertTrue(result.is_error)


# ---------------------------------------------------------------------------
# GitShowIndexFileTool
# ---------------------------------------------------------------------------

class TestGitShowIndexFileTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitShowIndexFileTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_show_index_file")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("path", schema["required"])
        self.assertNotIn("rev", schema.get("required", []))
        self.assertIn("startLine", schema["properties"])
        self.assertIn("endLine", schema["properties"])
        self.assertFalse(schema["additionalProperties"])

    def test_missing_path(self):
        result = self.tool.execute({}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("path", result.content)

    @patch("qgitc.agent.tools.git_show_index_file.run_git")
    def test_success_full_file(self, mock_run_git):
        mock_run_git.return_value = (True, "idx1\nidx2\nidx3")
        result = self.tool.execute({"path": "bar.py"}, _make_context())
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "idx1\nidx2\nidx3")
        mock_run_git.assert_called_once_with(
            "/fake/repo", ["show", ":bar.py"]
        )

    @patch("qgitc.agent.tools.git_show_index_file.run_git")
    def test_success_with_line_range(self, mock_run_git):
        mock_run_git.return_value = (True, "idx1\nidx2\nidx3\nidx4")
        result = self.tool.execute(
            {"path": "bar.py", "startLine": 2, "endLine": 3},
            _make_context(),
        )
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "idx2\nidx3")

    @patch("qgitc.agent.tools.git_show_index_file.run_git")
    def test_failure(self, mock_run_git):
        mock_run_git.return_value = (False, "fatal: path 'x' does not exist in the index")
        result = self.tool.execute({"path": "x"}, _make_context())
        self.assertTrue(result.is_error)


# ---------------------------------------------------------------------------
# GitBlameTool
# ---------------------------------------------------------------------------

class TestGitBlameTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitBlameTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_blame")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("path", schema["required"])
        self.assertIn("rev", schema["properties"])
        self.assertIn("startLine", schema["properties"])
        self.assertIn("endLine", schema["properties"])
        self.assertIn("ignoreWhitespace", schema["properties"])
        self.assertEqual(
            schema["properties"]["ignoreWhitespace"]["default"], True
        )
        self.assertFalse(schema["additionalProperties"])

    def test_missing_path(self):
        result = self.tool.execute({}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("path", result.content)

    @patch("qgitc.agent.tools.git_blame.run_git")
    def test_basic_blame(self, mock_run_git):
        mock_run_git.return_value = (True, "abc123 (Author 2024-01-01 1) line1")
        result = self.tool.execute({"path": "foo.py"}, _make_context())
        self.assertFalse(result.is_error)
        self.assertIn("abc123", result.content)
        mock_run_git.assert_called_once_with(
            "/fake/repo", ["blame", "-w", "--", "foo.py"]
        )

    @patch("qgitc.agent.tools.git_blame.run_git")
    def test_blame_without_whitespace_ignore(self, mock_run_git):
        mock_run_git.return_value = (True, "abc123 (Author 2024-01-01 1) line1")
        result = self.tool.execute(
            {"path": "foo.py", "ignoreWhitespace": False}, _make_context()
        )
        self.assertFalse(result.is_error)
        mock_run_git.assert_called_once_with(
            "/fake/repo", ["blame", "--", "foo.py"]
        )

    @patch("qgitc.agent.tools.git_blame.run_git")
    def test_blame_with_rev(self, mock_run_git):
        mock_run_git.return_value = (True, "abc123 (Author 2024-01-01 1) line1")
        result = self.tool.execute(
            {"path": "foo.py", "rev": "HEAD~3"}, _make_context()
        )
        self.assertFalse(result.is_error)
        mock_run_git.assert_called_once_with(
            "/fake/repo", ["blame", "-w", "HEAD~3", "--", "foo.py"]
        )

    @patch("qgitc.agent.tools.git_blame.run_git")
    def test_blame_with_start_and_end_line(self, mock_run_git):
        mock_run_git.return_value = (True, "abc123 (Author 2024-01-01 5) line5")
        result = self.tool.execute(
            {"path": "foo.py", "startLine": 5, "endLine": 10},
            _make_context(),
        )
        self.assertFalse(result.is_error)
        mock_run_git.assert_called_once_with(
            "/fake/repo", ["blame", "-w", "-L", "5,10", "--", "foo.py"]
        )

    @patch("qgitc.agent.tools.git_blame.run_git")
    def test_blame_with_start_line_only(self, mock_run_git):
        mock_run_git.return_value = (True, "abc123 (Author 2024-01-01 5) line5")
        result = self.tool.execute(
            {"path": "foo.py", "startLine": 5}, _make_context()
        )
        self.assertFalse(result.is_error)
        mock_run_git.assert_called_once_with(
            "/fake/repo", ["blame", "-w", "-L", "5,", "--", "foo.py"]
        )

    @patch("qgitc.agent.tools.git_blame.run_git")
    def test_blame_with_end_line_only(self, mock_run_git):
        mock_run_git.return_value = (True, "abc123 (Author 2024-01-01 1) line1")
        result = self.tool.execute(
            {"path": "foo.py", "endLine": 3}, _make_context()
        )
        self.assertFalse(result.is_error)
        mock_run_git.assert_called_once_with(
            "/fake/repo", ["blame", "-w", "-L", "1,3", "--", "foo.py"]
        )

    @patch("qgitc.agent.tools.git_blame.run_git")
    def test_blame_empty_output(self, mock_run_git):
        mock_run_git.return_value = (True, "")
        result = self.tool.execute({"path": "empty.py"}, _make_context())
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "No blame output")

    @patch("qgitc.agent.tools.git_blame.run_git")
    def test_blame_failure(self, mock_run_git):
        mock_run_git.return_value = (False, "fatal: no such path 'x' in HEAD")
        result = self.tool.execute({"path": "x"}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("fatal", result.content)

    @patch("qgitc.agent.tools.git_blame.run_git")
    def test_blame_with_rev_and_line_range(self, mock_run_git):
        mock_run_git.return_value = (True, "abc (A 2024-01-01 2) l2")
        result = self.tool.execute(
            {"path": "foo.py", "rev": "abc123", "startLine": 2, "endLine": 5},
            _make_context(),
        )
        self.assertFalse(result.is_error)
        mock_run_git.assert_called_once_with(
            "/fake/repo",
            ["blame", "-w", "-L", "2,5", "abc123", "--", "foo.py"],
        )


if __name__ == "__main__":
    unittest.main()
