# -*- coding: utf-8 -*-

import json
import os
import tempfile

from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tools.read_external_file import ReadExternalFileTool
from qgitc.gitutils import Git
from tests.base import TestBase


def _make_context(working_directory):
    return ToolContext(
        working_directory=working_directory,
        abort_requested=lambda: False,
    )


class TestAgentReadExternalFile(TestBase):
    def setUp(self):
        super().setUp()
        self.tool = ReadExternalFileTool()
        self.context = _make_context(Git.REPO_DIR)

    def _parseOutput(self, output: str):
        assert output.startswith("<<<METADATA>>>\n"), output
        rest = output[len("<<<METADATA>>>\n"):]
        metaJson, content = rest.split("\n<<<CONTENT>>>\n", 1)
        meta = json.loads(metaJson)
        return meta, content

    def test_requires_absolute_path(self):
        result = self.tool.execute(
            {
                "filePath": "relative.txt",
                "explanation": "Need to inspect an external file",
            },
            self.context,
        )
        assert result.is_error
        assert "absolute" in result.content.lower()

    def test_allows_repo_path_even_if_absolute(self):
        absPath = os.path.join(Git.REPO_DIR, "README.md")
        result = self.tool.execute(
            {
                "filePath": absPath,
                "explanation": "Read a repo file by absolute path",
            },
            self.context,
        )
        assert not result.is_error, result.content
        meta, content = self._parseOutput(result.content)
        assert meta["path"] == os.path.abspath(absPath)
        assert meta["totalLines"] >= 1
        assert content

    def test_does_not_require_repo_to_be_open(self):
        with tempfile.TemporaryDirectory() as td:
            absPath = os.path.join(td, "outside.txt")
            with open(absPath, "w", encoding="utf-8", newline="\n") as f:
                f.write("hello\nworld\n")

            context = _make_context("")
            result = self.tool.execute(
                {
                    "filePath": absPath,
                    "startLine": 1,
                    "endLine": 1,
                    "explanation": "Read a temp file without a repo",
                },
                context,
            )
            assert not result.is_error, result.content

    def test_reads_outside_repo_with_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            absPath = os.path.join(td, "outside.txt")
            with open(absPath, "w", encoding="utf-8", newline="\n") as f:
                f.write("hello\nworld\n")

            result = self.tool.execute(
                {
                    "filePath": absPath,
                    "startLine": 2,
                    "endLine": 2,
                    "explanation": "Read a temp file for debugging",
                },
                self.context,
            )

            assert not result.is_error, result.content
            meta, content = self._parseOutput(result.content)
            assert content == "world\n"
            assert meta["totalLines"] == 2
            assert meta["startLine"] == 2
            assert meta["endLine"] == 2
