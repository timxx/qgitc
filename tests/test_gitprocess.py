# -*- coding: utf-8 -*-

from qgitc.gitutils import Git, GitProcess
from tests.base import TestBase


class TestGitProcess(TestBase):

    def testGitBin(self):
        self.assertIsNotNone(GitProcess.GIT_BIN)

    def testCheckOutput(self):
        process = GitProcess(Git.REPO_DIR, ["version"])
        output, error = process.communicate()
        self.assertIsNotNone(output)
        self.assertTrue(not error)

        self.assertTrue(isinstance(output, bytes))

    def testCheckOutputText(self):
        process = GitProcess(Git.REPO_DIR, ["version"], True)
        output, error = process.communicate()
        self.assertIsNotNone(output)
        self.assertTrue(not error)

        self.assertTrue(isinstance(output, str))
