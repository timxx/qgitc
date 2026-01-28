# -*- coding: utf-8 -*-

import os

from qgitc.agenttoolexecutor import AgentToolExecutor
from qgitc.gitutils import Git
from tests.base import TestBase


class TestAgentReadFile(TestBase):
    def test_read_file_decodes_gbk(self):
        # Include non-ascii text to ensure gbk decoding path is exercised.
        text = "第一行\n第二行\n第三行"
        path = os.path.join(Git.REPO_DIR, "gbk_sample.txt")
        with open(path, "wb") as f:
            f.write(text.encode("gbk"))

        executor = AgentToolExecutor()
        result = executor._handle_read_file(
            "read_file",
            {
                "file_path": "gbk_sample.txt",
            },
        )

        assert result.ok, result.output
        self.assertEqual(result.output, text)

    def test_read_file_gbk_line_slicing(self):
        text = "第一行\n第二行\n第三行\n"
        path = os.path.join(Git.REPO_DIR, "gbk_sample2.txt")
        with open(path, "wb") as f:
            f.write(text.encode("gbk"))

        executor = AgentToolExecutor()
        result = executor._handle_read_file(
            "read_file",
            {
                "file_path": "gbk_sample2.txt",
                "start_line": 2,
                "end_line": 2,
            },
        )

        assert result.ok, result.output
        self.assertEqual(result.output, "第二行\n")

    def test_read_file_preserves_crlf_newlines(self):
        # Ensure we preserve original newline sequences (e.g. CRLF) and
        # don't normalize them away.
        data = b"line1\r\nline2\r\nline3\r\n"
        path = os.path.join(Git.REPO_DIR, "crlf_sample.txt")
        with open(path, "wb") as f:
            f.write(data)

        executor = AgentToolExecutor()
        result = executor._handle_read_file(
            "read_file",
            {
                "file_path": "crlf_sample.txt",
                "start_line": 1,
                "end_line": 2,
            },
        )

        assert result.ok, result.output
        self.assertEqual(result.output, "line1\r\nline2\r\n")

    def test_read_file_end_line_last_line(self):
        # end_line should be able to address the last line and preserve
        # its newline when present.
        data = b"a\nB\nccc\n"
        path = os.path.join(Git.REPO_DIR, "last_line_sample.txt")
        with open(path, "wb") as f:
            f.write(data)

        executor = AgentToolExecutor()
        result = executor._handle_read_file(
            "read_file",
            {
                "file_path": "last_line_sample.txt",
                "start_line": 3,
                "end_line": 3,
            },
        )

        assert result.ok, result.output
        self.assertEqual(result.output, "ccc\n")
