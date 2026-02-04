# -*- coding: utf-8 -*-

import json
import os
import tempfile

from qgitc.agenttoolexecutor import AgentToolExecutor
from qgitc.gitutils import Git
from tests.base import TestBase


class TestAgentReadFile(TestBase):
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

        executor = AgentToolExecutor()
        result = executor._handle_read_file(
            "read_file",
            {
                "filePath": "gbk_sample.txt",
            },
        )

        assert result.ok, result.output
        meta, content = self._parseOutput(result.output)
        self.assertEqual(content, text)
        self.assertEqual(meta["totalLines"], 3)
        self.assertEqual(meta["startLine"], 1)
        self.assertEqual(meta["endLine"], 3)

    def test_read_file_gbk_line_slicing(self):
        text = "第一行\n第二行\n第三行\n"
        path = os.path.join(Git.REPO_DIR, "gbk_sample2.txt")
        with open(path, "wb") as f:
            f.write(text.encode("gbk"))

        executor = AgentToolExecutor()
        result = executor._handle_read_file(
            "read_file",
            {
                "filePath": "gbk_sample2.txt",
                "startLine": 2,
                "endLine": 2,
            },
        )

        assert result.ok, result.output
        meta, content = self._parseOutput(result.output)
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

        executor = AgentToolExecutor()
        result = executor._handle_read_file(
            "read_file",
            {
                "filePath": "crlf_sample.txt",
                "startLine": 1,
                "endLine": 2,
            },
        )

        assert result.ok, result.output
        _, content = self._parseOutput(result.output)
        self.assertEqual(content, "line1\r\nline2\r\n")

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
                "filePath": "last_line_sample.txt",
                "startLine": 3,
                "endLine": 3,
            },
        )

        assert result.ok, result.output
        meta, content = self._parseOutput(result.output)
        self.assertEqual(content, "ccc\n")
        self.assertEqual(meta["startLine"], 3)
        self.assertEqual(meta["endLine"], 3)

    def test_read_file_absolute_outside_repo_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            absPath = os.path.join(td, "outside.txt")
            with open(absPath, "w", encoding="utf-8") as f:
                f.write("hello\nworld\n")

            executor = AgentToolExecutor()
            result = executor._handle_read_file(
                "read_file",
                {
                    "filePath": absPath,
                },
            )

            assert not result.ok
            assert "outside the repository" in result.output
