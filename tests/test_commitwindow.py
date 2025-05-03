# -*- coding: utf-8 -*-
import os
import tempfile
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from qgitc.application import Application
from qgitc.gitutils import Git
from tests.base import TestBase, createRepo


class TestCommitWindow(TestBase):
    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(Application.CommitWindow)
        self.window.show()
        self.oldRepoDir = Git.REPO_DIR
        self.processEvents()

    def tearDown(self):
        Git.REPO_DIR = self.oldRepoDir
        self.window.close()
        self.processEvents()
        super().tearDown()

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

            self.window.cancel(True)
            self.processEvents()
            # fix `PermissionError`, don't known why it happens LoL
            QTest.qWait(500)

    def testChanges(self):
        self.window.cancel()
        self.processEvents()
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

            spyStatusFinished = QSignalSpy(self.window._statusFetcher.finished)
            spyStatusStarted = QSignalSpy(self.window._statusFetcher.started)
            spyRepoChange = QSignalSpy(self.app.repoDirChanged)
            self.app.updateRepoDir(dir)
            self.assertEqual(1, spyRepoChange.count())

            while self.window._statusFetcher.isRunning() or spyStatusFinished.count() != spyStatusStarted.count():
                self.processEvents()

            # the submodule thread still running
            if self.window._findSubmoduleThread:
                spySubmodule = QSignalSpy(self.window._findSubmoduleThread.finished)
                # _findSubmoduleThread will `None` on finished
                thread = self.window._findSubmoduleThread
                while thread.isRunning() or spySubmodule.count() == 0:
                    self.processEvents()

                # and it will cause another status fetching
                QTest.qWait(50)
                while self.window._statusFetcher.isRunning() or spyStatusFinished.count() != spyStatusStarted.count():
                    self.processEvents()

            lvFiles = self.window.ui.lvFiles
            filesModel = lvFiles.model()
            self.assertEqual(filesModel.rowCount(), 3)
            self.assertEqual(self.window._stagedModel.rowCount(), 0)

            changes = {
                filesModel.data(filesModel.index(0, 0)),
                filesModel.data(filesModel.index(1, 0)),
                filesModel.data(filesModel.index(2, 0)),
            }
            self.assertSetEqual(
                changes, {"test.txt", subRepoFile, ".gitignore"})

            self.processEvents()
            rc = lvFiles.visualRect(filesModel.index(0, 0))
            self.assertFalse(rc.isEmpty())

            QTest.mouseClick(lvFiles.viewport(), Qt.LeftButton, pos=rc.center())
            self.processEvents()

            indexes = lvFiles.selectedIndexes()
            self.assertEqual(len(indexes), 1)
            self.assertEqual(indexes[0].row(), 0)
            oldFile = filesModel.data(indexes[0])

            spyFinished = QSignalSpy(self.window._submoduleExecutor.finished)
            QTest.mouseClick(self.window.ui.tbStage, Qt.LeftButton)
            while spyFinished.count() == 0:
                self.processEvents()

            stagedModel = self.window.ui.lvStaged.model()
            self.assertEqual(stagedModel.rowCount(), 1)
            self.assertEqual(oldFile, stagedModel.data(stagedModel.index(0, 0)))
            self.assertEqual(filesModel.rowCount(), 2)

            spyFinished = QSignalSpy(self.window._submoduleExecutor.finished)
            QTest.mouseClick(self.window.ui.tbStageAll, Qt.LeftButton)
            self.processEvents()
            while spyFinished.count() == 0:
                self.processEvents()

            self.assertEqual(stagedModel.rowCount(), 3)
            self.assertEqual(filesModel.rowCount(), 0)

            lvStaged = self.window.ui.lvStaged
            rc = lvStaged.visualRect(stagedModel.index(1, 0))
            self.assertFalse(rc.isEmpty())

            QTest.mouseClick(lvStaged.viewport(), Qt.LeftButton, pos=rc.center())
            self.processEvents()

            spyFinished = QSignalSpy(self.window._submoduleExecutor.finished)
            oldFile = stagedModel.data(stagedModel.index(1, 0))
            QTest.mouseClick(self.window.ui.tbUnstage, Qt.LeftButton)
            while spyFinished.count() == 0:
                self.processEvents()

            self.assertEqual(stagedModel.rowCount(), 2)
            self.assertEqual(filesModel.rowCount(), 1)
            self.assertEqual(oldFile, filesModel.data(filesModel.index(0, 0)))

            spyFinished = QSignalSpy(self.window._submoduleExecutor.finished)
            QTest.mouseClick(self.window.ui.tbUnstageAll, Qt.LeftButton)
            while spyFinished.count() == 0:
                self.processEvents()

            self.assertEqual(stagedModel.rowCount(), 0)
            self.assertEqual(filesModel.rowCount(), 3)

            self.window.cancel(True)
            self.processEvents()
