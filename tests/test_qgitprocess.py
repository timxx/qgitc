# -*- coding: utf-8 -*-

from PySide6.QtCore import QTimer

from qgitc.gitutils import Git, QGitProcess
from tests.base import TestBase


class TestGitProcess(TestBase):

    def testCheckOutput(self):
        process = QGitProcess(Git.REPO_DIR, ["version"])
        output, error = process.communicate()
        self.assertIsNotNone(output)
        self.assertTrue(not error)

        self.assertTrue(isinstance(output, bytes))

    def testCheckOutputText(self):
        process = QGitProcess(Git.REPO_DIR, ["version"], True)
        output, error = process.communicate()
        self.assertIsNotNone(output)
        self.assertTrue(not error)

        self.assertTrue(isinstance(output, str))

    def testTerminate(self):
        args = ["blame", "-L", "1,1", "-p",
                "--root", "--contents=-", "--", "README.md"]
        # use `--contents=-` to make it wait for input
        process = QGitProcess(Git.REPO_DIR, args)
        QTimer.singleShot(500, process.terminate)
        output, error = process.communicate()
        self.assertTrue(process.isCrashed())
        self.assertIsNone(output)
        self.assertIsNone(error)
