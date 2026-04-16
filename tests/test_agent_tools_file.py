# -*- coding: utf-8 -*-

import os
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from qgitc.agent.tool import ToolContext
from qgitc.agent.tools.apply_patch import ApplyPatchTool, DiffError
from qgitc.agent.tools.create_file import CreateFileTool
from qgitc.agent.tools.grep_search import GrepSearchTool
from qgitc.agent.tools.read_external_file import ReadExternalFileTool
from qgitc.agent.tools.read_file import ReadFileTool
from qgitc.agent.tools.run_command import RunCommandTool


def _make_context(working_directory):
    return ToolContext(
        working_directory=working_directory,
        abort_requested=lambda: False,
    )


class _TempDirMixin:
    """Mixin that provides a temporary directory for tests."""

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        def _remove_readonly(func, path, _):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        try:
            if sys.version_info < (3, 12):
                shutil.rmtree(self.tmpdir, onerror=_remove_readonly)
            else:
                shutil.rmtree(self.tmpdir, onexc=_remove_readonly)
        except Exception:
            pass
        super().tearDown()


# ======================================================================
# RunCommandTool
# ======================================================================


class TestRunCommandToolMeta(unittest.TestCase):
    def setUp(self):
        self.tool = RunCommandTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "run_command")

    def test_description(self):
        self.assertTrue(len(self.tool.description) > 0)

    def test_is_read_only(self):
        self.assertFalse(self.tool.is_read_only())

    def test_is_destructive(self):
        self.assertTrue(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        props = schema["properties"]
        self.assertIn("command", props)
        self.assertIn("workingDir", props)
        self.assertIn("timeout", props)
        self.assertIn("explanation", props)
        self.assertIn("command", schema["required"])
        self.assertIn("explanation", schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "run_command")


class TestRunCommandToolExecute(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tool = RunCommandTool()
        self.context = _make_context(self.tmpdir)

    def test_missing_command(self):
        result = self.tool.execute({}, self.context)
        self.assertTrue(result.is_error)
        self.assertIn("command is required", result.content)

    def test_invalid_working_dir(self):
        result = self.tool.execute(
            {"command": "echo hi", "explanation": "test"},
            _make_context("/nonexistent/path/xyz"),
        )
        self.assertTrue(result.is_error)
        self.assertIn("Invalid working directory", result.content)

    def test_successful_command(self):
        cmd = "echo hello"
        result = self.tool.execute(
            {"command": cmd, "explanation": "test"}, self.context
        )
        self.assertFalse(result.is_error)
        self.assertIn("hello", result.content)

    def test_failing_command(self):
        cmd = "exit 1" if os.name != "nt" else "cmd /c exit 1"
        result = self.tool.execute(
            {"command": cmd, "explanation": "test"}, self.context
        )
        self.assertTrue(result.is_error)

    def test_timeout(self):
        # Use a command that will definitely exceed 1 second
        if os.name == "nt":
            cmd = "ping -n 10 127.0.0.1"
        else:
            cmd = "sleep 10"
        result = self.tool.execute(
            {"command": cmd, "timeout": 1, "explanation": "test"},
            self.context,
        )
        self.assertTrue(result.is_error)
        self.assertIn("timed out", result.content)

    def test_no_output_success(self):
        # A command that succeeds but produces no output
        if os.name == "nt":
            cmd = "cd ."
        else:
            cmd = "true"
        result = self.tool.execute(
            {"command": cmd, "explanation": "test"}, self.context
        )
        self.assertFalse(result.is_error)
        self.assertIn("successfully", result.content)

    def test_custom_working_dir(self):
        sub = os.path.join(self.tmpdir, "sub")
        os.makedirs(sub)
        if os.name == "nt":
            cmd = "cd"
        else:
            cmd = "pwd"
        result = self.tool.execute(
            {"command": cmd, "workingDir": sub, "explanation": "test"},
            self.context,
        )
        self.assertFalse(result.is_error)
        # The output should contain the sub directory path
        self.assertIn("sub", result.content)


# ======================================================================
# ReadFileTool
# ======================================================================


class TestReadFileToolMeta(unittest.TestCase):
    def setUp(self):
        self.tool = ReadFileTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "read_file")

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("filePath", schema["properties"])
        self.assertIn("startLine", schema["properties"])
        self.assertIn("endLine", schema["properties"])
        self.assertIn("filePath", schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "read_file")


class TestReadFileToolExecute(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tool = ReadFileTool()
        self.context = _make_context(self.tmpdir)
        # Create a test file
        self.test_file = os.path.join(self.tmpdir, "test.txt")
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("line1\nline2\nline3\n")

    def test_missing_file_path(self):
        result = self.tool.execute({}, self.context)
        self.assertTrue(result.is_error)
        self.assertIn("filePath is required", result.content)

    def test_no_repo_dir(self):
        result = self.tool.execute(
            {"filePath": "test.txt"}, _make_context("")
        )
        self.assertTrue(result.is_error)

    def test_read_existing_file(self):
        result = self.tool.execute({"filePath": "test.txt"}, self.context)
        self.assertFalse(result.is_error)
        self.assertIn("line1", result.content)
        self.assertIn("line2", result.content)

    def test_read_nonexistent_file(self):
        result = self.tool.execute(
            {"filePath": "nonexistent.txt"}, self.context
        )
        self.assertTrue(result.is_error)
        self.assertIn("does not exist", result.content)

    def test_read_with_line_range(self):
        result = self.tool.execute(
            {"filePath": "test.txt", "startLine": 2, "endLine": 2},
            self.context,
        )
        self.assertFalse(result.is_error)
        self.assertIn("line2", result.content)

    def test_path_outside_repo(self):
        result = self.tool.execute(
            {"filePath": "../../etc/passwd"}, self.context
        )
        self.assertTrue(result.is_error)
        self.assertIn("outside the repository", result.content)


# ======================================================================
# ReadExternalFileTool
# ======================================================================


class TestReadExternalFileToolMeta(unittest.TestCase):
    def setUp(self):
        self.tool = ReadExternalFileTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "read_external_file")

    def test_is_read_only(self):
        self.assertFalse(self.tool.is_read_only())

    def test_is_destructive(self):
        self.assertTrue(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("filePath", schema["properties"])
        self.assertIn("explanation", schema["properties"])
        self.assertIn("filePath", schema["required"])
        self.assertIn("explanation", schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "read_external_file")


class TestReadExternalFileToolExecute(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tool = ReadExternalFileTool()
        self.context = _make_context(self.tmpdir)
        # Create a test file
        self.test_file = os.path.join(self.tmpdir, "external.txt")
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("external content\n")

    def test_missing_file_path(self):
        result = self.tool.execute(
            {"explanation": "test"}, self.context
        )
        self.assertTrue(result.is_error)
        self.assertIn("filePath is required", result.content)

    def test_relative_path_rejected(self):
        result = self.tool.execute(
            {"filePath": "relative/path.txt", "explanation": "test"},
            self.context,
        )
        self.assertTrue(result.is_error)
        self.assertIn("absolute filePath", result.content)

    def test_read_absolute_file(self):
        result = self.tool.execute(
            {"filePath": self.test_file, "explanation": "test"},
            self.context,
        )
        self.assertFalse(result.is_error)
        self.assertIn("external content", result.content)

    def test_nonexistent_file(self):
        result = self.tool.execute(
            {"filePath": os.path.join(self.tmpdir, "missing.txt"),
             "explanation": "test"},
            self.context,
        )
        self.assertTrue(result.is_error)
        self.assertIn("does not exist", result.content)


# ======================================================================
# GrepSearchTool
# ======================================================================


class TestGrepSearchToolMeta(unittest.TestCase):
    def setUp(self):
        self.tool = GrepSearchTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "grep_search")

    def test_is_read_only(self):
        self.assertTrue(self.tool.is_read_only())

    def test_is_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("query", schema["properties"])
        self.assertIn("isRegexp", schema["properties"])
        self.assertIn("includeIgnoredFiles", schema["properties"])
        self.assertIn("includePattern", schema["properties"])
        self.assertIn("maxResults", schema["properties"])
        self.assertIn("query", schema["required"])
        self.assertIn("isRegexp", schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "grep_search")


class TestGrepSearchToolExecute(unittest.TestCase):
    def setUp(self):
        self.tool = GrepSearchTool()

    def test_missing_query(self):
        context = _make_context("/tmp")
        result = self.tool.execute({"isRegexp": False}, context)
        self.assertTrue(result.is_error)
        self.assertIn("query is required", result.content)

    def test_missing_is_regexp(self):
        context = _make_context("/tmp")
        result = self.tool.execute({"query": "hello"}, context)
        self.assertTrue(result.is_error)
        self.assertIn("isRegexp is required", result.content)

    def test_no_repo_dir(self):
        context = _make_context("")
        result = self.tool.execute(
            {"query": "hello", "isRegexp": False}, context
        )
        self.assertTrue(result.is_error)

    @patch("qgitc.agent.tools.grep_search.grepSearch")
    def test_successful_search(self, mock_grep):
        mock_grep.return_value = "file.py:1: hello world"
        context = _make_context("/some/repo")
        result = self.tool.execute(
            {"query": "hello", "isRegexp": False}, context
        )
        self.assertFalse(result.is_error)
        self.assertIn("hello world", result.content)
        mock_grep.assert_called_once_with(
            repoDir="/some/repo",
            query="hello",
            isRegexp=False,
            includeIgnoredFiles=False,
            includePattern=None,
            maxResults=30,
        )

    @patch("qgitc.agent.tools.grep_search.grepSearch")
    def test_search_exception(self, mock_grep):
        mock_grep.side_effect = ValueError("Invalid regex: bad pattern")
        context = _make_context("/some/repo")
        result = self.tool.execute(
            {"query": "[bad", "isRegexp": True}, context
        )
        self.assertTrue(result.is_error)
        self.assertIn("Invalid regex", result.content)


# ======================================================================
# CreateFileTool
# ======================================================================


class TestCreateFileToolMeta(unittest.TestCase):
    def setUp(self):
        self.tool = CreateFileTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "create_file")

    def test_is_read_only(self):
        self.assertFalse(self.tool.is_read_only())

    def test_is_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("filePath", schema["properties"])
        self.assertIn("content", schema["properties"])
        self.assertIn("filePath", schema["required"])
        self.assertIn("content", schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "create_file")


class TestCreateFileToolExecute(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tool = CreateFileTool()
        self.context = _make_context(self.tmpdir)

    def test_missing_file_path(self):
        result = self.tool.execute({"content": "hello"}, self.context)
        self.assertTrue(result.is_error)
        self.assertIn("filePath is required", result.content)

    def test_missing_content(self):
        result = self.tool.execute({"filePath": "new.txt"}, self.context)
        self.assertTrue(result.is_error)
        self.assertIn("content is required", result.content)

    def test_create_new_file(self):
        result = self.tool.execute(
            {"filePath": "new.txt", "content": "hello world"},
            self.context,
        )
        self.assertFalse(result.is_error)
        self.assertIn("Created", result.content)
        self.assertIn("new.txt", result.content)
        # Verify file was actually created
        created = os.path.join(self.tmpdir, "new.txt")
        self.assertTrue(os.path.isfile(created))
        with open(created, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "hello world")

    def test_create_in_subdirectory(self):
        result = self.tool.execute(
            {"filePath": "sub/dir/new.txt", "content": "deep"},
            self.context,
        )
        self.assertFalse(result.is_error)
        created = os.path.join(self.tmpdir, "sub", "dir", "new.txt")
        self.assertTrue(os.path.isfile(created))

    def test_file_already_exists(self):
        existing = os.path.join(self.tmpdir, "exists.txt")
        with open(existing, "w") as f:
            f.write("existing")
        result = self.tool.execute(
            {"filePath": "exists.txt", "content": "new"},
            self.context,
        )
        self.assertTrue(result.is_error)
        self.assertIn("already exists", result.content)

    def test_path_outside_repo(self):
        result = self.tool.execute(
            {"filePath": "../../escape.txt", "content": "bad"},
            self.context,
        )
        self.assertTrue(result.is_error)
        self.assertIn("outside the repository", result.content)

    def test_no_repo_dir(self):
        result = self.tool.execute(
            {"filePath": "new.txt", "content": "hello"},
            _make_context(""),
        )
        self.assertTrue(result.is_error)


# ======================================================================
# ApplyPatchTool
# ======================================================================


class TestApplyPatchToolMeta(unittest.TestCase):
    def setUp(self):
        self.tool = ApplyPatchTool()

    def test_name(self):
        self.assertEqual(self.tool.name, "apply_patch")

    def test_is_read_only(self):
        self.assertFalse(self.tool.is_read_only())

    def test_is_destructive(self):
        self.assertFalse(self.tool.is_destructive())

    def test_input_schema(self):
        schema = self.tool.input_schema()
        self.assertEqual(schema["type"], "object")
        self.assertIn("input", schema["properties"])
        self.assertIn("explanation", schema["properties"])
        self.assertIn("input", schema["required"])
        self.assertIn("explanation", schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_openai_schema(self):
        schema = self.tool.openai_schema()
        self.assertEqual(schema["type"], "function")
        self.assertEqual(schema["function"]["name"], "apply_patch")


class TestApplyPatchToolExecute(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tool = ApplyPatchTool()
        self.context = _make_context(self.tmpdir)

    def test_missing_input(self):
        result = self.tool.execute(
            {"explanation": "test"}, self.context
        )
        self.assertTrue(result.is_error)
        self.assertIn("input is required", result.content)

    def test_empty_patch(self):
        result = self.tool.execute(
            {"input": "   ", "explanation": "test"}, self.context
        )
        self.assertTrue(result.is_error)
        self.assertIn("empty", result.content.lower())

    def test_no_repo_dir(self):
        result = self.tool.execute(
            {"input": "*** Begin Patch\n*** End Patch", "explanation": "test"},
            _make_context(""),
        )
        self.assertTrue(result.is_error)

    @patch("qgitc.agent.tools.apply_patch.process_patch")
    def test_successful_patch(self, mock_process):
        mock_process.return_value = "Applied 1 change to 1 file."
        result = self.tool.execute(
            {"input": "*** Begin Patch\n*** End Patch", "explanation": "test"},
            self.context,
        )
        self.assertFalse(result.is_error)
        self.assertIn("Applied", result.content)

    @patch("qgitc.agent.tools.apply_patch.process_patch")
    def test_diff_error(self, mock_process):
        mock_process.side_effect = DiffError("Hunk mismatch")
        result = self.tool.execute(
            {"input": "*** Begin Patch\n*** End Patch", "explanation": "test"},
            self.context,
        )
        self.assertTrue(result.is_error)
        self.assertIn("Hunk mismatch", result.content)

    @patch("qgitc.agent.tools.apply_patch.process_patch")
    def test_generic_exception(self, mock_process):
        mock_process.side_effect = RuntimeError("unexpected")
        result = self.tool.execute(
            {"input": "*** Begin Patch\n*** End Patch", "explanation": "test"},
            self.context,
        )
        self.assertTrue(result.is_error)
        self.assertIn("Failed to apply patch", result.content)

    def test_bom_stripped_from_input(self):
        """Verify BOM character is stripped from patch input."""
        with patch("qgitc.agent.tools.apply_patch.process_patch") as mock_process:
            mock_process.return_value = "ok"
            self.tool.execute(
                {"input": "\ufeff*** Begin Patch\n*** End Patch",
                 "explanation": "test"},
                self.context,
            )
            # The first arg to process_patch should have BOM stripped
            call_args = mock_process.call_args
            patch_text = call_args[0][0]
            self.assertFalse(patch_text.startswith("\ufeff"))


if __name__ == "__main__":
    unittest.main()
