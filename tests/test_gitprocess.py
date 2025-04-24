# -*- coding: utf-8 -*-
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest, QSignalSpy
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

    def testTerminate(self):
        args = ["blame", "-L", "1,1", "-p",
                "--root", "--contents=-", "--", __file__]
        # use `--contents=-` to make it wait for input
        process = GitProcess(Git.REPO_DIR, args)
        QTimer.singleShot(500, process.terminate)
        output, error = process.communicate()
        self.assertTrue(process.isCrashed())
        self.assertIsNone(output)
        self.assertIsNone(error)
