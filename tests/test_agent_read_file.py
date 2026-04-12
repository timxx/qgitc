# -*- coding: utf-8 -*-

import json
import os
import tempfile
from unittest.mock import patch

from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tools.read_file import ReadFileTool
from qgitc.gitutils import Git
from qgitc.tools import readfile as readfile_tool
from tests.base import TestBase


def _make_context(working_directory):
    return ToolContext(
        working_directory=working_directory,
        abort_requested=lambda: False,
    )


class TestAgentReadFile(TestBase):
    def setUp(self):
        super().setUp()
        self.tool = ReadFileTool()
        self.context = _make_context(Git.REPO_DIR)

    def _parseOutput(self, output: str):
        assert output.startswith("<<<METADATA>>>\n"), output
        rest = output[len("<<<METADATA>>>\n"):]
        metaJson, content = rest.split("\n<<<CONTENT>>>\n", 1)
        meta = json.loads(metaJson)
        return meta, content

    def test_read_file_decodes_gbk(self):
        # Include non-ascii text to ensure gbk decoding path is exercised.
        text = "第一行\n第二行\n第三行"
        path = os.path.join(Git.REPO_DIR, "gbk_sample.txt")
        with open(path, "wb") as f:
            f.write(text.encode("gbk"))

        result = self.tool.execute(
            {"filePath": "gbk_sample.txt"},
            self.context,
        )

        assert not result.is_error, result.content
        meta, content = self._parseOutput(result.content)
        self.assertEqual(content, text)
        self.assertEqual(meta["totalLines"], 3)
        self.assertEqual(meta["startLine"], 1)
        self.assertEqual(meta["endLine"], 3)

    def test_read_file_gbk_line_slicing(self):
        text = "第一行\n第二行\n第三行\n"
        path = os.path.join(Git.REPO_DIR, "gbk_sample2.txt")
        with open(path, "wb") as f:
            f.write(text.encode("gbk"))

        result = self.tool.execute(
            {
                "filePath": "gbk_sample2.txt",
                "startLine": 2,
                "endLine": 2,
            },
            self.context,
        )

        assert not result.is_error, result.content
        meta, content = self._parseOutput(result.content)
        self.assertEqual(content, "第二行\n")
        self.assertEqual(meta["startLine"], 2)
        self.assertEqual(meta["endLine"], 2)

    def test_read_file_preserves_crlf_newlines(self):
        # Ensure we preserve original newline sequences (e.g. CRLF) and
        # don't normalize them away.
        data = b"line1\r\nline2\r\nline3\r\n"
        path = os.path.join(Git.REPO_DIR, "crlf_sample.txt")
        with open(path, "wb") as f:
            f.write(data)

        result = self.tool.execute(
            {
                "filePath": "crlf_sample.txt",
                "startLine": 1,
                "endLine": 2,
            },
            self.context,
        )

        assert not result.is_error, result.content
        _, content = self._parseOutput(result.content)
        self.assertEqual(content, "line1\r\nline2\r\n")

    def test_read_file_end_line_last_line(self):
        # end_line should be able to address the last line and preserve
        # its newline when present.
        data = b"a\nB\nccc\n"
        path = os.path.join(Git.REPO_DIR, "last_line_sample.txt")
        with open(path, "wb") as f:
            f.write(data)

        result = self.tool.execute(
            {
                "filePath": "last_line_sample.txt",
                "startLine": 3,
                "endLine": 3,
            },
            self.context,
        )

        assert not result.is_error, result.content
        meta, content = self._parseOutput(result.content)
        self.assertEqual(content, "ccc\n")
        self.assertEqual(meta["startLine"], 3)
        self.assertEqual(meta["endLine"], 3)

    def test_read_file_absolute_outside_repo_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            absPath = os.path.join(td, "outside.txt")
            with open(absPath, "w", encoding="utf-8") as f:
                f.write("hello\nworld\n")

            result = self.tool.execute(
                {"filePath": absPath},
                self.context,
            )

            assert result.is_error
            assert "outside the repository" in result.content

    def test_read_file_blocks_symlink_escape(self):
        with tempfile.TemporaryDirectory() as td:
            outsidePath = os.path.join(td, "outside.txt")
            with open(outsidePath, "w", encoding="utf-8") as f:
                f.write("hello\n")

            linkPath = os.path.join(Git.REPO_DIR, "link_outside.txt")
            try:
                os.symlink(outsidePath, linkPath)
            except (OSError, NotImplementedError) as e:
                self.skipTest(f"symlink not supported: {e}")

            result = self.tool.execute(
                {"filePath": "link_outside.txt"},
                self.context,
            )

            assert result.is_error
            assert "outside the repository" in result.content

    def test_normalize_tool_file_path_windows_drive_prefix_only(self):
        # Regression test: only strip the leading slash for the specific "/C:/" pattern.
        with patch.object(readfile_tool.os, "name", "nt"):
            self.assertEqual(
                readfile_tool.normalizeToolFilePath(" /C:/temp/x.txt "),
                "C:/temp/x.txt",
            )
            self.assertEqual(readfile_tool.normalizeToolFilePath(
                "/etc/hosts"), "/etc/hosts")
            self.assertEqual(
                readfile_tool.normalizeToolFilePath("//server/share/file.txt"),
                "//server/share/file.txt",
            )
            self.assertEqual(readfile_tool.normalizeToolFilePath(
                "/tmp/foo:bar"), "/tmp/foo:bar")
