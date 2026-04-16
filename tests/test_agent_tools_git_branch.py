# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tools.git_current_branch import GitCurrentBranchTool
from qgitc.agent.tools.git_branch import GitBranchTool
from qgitc.agent.tools.git_checkout import GitCheckoutTool
from qgitc.agent.tools.git_cherry_pick import GitCherryPickTool
from qgitc.agent.tools.git_commit import GitCommitTool
from qgitc.agent.tools.git_add import GitAddTool


def _make_context(working_directory="/tmp/repo"):
    return ToolContext(
        working_directory=working_directory,
        abort_requested=lambda: False,
    )


_PATCH_CURRENT_BRANCH = "qgitc.agent.tools.git_current_branch.run_git"
_PATCH_BRANCH = "qgitc.agent.tools.git_branch.run_git"
_PATCH_CHECKOUT = "qgitc.agent.tools.git_checkout.run_git"
_PATCH_CHERRY_PICK = "qgitc.agent.tools.git_cherry_pick.run_git"
_PATCH_COMMIT = "qgitc.agent.tools.git_commit.run_git"
_PATCH_ADD = "qgitc.agent.tools.git_add.run_git"


# ---- GitCurrentBranchTool ----


class TestGitCurrentBranchTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitCurrentBranchTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_current_branch")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["properties"], {})
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema_format(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        func = schema["function"]
        self.assertEqual(func["name"], "git_current_branch")
        self.assertEqual(func["description"], self.tool.description)
        self.assertEqual(func["parameters"], self.tool.input_schema())

    @patch(_PATCH_CURRENT_BRANCH, return_value=(True, "main"))
    def test_execute_returns_branch(self, mock_git):
        result = self.tool.execute({}, _make_context())
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "main")
        mock_git.assert_called_once_with(
            "/tmp/repo", ["rev-parse", "--abbrev-ref", "HEAD"]
        )

    @patch(_PATCH_CURRENT_BRANCH, return_value=(True, ""))
    def test_execute_empty_output_is_error(self, mock_git):
        result = self.tool.execute({}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("Failed to determine", result.content)

    @patch(_PATCH_CURRENT_BRANCH)
    def test_execute_detached_head(self, mock_git):
        mock_git.side_effect = [
            (True, "HEAD"),
            (True, "abc1234"),
        ]
        result = self.tool.execute({}, _make_context())
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "detached HEAD at abc1234")
        self.assertEqual(mock_git.call_count, 2)

    @patch(_PATCH_CURRENT_BRANCH)
    def test_execute_detached_head_no_sha(self, mock_git):
        mock_git.side_effect = [
            (True, "HEAD"),
            (False, ""),
        ]
        result = self.tool.execute({}, _make_context())
        self.assertFalse(result.is_error)
        self.assertEqual(result.content, "detached HEAD")

    @patch(_PATCH_CURRENT_BRANCH, return_value=(False, "fatal: not a git repository"))
    def test_execute_failure(self, mock_git):
        result = self.tool.execute({}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("not a git repository", result.content)


# ---- GitBranchTool ----


class TestGitBranchTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitBranchTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_branch")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("all", schema["properties"])
        self.assertEqual(schema["properties"]["all"]["type"], "boolean")
        self.assertFalse(schema["additionalProperties"])

    @patch(_PATCH_BRANCH, return_value=(True, "* main\n  develop"))
    def test_execute_default(self, mock_git):
        result = self.tool.execute({}, _make_context())
        self.assertFalse(result.is_error)
        self.assertIn("main", result.content)
        mock_git.assert_called_once_with("/tmp/repo", ["branch"])

    @patch(_PATCH_BRANCH, return_value=(True, "* main\n  remotes/origin/main"))
    def test_execute_all(self, mock_git):
        result = self.tool.execute({"all": True}, _make_context())
        self.assertFalse(result.is_error)
        mock_git.assert_called_once_with("/tmp/repo", ["branch", "-a"])

    @patch(_PATCH_BRANCH, return_value=(False, "fatal: error"))
    def test_execute_failure(self, mock_git):
        result = self.tool.execute({}, _make_context())
        self.assertTrue(result.is_error)


# ---- GitCheckoutTool ----


class TestGitCheckoutTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitCheckoutTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_checkout")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_not_read_only(self):
        self.assertFalse(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("branch", schema["properties"])
        self.assertIn("branch", schema["required"])
        self.assertFalse(schema["additionalProperties"])

    @patch(_PATCH_CHECKOUT, return_value=(True, "Switched to branch 'develop'"))
    def test_execute_success(self, mock_git):
        result = self.tool.execute({"branch": "develop"}, _make_context())
        self.assertFalse(result.is_error)
        self.assertIn("develop", result.content)
        mock_git.assert_called_once_with(
            "/tmp/repo", ["checkout", "develop"]
        )

    def test_execute_missing_branch(self):
        result = self.tool.execute({}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("branch", result.content)

    @patch(_PATCH_CHECKOUT, return_value=(False, "error: pathspec 'nope' did not match"))
    def test_execute_failure(self, mock_git):
        result = self.tool.execute({"branch": "nope"}, _make_context())
        self.assertTrue(result.is_error)


# ---- GitCherryPickTool ----


class TestGitCherryPickTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitCherryPickTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_cherry_pick")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_not_read_only(self):
        self.assertFalse(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("commits", schema["properties"])
        self.assertIn("commits", schema["required"])
        self.assertEqual(schema["properties"]["commits"]["type"], "array")
        self.assertEqual(
            schema["properties"]["commits"]["minItems"], 1
        )
        self.assertFalse(schema["additionalProperties"])

    @patch(_PATCH_CHERRY_PICK, return_value=(True, "[main abc1234] cherry-picked"))
    def test_execute_single(self, mock_git):
        result = self.tool.execute({"commits": ["abc1234"]}, _make_context())
        self.assertFalse(result.is_error)
        mock_git.assert_called_once_with(
            "/tmp/repo", ["cherry-pick", "abc1234"]
        )

    @patch(_PATCH_CHERRY_PICK, return_value=(True, ""))
    def test_execute_multiple(self, mock_git):
        result = self.tool.execute(
            {"commits": ["aaa", "bbb", "ccc"]}, _make_context()
        )
        self.assertFalse(result.is_error)
        mock_git.assert_called_once_with(
            "/tmp/repo", ["cherry-pick", "aaa", "bbb", "ccc"]
        )

    def test_execute_missing_commits(self):
        result = self.tool.execute({}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("commits", result.content)

    def test_execute_empty_commits(self):
        result = self.tool.execute({"commits": []}, _make_context())
        self.assertTrue(result.is_error)

    @patch(_PATCH_CHERRY_PICK, return_value=(False, "error: could not apply"))
    def test_execute_failure(self, mock_git):
        result = self.tool.execute({"commits": ["bad"]}, _make_context())
        self.assertTrue(result.is_error)


# ---- GitCommitTool ----


class TestGitCommitTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitCommitTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_commit")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_not_read_only(self):
        self.assertFalse(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("message", schema["properties"])
        self.assertIn("message", schema["required"])
        self.assertFalse(schema["additionalProperties"])

    @patch(_PATCH_COMMIT, return_value=(True, "[main abc1234] fix: stuff"))
    def test_execute_success(self, mock_git):
        result = self.tool.execute(
            {"message": "fix: stuff"}, _make_context()
        )
        self.assertFalse(result.is_error)
        mock_git.assert_called_once_with(
            "/tmp/repo", ["commit", "-m", "fix: stuff", "--no-edit"]
        )

    def test_execute_missing_message(self):
        result = self.tool.execute({}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("message", result.content)

    @patch(_PATCH_COMMIT, return_value=(False, "nothing to commit"))
    def test_execute_failure(self, mock_git):
        result = self.tool.execute(
            {"message": "empty"}, _make_context()
        )
        self.assertTrue(result.is_error)


# ---- GitAddTool ----


class TestGitAddTool(unittest.TestCase):
    def setUp(self):
        self.tool = GitAddTool()

    def test_name_and_description(self):
        self.assertEqual(self.tool.name, "git_add")
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_not_read_only(self):
        self.assertFalse(self.tool.is_read_only())

    def test_is_not_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("files", schema["properties"])
        self.assertIn("files", schema["required"])
        self.assertEqual(schema["properties"]["files"]["type"], "array")
        self.assertEqual(schema["properties"]["files"]["minItems"], 1)
        self.assertFalse(schema["additionalProperties"])

    @patch(_PATCH_ADD, return_value=(True, ""))
    def test_execute_single_file(self, mock_git):
        result = self.tool.execute(
            {"files": ["foo.py"]}, _make_context()
        )
        self.assertFalse(result.is_error)
        mock_git.assert_called_once_with(
            "/tmp/repo", ["add", "foo.py"]
        )

    @patch(_PATCH_ADD, return_value=(True, ""))
    def test_execute_multiple_files(self, mock_git):
        result = self.tool.execute(
            {"files": ["a.py", "b.py", "c.txt"]}, _make_context()
        )
        self.assertFalse(result.is_error)
        mock_git.assert_called_once_with(
            "/tmp/repo", ["add", "a.py", "b.py", "c.txt"]
        )

    def test_execute_missing_files(self):
        result = self.tool.execute({}, _make_context())
        self.assertTrue(result.is_error)
        self.assertIn("files", result.content)

    def test_execute_empty_files(self):
        result = self.tool.execute({"files": []}, _make_context())
        self.assertTrue(result.is_error)

    @patch(_PATCH_ADD, return_value=(False, "fatal: pathspec 'nope' did not match"))
    def test_execute_failure(self, mock_git):
        result = self.tool.execute(
            {"files": ["nope"]}, _make_context()
        )
        self.assertTrue(result.is_error)


# ---- run_git helper ----


class TestRunGitHelper(unittest.TestCase):
    @patch("qgitc.agent.tools._utils.runGit")
    def test_success(self, mock_run_git):
        mock_run_git.return_value = (True, "output\n", "")
        from qgitc.agent.tools.utils import run_git
        ok, out = run_git("/tmp/repo", ["status"])
        self.assertTrue(ok)
        self.assertEqual(out, "output")

    @patch("qgitc.agent.tools._utils.runGit")
    def test_failure_with_stderr(self, mock_run_git):
        mock_run_git.return_value = (False, "", "fatal: error\n")
        from qgitc.agent.tools.utils import run_git
        ok, out = run_git("/tmp/repo", ["bad"])
        self.assertFalse(ok)
        self.assertIn("fatal: error", out)

    @patch("qgitc.agent.tools._utils.runGit", side_effect=Exception("boom"))
    def test_exception(self, mock_run_git):
        from qgitc.agent.tools.utils import run_git
        with self.assertRaises(Exception):
            run_git("/tmp/repo", ["status"])


if __name__ == "__main__":
    unittest.main()
