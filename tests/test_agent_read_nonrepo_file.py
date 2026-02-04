# -*- coding: utf-8 -*-

import json
import os
import tempfile

from qgitc.agenttoolexecutor import AgentToolExecutor
from qgitc.gitutils import Git
from tests.base import TestBase


class TestAgentReadNonRepoFile(TestBase):
    def _parseOutput(self, output: str):
        assert output.startswith("<<<METADATA>>>\n"), output
        rest = output[len("<<<METADATA>>>\n"):]
        metaJson, content = rest.split("\n<<<CONTENT>>>\n", 1)
        meta = json.loads(metaJson)
        return meta, content

    def test_requires_absolute_path(self):
        executor = AgentToolExecutor()
        result = executor._handle_read_nonrepo_file(
            "read_nonrepo_file",
            {
                "filePath": "relative.txt",
                "explanation": "Need to inspect an external file",
            },
        )
        assert not result.ok
        assert "absolute" in result.output.lower()

    def test_allows_repo_path_even_if_absolute(self):
        executor = AgentToolExecutor()
        absPath = os.path.join(Git.REPO_DIR, "README.md")
        result = executor._handle_read_nonrepo_file(
            "read_nonrepo_file",
            {
                "filePath": absPath,
                "explanation": "Read a repo file by absolute path",
            },
        )
        assert result.ok, result.output
        meta, content = self._parseOutput(result.output)
        assert meta["path"] == os.path.abspath(absPath)
        assert meta["totalLines"] >= 1
        assert content

    def test_does_not_require_repo_to_be_open(self):
        oldRepoDir = getattr(Git, "REPO_DIR", None)
        try:
            Git.REPO_DIR = ""
            with tempfile.TemporaryDirectory() as td:
                absPath = os.path.join(td, "outside.txt")
                with open(absPath, "w", encoding="utf-8", newline="\n") as f:
                    f.write("hello\nworld\n")

                executor = AgentToolExecutor()
                result = executor._handle_read_nonrepo_file(
                    "read_nonrepo_file",
                    {
                        "filePath": absPath,
                        "startLine": 1,
                        "endLine": 1,
                        "explanation": "Read a temp file without a repo",
                    },
                )
                assert result.ok, result.output
        finally:
            Git.REPO_DIR = oldRepoDir

    def test_reads_outside_repo_with_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            absPath = os.path.join(td, "outside.txt")
            with open(absPath, "w", encoding="utf-8", newline="\n") as f:
                f.write("hello\nworld\n")

            executor = AgentToolExecutor()
            result = executor._handle_read_nonrepo_file(
                "read_nonrepo_file",
                {
                    "filePath": absPath,
                    "startLine": 2,
                    "endLine": 2,
                    "explanation": "Read a temp file for debugging",
                },
            )

            assert result.ok, result.output
            meta, content = self._parseOutput(result.output)
            assert content == "world\n"
            assert meta["totalLines"] == 2
            assert meta["startLine"] == 2
            assert meta["endLine"] == 2
