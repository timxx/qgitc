# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tools.git_diff import GitDiffTool
from qgitc.agent.tools.git_diff_range import GitDiffRangeTool
from qgitc.agent.tools.git_diff_staged import GitDiffStagedTool
from qgitc.agent.tools.git_diff_unstaged import GitDiffUnstagedTool
from qgitc.agent.tools.git_log import GitLogTool


def _ctx(wd="/fake/repo"):
    return ToolContext(working_directory=wd, abort_requested=lambda: False)


# ---------------------------------------------------------------------------
# GitLogTool
# ---------------------------------------------------------------------------
class TestGitLogTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitLogTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "git_log")

    def test_description(self):
        self.assertIn("commit history", self.tool.description)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema_structure(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        props = schema["properties"]
        for key in ("nth", "maxCount", "since", "until", "rev", "path", "follow", "nameStatus"):
            self.assertIn(key, props)
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "git_log")

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_basic_log(self, mock_run):
        mock_run.return_value = (True, "abc1234 first\ndef5678 second")
        result = self.tool.execute({}, _ctx())
        self.assertFalse(result.is_error)
        self.assertIn("abc1234", result.content)
        args = mock_run.call_args[0][1]
        self.assertIn("log", args)
        self.assertIn("--oneline", args)
        self.assertIn("-n", args)
        idx = args.index("-n")
        self.assertEqual(args[idx + 1], "20")

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_max_count(self, mock_run):
        mock_run.return_value = (True, "abc1234 first")
        self.tool.execute({"maxCount": 5}, _ctx())
        args = mock_run.call_args[0][1]
        idx = args.index("-n")
        self.assertEqual(args[idx + 1], "5")

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_nth_commit_found(self, mock_run):
        mock_run.return_value = (True, "abc1234 the third commit")
        result = self.tool.execute({"nth": 3}, _ctx())
        self.assertFalse(result.is_error)
        self.assertIn("nth=3", result.content)
        self.assertIn("abc1234", result.content)
        args = mock_run.call_args[0][1]
        self.assertIn("--skip", args)
        self.assertEqual(args[args.index("--skip") + 1], "2")

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_nth_commit_not_found(self, mock_run):
        mock_run.return_value = (True, "")
        result = self.tool.execute({"nth": 999}, _ctx())
        self.assertTrue(result.is_error)
        self.assertIn("No commit found", result.content)

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_nth_with_path(self, mock_run):
        mock_run.return_value = (True, "abc1234 file change")
        result = self.tool.execute({"nth": 1, "path": "foo.py"}, _ctx())
        self.assertIn("filtered by path=foo.py", result.content)

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_since_until(self, mock_run):
        mock_run.return_value = (True, "abc1234 recent")
        self.tool.execute({"since": "2023-01-01", "until": "2023-06-01"}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertIn("--since", args)
        self.assertIn("2023-01-01", args)
        self.assertIn("--until", args)
        self.assertIn("2023-06-01", args)

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_name_status(self, mock_run):
        mock_run.return_value = (True, "abc1234 commit\nM file.py")
        self.tool.execute({"nameStatus": True}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertIn("--name-status", args)

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_rev(self, mock_run):
        mock_run.return_value = (True, "abc1234 commit")
        self.tool.execute({"rev": "main"}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertIn("main", args)

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_path_with_follow(self, mock_run):
        mock_run.return_value = (True, "abc1234 commit")
        self.tool.execute({"path": "src/main.py", "follow": True}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertIn("--follow", args)
        self.assertIn("--", args)
        self.assertIn("src/main.py", args)

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_path_without_follow(self, mock_run):
        mock_run.return_value = (True, "abc1234 commit")
        self.tool.execute({"path": "src/main.py", "follow": False}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertNotIn("--follow", args)
        self.assertIn("--", args)
        self.assertIn("src/main.py", args)

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_empty_output(self, mock_run):
        mock_run.return_value = (True, "")
        result = self.tool.execute({}, _ctx())
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "No commits found.")

    @patch("qgitc.agent.tools.git_log.run_git")
    def test_git_error(self, mock_run):
        mock_run.return_value = (False, "fatal: bad revision")
        result = self.tool.execute({"rev": "nonexistent"}, _ctx())
        self.assertTrue(result.is_error)
        self.assertIn("fatal", result.content)


# ---------------------------------------------------------------------------
# GitDiffTool
# ---------------------------------------------------------------------------
class TestGitDiffTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitDiffTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "git_diff")

    def test_description(self):
        self.assertIn("diff", self.tool.description)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema_requires_rev(self):
        schema = self.tool.input_schema()
        self.assertIn("rev", schema.get("required", []))
        self.assertIn("rev", schema["properties"])
        self.assertIn("files", schema["properties"])
        self.assertFalse(schema["additionalProperties"])

    @patch("qgitc.agent.tools.git_diff.run_git")
    def test_basic_diff(self, mock_run):
        mock_run.return_value = (True, "diff --git a/f b/f\n+line")
        result = self.tool.execute({"rev": "abc123"}, _ctx())
        self.assertFalse(result.is_error)
        self.assertIn("+line", result.content)
        args = mock_run.call_args[0][1]
        self.assertIn("diff-tree", args)
        self.assertIn("-r", args)
        self.assertIn("--root", args)
        self.assertIn("abc123", args)
        self.assertIn("-p", args)
        self.assertIn("--textconv", args)
        self.assertIn("-C", args)
        self.assertIn("--no-commit-id", args)
        self.assertIn("-U3", args)

    @patch("qgitc.agent.tools.git_diff.run_git")
    def test_diff_with_files(self, mock_run):
        mock_run.return_value = (True, "diff output")
        self.tool.execute({"rev": "abc123", "files": ["a.py", "b.py"]}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertIn("--", args)
        sep_idx = args.index("--")
        self.assertIn("a.py", args[sep_idx:])
        self.assertIn("b.py", args[sep_idx:])

    @patch("qgitc.agent.tools.git_diff.run_git")
    def test_no_differences(self, mock_run):
        mock_run.return_value = (True, "")
        result = self.tool.execute({"rev": "abc123"}, _ctx())
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "No differences found")

    @patch("qgitc.agent.tools.git_diff.run_git")
    def test_git_error(self, mock_run):
        mock_run.return_value = (False, "fatal: bad object")
        result = self.tool.execute({"rev": "bad"}, _ctx())
        self.assertTrue(result.is_error)


# ---------------------------------------------------------------------------
# GitDiffUnstagedTool
# ---------------------------------------------------------------------------
class TestGitDiffUnstagedTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitDiffUnstagedTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "git_diff_unstaged")

    def test_description(self):
        self.assertIn("not yet staged", self.tool.description)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertIn("nameOnly", schema["properties"])
        self.assertIn("files", schema["properties"])
        self.assertFalse(schema["additionalProperties"])

    @patch("qgitc.agent.tools.git_diff_unstaged.run_git")
    def test_full_diff(self, mock_run):
        mock_run.return_value = (True, "diff output")
        result = self.tool.execute({}, _ctx())
        self.assertFalse(result.is_error)
        args = mock_run.call_args[0][1]
        self.assertIn("diff-files", args)
        self.assertIn("-p", args)
        self.assertIn("--textconv", args)
        self.assertIn("--submodule", args)
        self.assertIn("-C", args)
        self.assertIn("-U3", args)

    @patch("qgitc.agent.tools.git_diff_unstaged.run_git")
    def test_name_only(self, mock_run):
        mock_run.return_value = (True, "file.py\nother.py")
        result = self.tool.execute({"nameOnly": True}, _ctx())
        self.assertFalse(result.is_error)
        args = mock_run.call_args[0][1]
        self.assertIn("diff", args)
        self.assertIn("--name-only", args)
        self.assertNotIn("diff-files", args)

    @patch("qgitc.agent.tools.git_diff_unstaged.run_git")
    def test_with_files(self, mock_run):
        mock_run.return_value = (True, "diff output")
        self.tool.execute({"files": ["a.py"]}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertIn("--", args)
        self.assertIn("a.py", args)

    @patch("qgitc.agent.tools.git_diff_unstaged.run_git")
    def test_no_changes(self, mock_run):
        mock_run.return_value = (True, "")
        result = self.tool.execute({}, _ctx())
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "No changed files found")

    @patch("qgitc.agent.tools.git_diff_unstaged.run_git")
    def test_git_error(self, mock_run):
        mock_run.return_value = (False, "error message")
        result = self.tool.execute({}, _ctx())
        self.assertTrue(result.is_error)


# ---------------------------------------------------------------------------
# GitDiffStagedTool
# ---------------------------------------------------------------------------
class TestGitDiffStagedTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitDiffStagedTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "git_diff_staged")

    def test_description(self):
        self.assertIn("staged", self.tool.description)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertIn("nameOnly", schema["properties"])
        self.assertIn("files", schema["properties"])
        self.assertFalse(schema["additionalProperties"])

    @patch("qgitc.agent.tools.git_diff_staged.run_git")
    def test_full_diff(self, mock_run):
        mock_run.return_value = (True, "diff output")
        result = self.tool.execute({}, _ctx())
        self.assertFalse(result.is_error)
        args = mock_run.call_args[0][1]
        self.assertIn("diff-index", args)
        self.assertIn("--cached", args)
        self.assertIn("HEAD", args)
        self.assertIn("-p", args)
        self.assertIn("--textconv", args)
        self.assertIn("--submodule", args)
        self.assertIn("-C", args)
        self.assertIn("-U3", args)

    @patch("qgitc.agent.tools.git_diff_staged.run_git")
    def test_name_only(self, mock_run):
        mock_run.return_value = (True, "file.py")
        result = self.tool.execute({"nameOnly": True}, _ctx())
        self.assertFalse(result.is_error)
        args = mock_run.call_args[0][1]
        self.assertIn("diff", args)
        self.assertIn("--name-only", args)
        self.assertIn("--cached", args)
        self.assertNotIn("diff-index", args)

    @patch("qgitc.agent.tools.git_diff_staged.run_git")
    def test_with_files(self, mock_run):
        mock_run.return_value = (True, "diff output")
        self.tool.execute({"files": ["x.py"]}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertIn("--", args)
        self.assertIn("x.py", args)

    @patch("qgitc.agent.tools.git_diff_staged.run_git")
    def test_no_changes(self, mock_run):
        mock_run.return_value = (True, "")
        result = self.tool.execute({}, _ctx())
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "No changed files found")

    @patch("qgitc.agent.tools.git_diff_staged.run_git")
    def test_git_error(self, mock_run):
        mock_run.return_value = (False, "error")
        result = self.tool.execute({}, _ctx())
        self.assertTrue(result.is_error)


# ---------------------------------------------------------------------------
# GitDiffRangeTool
# ---------------------------------------------------------------------------
class TestGitDiffRangeTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitDiffRangeTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "git_diff_range")

    def test_description(self):
        self.assertIn("range", self.tool.description)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema_requires_rev(self):
        schema = self.tool.input_schema()
        self.assertIn("rev", schema.get("required", []))
        props = schema["properties"]
        for key in ("rev", "files", "nameStatus", "contextLines", "findRenames"):
            self.assertIn(key, props)
        self.assertFalse(schema["additionalProperties"])

    @patch("qgitc.agent.tools.git_diff_range.run_git")
    def test_basic_range(self, mock_run):
        mock_run.return_value = (True, "diff output")
        result = self.tool.execute({"rev": "A..B"}, _ctx())
        self.assertFalse(result.is_error)
        args = mock_run.call_args[0][1]
        self.assertIn("diff", args)
        self.assertIn("-U3", args)
        self.assertIn("-M", args)
        self.assertIn("-C", args)
        self.assertIn("A..B", args)

    @patch("qgitc.agent.tools.git_diff_range.run_git")
    def test_name_status(self, mock_run):
        mock_run.return_value = (True, "R100\told.py\tnew.py")
        result = self.tool.execute({"rev": "A..B", "nameStatus": True}, _ctx())
        self.assertFalse(result.is_error)
        args = mock_run.call_args[0][1]
        self.assertIn("--name-status", args)
        self.assertNotIn("-U3", args)

    @patch("qgitc.agent.tools.git_diff_range.run_git")
    def test_custom_context_lines(self, mock_run):
        mock_run.return_value = (True, "diff output")
        self.tool.execute({"rev": "HEAD", "contextLines": 10}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertIn("-U10", args)

    @patch("qgitc.agent.tools.git_diff_range.run_git")
    def test_no_renames(self, mock_run):
        mock_run.return_value = (True, "diff output")
        self.tool.execute({"rev": "HEAD", "findRenames": False}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertNotIn("-M", args)
        self.assertNotIn("-C", args)

    @patch("qgitc.agent.tools.git_diff_range.run_git")
    def test_with_files(self, mock_run):
        mock_run.return_value = (True, "diff output")
        self.tool.execute({"rev": "HEAD", "files": ["a.py", "b.py"]}, _ctx())
        args = mock_run.call_args[0][1]
        self.assertIn("--", args)
        sep_idx = args.index("--")
        self.assertIn("a.py", args[sep_idx:])
        self.assertIn("b.py", args[sep_idx:])

    @patch("qgitc.agent.tools.git_diff_range.run_git")
    def test_no_differences(self, mock_run):
        mock_run.return_value = (True, "")
        result = self.tool.execute({"rev": "HEAD"}, _ctx())
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "No differences found")

    @patch("qgitc.agent.tools.git_diff_range.run_git")
    def test_git_error(self, mock_run):
        mock_run.return_value = (False, "fatal: bad revision")
        result = self.tool.execute({"rev": "bad"}, _ctx())
        self.assertTrue(result.is_error)


if __name__ == "__main__":
    unittest.main()
