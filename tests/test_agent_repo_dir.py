# -*- coding: utf-8 -*-

import os
import tempfile

from qgitc.agenttoolexecutor import AgentToolExecutor
from qgitc.gitutils import Git
from tests.base import TestBase


class TestAgentRepoDirResolution(TestBase):
    def createSubRepo(self):
        return True

    def test_git_status_repoDir_relative_resolves_against_git_repo_dir(self):
        # Regression: tool calls may supply repoDir as a repo-relative path (like "."),
        # and the process cwd may not be Git.REPO_DIR. Ensure we resolve relative repoDir
        # against Git.REPO_DIR (not against the current working directory).

        assert Git.REPO_DIR

        oldCwd = os.getcwd()
        with tempfile.TemporaryDirectory() as td:
            os.chdir(td)
            try:
                executor = AgentToolExecutor()
                result = executor._handle_git_status(
                    "git_status",
                    {
                        "repoDir": ".",
                    },
                )
            finally:
                os.chdir(oldCwd)

        self.assertTrue(result.ok, msg=result.output)
        self.assertIn("working tree clean", result.output)

    def test_git_status_repoDir_outside_repo_rejected(self):
        assert Git.REPO_DIR

        outside = os.path.abspath(os.path.join(Git.REPO_DIR, os.pardir))
        executor = AgentToolExecutor()
        result = executor._handle_git_status(
            "git_status",
            {
                "repoDir": outside,
            },
        )

        self.assertFalse(result.ok)
        self.assertIn("outside the repository", result.output)

    def test_relative_subRepo(self):
        assert Git.REPO_DIR

        executor = AgentToolExecutor()
        result = executor._handle_git_status(
            "git_status",
            {
                "repoDir": "subRepo",
            },
        )

        self.assertTrue(result.ok, msg=result.output)
        self.assertIn("working tree clean", result.output)

    def test_abs_subRepo(self):
        assert Git.REPO_DIR

        subRepoPath = os.path.join(Git.REPO_DIR, "subRepo")
        executor = AgentToolExecutor()
        result = executor._handle_git_status(
            "git_status",
            {
                "repoDir": subRepoPath,
            },
        )

        self.assertTrue(result.ok, msg=result.output)
        self.assertIn("working tree clean", result.output)
