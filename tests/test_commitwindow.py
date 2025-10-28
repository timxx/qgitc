# -*- coding: utf-8 -*-
import os
from unittest import mock
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QDialog

from qgitc.aichatwindow import AiChatWidget, AiChatWindow
from qgitc.events import CodeReviewEvent
from qgitc.gitutils import Git
from qgitc.llm import AiModelBase
from qgitc.windowtype import WindowType
from tests.base import TemporaryDirectory, TestBase, createRepo
from tests.mockgithubcopilot import MockGithubCopilot, MockGithubCopilotStep


class TestCommitWindow(TestBase):
    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(WindowType.CommitWindow)
        self.window.show()
        self.processEvents()

    def tearDown(self):
        self.window.close()
        self.processEvents()
        super().tearDown()

    def createSubRepo(self):
        return True

    def waitForLoaded(self):
        self.wait(10000, self.window._statusFetcher.isRunning)
        self.wait(10000, self.window._infoFetcher.isRunning)
        self.wait(10000, self.window._submoduleExecutor.isRunning)

        self.wait(50)

    def testRepoChanged(self):
        self.waitForLoaded()

        with TemporaryDirectory() as dir:
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
        self.wait(10000, lambda: spyFinished.count() == 0)

        stagedModel = self.window.ui.lvStaged.model()
        self.assertEqual(stagedModel.rowCount(), 1)
        self.assertEqual(oldFile, stagedModel.data(stagedModel.index(0, 0)))
        self.assertEqual(filesModel.rowCount(), 1)

        spyFinished = QSignalSpy(self.window._submoduleExecutor.finished)
        QTest.mouseClick(self.window.ui.tbStageAll, Qt.LeftButton)
        self.processEvents()
        self.wait(10000, lambda: spyFinished.count() == 0)

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
        self.wait(10000, lambda: spyFinished.count() == 0)

        self.assertEqual(stagedModel.rowCount(), 1)
        self.assertEqual(filesModel.rowCount(), 1)
        self.assertEqual(oldFile, filesModel.data(filesModel.index(0, 0)))

        spyFinished = QSignalSpy(self.window._submoduleExecutor.finished)
        QTest.mouseClick(self.window.ui.tbUnstageAll, Qt.LeftButton)
        self.wait(10000, lambda: spyFinished.count() == 0)

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

        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        self.wait(500)
        self.assertTrue(self.window.ui.btnGenMessage.isEnabled())
        # no message by default
        self.assertTrue(self.window.ui.teMessage.document(
        ).isEmpty() or self.window.ui.btnRefineMsg.isEnabled())

        with MockGithubCopilot(self) as mock:
            spyError = QSignalSpy(self.window._aiMessage.messageAvailable)
            QTest.mouseClick(self.window.ui.btnGenMessage, Qt.LeftButton)
            self.processEvents()
            self.assertTrue(self.window.ui.btnCancelGen.isVisible())
            self.assertFalse(self.window.ui.btnGenMessage.isVisible())
            self.assertFalse(self.window.ui.btnRefineMsg.isEnabled())
            self.assertTrue(self.window.ui.btnRefineMsg.isVisible())

            self.wait(10000, lambda: spyError.count() == 0)
            self.assertEqual(spyError.at(0)[0], "This is a mock response")
            self.assertEqual(
                self.window.ui.teMessage.toPlainText(), "This is a mock response")
            self.assertTrue(self.window.ui.btnRefineMsg.isEnabled())

            mock.assertEverythingOK()

        self.processEvents()

        # clear the token for the next test
        self.app.settings().setGithubCopilotAccessToken("")
        self.app.settings().setGithubCopilotToken("")

        with MockGithubCopilot(self, MockGithubCopilotStep.LoginAccessDenied) as mock:
            spyError = QSignalSpy(self.window._aiMessage.errorOccurred)

            # mock QMessageBox.critical
            with patch("PySide6.QtWidgets.QMessageBox.critical") as mock_critical:
                QTest.mouseClick(self.window.ui.btnRefineMsg, Qt.LeftButton)
                self.wait(10000, lambda: spyError.count() == 0)
                mock_critical.assert_called_once()
            mock.assertEverythingOK()

        self.wait(50)
        self.window.cancel(True)

    def testCommit(self):
        self.waitForLoaded()

        # no files staged by default
        self.assertEqual(self.window._stagedModel.rowCount(), 0)
        self.assertFalse(self.window.ui.btnCommit.isEnabled())
        self.assertFalse(self.window.ui.cbAmend.isChecked())

        QTest.mouseClick(self.window.ui.cbAmend, Qt.LeftButton)
        self.processEvents()
        self.assertTrue(self.window.ui.btnCommit.isEnabled())
        self.assertTrue(self.window.ui.cbAmend.isChecked())

        QTest.mouseClick(self.window.ui.cbAmend, Qt.LeftButton)
        self.assertFalse(self.window.ui.cbAmend.isChecked())

        with open(os.path.join(self.gitDir.name, "test.txt"), "w+") as f:
            f.write("test")

        subRepoFile = os.path.join("subRepo", "test.py")
        with open(os.path.join(self.gitDir.name, subRepoFile), "a+") as f:
            f.write("# new line\n")

        branch = self.window._branchLabel.text()
        self.assertTrue(len(branch) > 0)

        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        self.assertEqual(branch, self.window._branchLabel.text())

        spyFinished = QSignalSpy(self.window._submoduleExecutor.finished)
        QTest.mouseClick(self.window.ui.tbStageAll, Qt.LeftButton)
        self.wait(10000, lambda: spyFinished.count() == 0)

        self.assertEqual(self.window._stagedModel.rowCount(), 2)
        self.assertTrue(self.window.ui.btnCommit.isEnabled())

        self.window.ui.teMessage.clear()
        # no message by default
        with patch("PySide6.QtWidgets.QMessageBox.critical") as mock_critical:
            QTest.mouseClick(self.window.ui.btnCommit, Qt.LeftButton)
            self.processEvents()
            mock_critical.assert_called_once()

        self.window.ui.teMessage.insertPlainText("# comment line\ntest commit")

        with patch("PySide6.QtWidgets.QMessageBox.critical") as mock_critical:
            spyFinished = QSignalSpy(self.window._commitExecutor.finished)
            spyReload = QSignalSpy(self.window._statusFetcher.finished)
            QTest.mouseClick(self.window.ui.btnCommit, Qt.LeftButton)
            self.wait(10000, lambda: spyFinished.count() == 0)
            self.wait(10000, lambda: spyReload.count() == 0)
            mock_critical.assert_not_called()
            self.assertEqual(
                self.window.ui.stackedWidget.currentWidget(), self.window.ui.pageProgress)
            self.assertEqual(self.window._stagedModel.rowCount(), 0)

            result = self.window.ui.teOutput.toPlainText()
            self.assertIn("create mode 100644 test.txt", result)
            self.assertIn("test commit", result)
            self.assertIn("1 file changed, 1 insertion", result)

            self.assertEqual(branch, self.window._branchLabel.text())

    def testCancelRunningCommit(self):
        self.waitForLoaded()
        # Simulate commit executor running
        self.window._commitExecutor.isRunning = lambda: True
        with patch.object(self.window._commitExecutor, "cancel") as mock_cancel, \
                patch.object(self.window, "_updateCommitStatus") as mock_update_status, \
                patch.object(self.window.ui.lbStatus, "setText") as mock_set_text:
            self.window._onCommitActionClicked()
            mock_cancel.assert_called_once()
            mock_update_status.assert_called_once_with(False)
            mock_set_text.assert_called_once_with(
                self.window.tr("Commit aborted"))

    def testCancelCommitNotRun(self):
        self.waitForLoaded()
        # Simulate commit executor not running
        self.window._commitExecutor.isRunning = lambda: False
        with patch.object(self.window.ui.stackedWidget, "setCurrentWidget") as mock_set_widget:
            self.window._onCommitActionClicked()
            mock_set_widget.assert_called_once_with(self.window.ui.pageMessage)

    def testCodeReview(self):
        self.waitForLoaded()

        with open(os.path.join(self.gitDir.name, "test.py"), "w+") as f:
            f.write("# dummy change\n")

        error = Git.addFiles(repoDir=self.gitDir.name, files=["test.py"])
        self.assertIsNone(error)

        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        QTest.mouseClick(self.window.ui.tbStageAll, Qt.LeftButton)
        self.waitForLoaded()

        self.assertTrue(self.window.ui.btnCodeReview.isEnabled())

        with patch.object(self.app, 'trackFeatureUsage') as mock_track, \
                patch.object(self.app, 'postEvent') as mock_post_event:

            # Click the code review button to trigger the actual flow
            QTest.mouseClick(self.window.ui.btnCodeReview, Qt.LeftButton)
            self.processEvents()

            # Verify feature usage was tracked
            mock_track.assert_called_once_with("commit.ai_cr")

            # Verify an event was posted
            self.assertEqual(mock_post_event.call_count, 1)
            posted_event: CodeReviewEvent = mock_post_event.call_args[0][1]

            # Verify it's a CodeReviewEvent
            self.assertIsInstance(posted_event, CodeReviewEvent)

            # Verify the event contains submodule files
            self.assertIsNotNone(posted_event.submodules)
            self.assertIsInstance(posted_event.submodules, dict)
            self.assertIn(".", posted_event.submodules)  # Root submodule
            # Our test file
            self.assertIn("test.py", posted_event.submodules["."])

        # Test AI window creation and model setup with mock models
        mock_model = mock.MagicMock(spec=AiModelBase)
        mock_model.name = "Test AI Model"
        mock_model.history = []
        mock_model.queryAsync = mock.MagicMock()
        mock_model.isLocal.return_value = False
        mock_model.modelId = "test-model"

        # Mock the model factory to return our mock model
        codeReviewForStagedFiles = AiChatWindow.codeReviewForStagedFiles
        with patch('qgitc.llmprovider.AiModelFactory.models') as mock_factory_models, \
                patch('qgitc.aichatwindow.AiChatWindow.codeReviewForStagedFiles') as mock_code_review:

            chatWindow = self.app.getWindow(WindowType.AiAssistant, False)
            self.assertIsNone(chatWindow)

            mock_factory_models.return_value = [lambda parent: mock_model]

            # Create CodeReviewEvent and simulate event processing
            test_event = CodeReviewEvent({".": ["test.py"]})

            # Process the event (this will create AI window and call codeReviewForStagedFiles)
            processed = self.app.event(test_event)
            self.assertTrue(processed)

            # Verify that codeReviewForStagedFiles was called
            mock_code_review.assert_called_once()
            called_args = mock_code_review.call_args[0][0]

            # Verify the staged files were passed correctly
            self.assertIsInstance(called_args, dict)
            self.assertIn(".", called_args)
            self.assertIn("test.py", called_args["."])

            chatWindow = self.app.getWindow(WindowType.AiAssistant, False)
            self.assertIsNotNone(chatWindow)

            codeReviewForStagedFiles(chatWindow, test_event.submodules)
            spyFinished = QSignalSpy(chatWindow._executor.finished)

            chatWidget: AiChatWidget = chatWindow.centralWidget()
            spyInitialized = QSignalSpy(chatWidget.initialized)
            self.assertFalse(chatWidget._isInitialized)

            self.wait(5000, lambda: spyInitialized.count() == 0 and spyFinished.count() == 0)
            self.processEvents()

            self.assertEqual(spyInitialized.count(), 1)
            self.assertEqual(spyFinished.count(), 1)
            self.assertTrue(chatWidget._isInitialized)

            model = chatWidget.currentChatModel()
            self.assertIsNotNone(model)
            self.assertEqual(model.modelId, "test-model")

            chatWindow.close()
