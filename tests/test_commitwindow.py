# -*- coding: utf-8 -*-
import os
import tempfile
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QDialog
from qgitc.application import Application
from qgitc.gitutils import Git
from tests.base import TestBase, createRepo
from tests.mockgithubcopilot import MockGithubCopilotStep, MockGithubCopilot


class TestCommitWindow(TestBase):
    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(Application.CommitWindow)
        self.window.show()
        self.processEvents()

    def tearDown(self):
        self.window.close()
        self.processEvents()
        super().tearDown()

    def createSubRepo(self):
        return True

    def waitForLoaded(self):
        thread = self.window._findSubmoduleThread
        if thread:
            while thread.isRunning():
                self.processEvents()
        while self.window._statusFetcher.isRunning():
            self.processEvents()

        self.wait(50)

    def testRepoChanged(self):
        self.waitForLoaded()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as dir:
            createRepo(dir)

            with patch("qgitc.commitwindow.CommitWindow._onRepoDirChanged") as mock:
                self.app.updateRepoDir(dir)
                self.processEvents()
                mock.assert_called_once()

    def testNoChanges(self):
        self.waitForLoaded()

        self.assertEqual(self.window._filesModel.rowCount(), 0)
        self.assertEqual(self.window._stagedModel.rowCount(), 0)

        self.window.cancel(True)
        self.processEvents()

    def testChanges(self):
        self.waitForLoaded()

        with open(os.path.join(self.gitDir.name, "test.txt"), "w+") as f:
            f.write("test")

        subRepoFile = os.path.join("subRepo", "test.py")
        with open(os.path.join(self.gitDir.name, subRepoFile), "a+") as f:
            f.write("# new line\n")

        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        lvFiles = self.window.ui.lvFiles
        filesModel = lvFiles.model()
        self.assertEqual(filesModel.rowCount(), 2)
        self.assertEqual(self.window._stagedModel.rowCount(), 0)

        changes = {
            filesModel.data(filesModel.index(0, 0)),
            filesModel.data(filesModel.index(1, 0)),
        }
        self.assertSetEqual(changes, {"test.txt", subRepoFile})

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
        self.assertEqual(filesModel.rowCount(), 1)

        spyFinished = QSignalSpy(self.window._submoduleExecutor.finished)
        QTest.mouseClick(self.window.ui.tbStageAll, Qt.LeftButton)
        self.processEvents()
        while spyFinished.count() == 0:
            self.processEvents()

        self.assertEqual(stagedModel.rowCount(), 2)
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

        self.assertEqual(stagedModel.rowCount(), 1)
        self.assertEqual(filesModel.rowCount(), 1)
        self.assertEqual(oldFile, filesModel.data(filesModel.index(0, 0)))

        spyFinished = QSignalSpy(self.window._submoduleExecutor.finished)
        QTest.mouseClick(self.window.ui.tbUnstageAll, Qt.LeftButton)
        while spyFinished.count() == 0:
            self.processEvents()

        self.assertEqual(stagedModel.rowCount(), 0)
        self.assertEqual(filesModel.rowCount(), 2)

        self.window.cancel(True)
        self.processEvents()

    def testOptions(self):
        self.waitForLoaded()

        with patch("qgitc.preferences.Preferences.exec") as mock:
            mock.return_value = QDialog.Rejected
            QTest.mouseClick(self.window.ui.tbOptions, Qt.LeftButton)
            mock.assert_called_once()

    def testAiMessage(self):
        self.waitForLoaded()

        # no local changes by default
        self.assertFalse(self.window.ui.btnGenMessage.isEnabled())
        self.assertTrue(self.window.ui.btnCancelGen.isHidden())

        with open(os.path.join(self.gitDir.name, "test.py"), "a+") as f:
            f.write("# new line\n")

        Git.addFiles(repoDir=self.gitDir.name, files=["test.py"])

        spyStatus = QSignalSpy(self.window._statusFetcher.finished)
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        while self.window._statusFetcher.isRunning() or spyStatus.count() == 0:
            self.processEvents()

        self.assertTrue(self.window.ui.btnGenMessage.isEnabled())
        # no message by default
        self.assertFalse(self.window.ui.btnRefineMsg.isEnabled())

        with MockGithubCopilot(self) as mock:
            spyFinished = QSignalSpy(self.window._aiMessage.messageAvailable)
            QTest.mouseClick(self.window.ui.btnGenMessage, Qt.LeftButton)
            self.processEvents()
            self.assertTrue(self.window.ui.btnCancelGen.isVisible())
            self.assertFalse(self.window.ui.btnGenMessage.isVisible())
            self.assertFalse(self.window.ui.btnRefineMsg.isEnabled())
            self.assertTrue(self.window.ui.btnRefineMsg.isVisible())

            while spyFinished.count() == 0:
                self.processEvents()
            self.assertEqual(spyFinished.at(0)[0], "This is a mock response")
            self.assertEqual(
                self.window.ui.teMessage.toPlainText(), "This is a mock response")
            self.assertTrue(self.window.ui.btnRefineMsg.isEnabled())

            mock.assertEverythingOK()

        self.processEvents()

        # clear the token for the next test
        self.app.settings().setGithubCopilotAccessToken("")
        self.app.settings().setGithubCopilotToken("")

        with MockGithubCopilot(self, MockGithubCopilotStep.LoginAccessDenied) as mock:
            spyFinished = QSignalSpy(self.window._aiMessage.messageAvailable)
            QTest.mouseClick(self.window.ui.btnRefineMsg, Qt.LeftButton)
            self.processEvents()
            self.assertTrue(self.window.ui.btnCancelGen.isVisible())
            self.assertTrue(self.window.ui.btnGenMessage.isVisible())
            self.assertFalse(self.window.ui.btnGenMessage.isEnabled())
            self.assertFalse(self.window.ui.btnRefineMsg.isVisible())

            while spyFinished.count() == 0:
                self.processEvents()
            self.assertEqual(spyFinished.at(0)[0], "")

            mock.assertEverythingOK()

        self.wait(50)
        self.window.cancel(True)
