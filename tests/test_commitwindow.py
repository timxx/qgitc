# -*- coding: utf-8 -*-
import os
import tempfile
from unittest.mock import patch
from PySide6.QtTest import QTest, QSignalSpy
from qgitc.application import Application
from qgitc.gitutils import Git
from tests.base import TestBase, createRepo


class TestCommitWindow(TestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.window = cls.app.getWindow(Application.CommitWindow)
        cls.window.show()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        super().tearDownClass()

    def setUp(self):
        self.oldRepoDir = Git.REPO_DIR
        self.window.cancel()
        self.processEvents()

    def tearDown(self):
        Git.REPO_DIR = self.oldRepoDir
        self.window.cancel()
        self.processEvents()

    def testRepoChanged(self):
        with tempfile.TemporaryDirectory() as dir:
            createRepo(dir)

            with patch("qgitc.commitwindow.CommitWindow._onRepoDirChanged") as mock:
                self.app.updateRepoDir(dir)
                self.processEvents()
                mock.assert_called_once()

    def testNoChanges(self):
        with tempfile.TemporaryDirectory() as dir:
            createRepo(dir)
            self.processEvents()

            spy = QSignalSpy(self.window._statusFetcher.finished)

            self.app.updateRepoDir(dir)
            while self.window._statusFetcher.isRunning() or spy.count() == 0:
                self.processEvents()

            self.processEvents()
            self.assertEqual(self.window._filesModel.rowCount(), 0)
            self.assertEqual(self.window._stagedModel.rowCount(), 0)

            self.window.cancel()
            self.processEvents()
            # fix `PermissionError`, don't known why it happens LoL
            QTest.qWait(500)

    def testChanges(self):
        with tempfile.TemporaryDirectory() as dir:
            createRepo(dir)
            with open(os.path.join(dir, ".gitignore"), "w+") as f:
                f.write("/subRepo/\n")
            with open(os.path.join(dir, "test.txt"), "w+") as f:
                f.write("test")

            createRepo(os.path.join(dir, "subRepo"))
            subRepoFile = os.path.join("subRepo", "test.py")
            with open(os.path.join(dir, subRepoFile), "a+") as f:
                f.write("# new line\n")

            spySubmodule = QSignalSpy(self.window._findSubmoduleThread.finished)
            spyStatusFinished = QSignalSpy(self.window._statusFetcher.finished)
            spyStatusStarted = QSignalSpy(self.window._statusFetcher.started)

            self.processEvents()
            self.app.updateRepoDir(dir)
            while self.window._findSubmoduleThread.isRunning() or spySubmodule.count() == 0:
                self.processEvents()

            self.processEvents()
            while self.window._statusFetcher.isRunning() or spyStatusFinished.count() != spyStatusStarted.count():
                self.processEvents()

            QTest.qWait(50)
            self.processEvents()

            filesModel = self.window._filesModel
            self.assertEqual(filesModel.rowCount(), 3)
            self.assertEqual(self.window._stagedModel.rowCount(), 0)

            changes = {
                filesModel.data(filesModel.index(0, 0)),
                filesModel.data(filesModel.index(1, 0)),
                filesModel.data(filesModel.index(2, 0)),
            }
            self.assertSetEqual(
                changes, {"test.txt", subRepoFile, ".gitignore"})

            self.window.cancel()
            self.processEvents()
