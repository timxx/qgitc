# -*- coding: utf-8 -*-
import os
from unittest import mock
from unittest.mock import patch

from PySide6.QtCore import QItemSelectionModel, Qt, QThread
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QDialog, QMessageBox

from qgitc.aichatwindow import AiChatWidget
from qgitc.cancelevent import CancelEvent
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

        # Patch exec at class level before dialog is instantiated
        with patch.object(QDialog, 'exec', return_value=QDialog.Rejected) as mock_exec:
            QTest.mouseClick(self.window.ui.tbOptions, Qt.LeftButton)
            self.processEvents()
            mock_exec.assert_called_once()

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

        with patch('qgitc.llmprovider.AiModelFactory.models') as mock_factory_models:
            mock_factory_models.return_value = [lambda parent: mock_model]

            chatWindow = self.app.getWindow(WindowType.AiAssistant, False)
            self.assertIsNotNone(chatWindow)

            chatWindow.codeReviewForStagedFiles(test_event.submodules)
            spyFinished = QSignalSpy(chatWindow._executor.finished)

            chatWidget: AiChatWidget = chatWindow.centralWidget()
            spyInitialized = QSignalSpy(chatWidget.initialized)
            self.assertFalse(chatWidget._isInitialized)

            self.wait(5000, lambda: spyInitialized.count()
                      == 0 or spyFinished.count() == 0)
            self.processEvents()

            self.assertEqual(spyInitialized.count(), 1)
            self.assertEqual(spyFinished.count(), 1)
            self.assertTrue(chatWidget._isInitialized)

            model = chatWidget.currentChatModel()
            self.assertIsNotNone(model)
            self.assertEqual(model.modelId, "test-model")

            chatWindow.close()

    def testDeleteSingleFile(self):
        self.waitForLoaded()

        # Create a test file
        testFile = os.path.join(self.gitDir.name, "delete_test.txt")
        with open(testFile, "w+") as f:
            f.write("test content")

        # Refresh to show the file
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        lvFiles = self.window.ui.lvFiles
        filesModel = lvFiles.model()
        self.assertGreater(filesModel.rowCount(), 0)

        # Find and select the test file
        for row in range(filesModel.rowCount()):
            index = filesModel.index(row, 0)
            fileName = filesModel.data(index)
            if fileName == "delete_test.txt":
                lvFiles.setCurrentIndex(index)
                break

        # Mock the context menu action trigger
        with patch.object(self.window._submoduleExecutor, 'submit') as mock_submit:
            self.window._acDeleteFiles.setData(lvFiles)
            self.window._onDeleteFiles()
            self.processEvents()

            # Verify submit was called with the delete function
            mock_submit.assert_called_once()
            args = mock_submit.call_args[0]
            self.assertIn(".", args[0])  # Root submodule
            self.assertIn("delete_test.txt", args[0]["."])
            self.assertEqual(args[1], self.window._doDeleteFiles)

    def testDeleteMultipleFiles(self):
        self.waitForLoaded()

        # Create multiple test files
        testFiles = ["delete1.txt", "delete2.txt", "delete3.txt"]
        for fileName in testFiles:
            filePath = os.path.join(self.gitDir.name, fileName)
            with open(filePath, "w+") as f:
                f.write("test content")

        # Refresh to show the files
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        lvFiles = self.window.ui.lvFiles
        filesModel = lvFiles.model()
        self.assertGreater(filesModel.rowCount(), 0)

        # Select all test files
        lvFiles.clearSelection()
        selectionModel = lvFiles.selectionModel()
        for row in range(filesModel.rowCount()):
            index = filesModel.index(row, 0)
            fileName = filesModel.data(index)
            if fileName in testFiles:
                selectionModel.select(index, QItemSelectionModel.Select)

        selectedIndexes = lvFiles.selectedIndexes()
        self.assertEqual(len(selectedIndexes), 3)

        # Mock QMessageBox.question to simulate user confirmation
        with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.Yes) as mock_question, \
                patch.object(self.window._submoduleExecutor, 'submit') as mock_submit:

            self.window._acDeleteFiles.setData(lvFiles)
            self.window._onDeleteFiles()
            self.processEvents()

            # Verify confirmation dialog was shown
            mock_question.assert_called_once()
            call_args = mock_question.call_args[0]
            # Check that the message mentions multiple files
            self.assertIn("3", call_args[2])  # Message should contain "3"

            # Verify submit was called
            mock_submit.assert_called_once()

    def testDeleteMultipleFilesCancel(self):
        self.waitForLoaded()

        # Create multiple test files
        testFiles = ["delete_cancel1.txt", "delete_cancel2.txt"]
        for fileName in testFiles:
            filePath = os.path.join(self.gitDir.name, fileName)
            with open(filePath, "w+") as f:
                f.write("test content")

        # Refresh to show the files
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        lvFiles = self.window.ui.lvFiles
        filesModel = lvFiles.model()

        # Select all test files
        lvFiles.clearSelection()
        selectionModel = lvFiles.selectionModel()
        for row in range(filesModel.rowCount()):
            index = filesModel.index(row, 0)
            fileName = filesModel.data(index)
            if fileName in testFiles:
                selectionModel.select(index, QItemSelectionModel.Select)

        # Mock QMessageBox.question to simulate user canceling
        with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.No) as mock_question, \
                patch.object(self.window._submoduleExecutor, 'submit') as mock_submit:

            self.window._acDeleteFiles.setData(lvFiles)
            self.window._onDeleteFiles()
            self.processEvents()

            # Verify confirmation dialog was shown
            mock_question.assert_called_once()

            # Verify submit was NOT called (user canceled)
            mock_submit.assert_not_called()

    def testDoDeleteFiles(self):
        """Test the actual file deletion worker function"""
        self.waitForLoaded()

        # Create test files
        testFiles = ["worker_delete1.txt", "worker_delete2.txt"]
        fullPaths = []
        for fileName in testFiles:
            filePath = os.path.join(self.gitDir.name, fileName)
            with open(filePath, "w+") as f:
                f.write("test content")
            fullPaths.append(filePath)
            self.assertTrue(os.path.exists(filePath))

        # Mock cancel event with a mock thread
        mockThread = mock.MagicMock(spec=QThread)
        mockThread.isInterruptionRequested.return_value = False
        cancelEvent = CancelEvent(mockThread)

        # Call the delete worker function
        self.window._doDeleteFiles(".", testFiles, cancelEvent)
        self.processEvents()

        # Verify files were deleted
        for filePath in fullPaths:
            self.assertFalse(os.path.exists(filePath))

    def testDeleteFileError(self):
        """Test error handling in file deletion"""
        self.waitForLoaded()

        # Try to delete a non-existent file
        mockThread = mock.MagicMock(spec=QThread)
        mockThread.isInterruptionRequested.return_value = False
        cancelEvent = CancelEvent(mockThread)

        # Mock a file that doesn't exist (should not cause error since we check existence)
        nonExistentFile = "this_file_does_not_exist.txt"

        with patch.object(self.window, '_statusFetcher'):
            # Call delete on non-existent file (should handle gracefully)
            self.window._doDeleteFiles(".", [nonExistentFile], cancelEvent)
            self.processEvents()

        # Test with an actual error (mock os.remove to raise exception)
        testFile = "error_test.txt"
        filePath = os.path.join(self.gitDir.name, testFile)
        with open(filePath, "w+") as f:
            f.write("test")

        with patch('os.remove', side_effect=PermissionError("Permission denied")), \
                patch.object(self.window._statusFetcher, 'fetchStatus'), \
                patch("PySide6.QtWidgets.QMessageBox.critical") as mock_critical:

            self.window._doDeleteFiles(".", [testFile], cancelEvent)
            self.processEvents()

            # Give time for event to be processed
            self.wait(100)

            # Verify error message box was shown
            mock_critical.assert_called_once()

            # File should still exist due to error
            self.assertTrue(os.path.exists(filePath))

    def testDeleteContextMenu(self):
        """Test delete action in context menu"""
        self.waitForLoaded()

        # Create a test file
        testFile = os.path.join(self.gitDir.name, "context_menu_test.txt")
        with open(testFile, "w+") as f:
            f.write("test content")

        # Refresh to show the file
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        lvFiles = self.window.ui.lvFiles
        filesModel = lvFiles.model()

        # Find and select the test file
        for row in range(filesModel.rowCount()):
            index = filesModel.index(row, 0)
            fileName = filesModel.data(index)
            if fileName == "context_menu_test.txt":
                lvFiles.setCurrentIndex(index)
                break

        # Verify delete action exists and has correct text
        self.assertIsNotNone(self.window._acDeleteFiles)
        self.assertIn("Delete", self.window._acDeleteFiles.text())

    def testCheckoutSingleFile(self):
        """Test checkout action for a single file"""
        self.waitForLoaded()

        # Create and modify a tracked file
        testFile = os.path.join(self.gitDir.name, "test.py")
        with open(testFile, "a+") as f:
            f.write("\n# Modified content\n")

        # Refresh to show the modified file
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        lvFiles = self.window.ui.lvFiles
        filesModel = lvFiles.model()
        self.assertGreater(filesModel.rowCount(), 0)

        # Find and select the test file
        found = False
        for row in range(filesModel.rowCount()):
            index = filesModel.index(row, 0)
            fileName = filesModel.data(index)
            if fileName == "test.py":
                lvFiles.setCurrentIndex(index)
                found = True
                break

        self.assertTrue(found, "test.py should be in the modified files list")

        # Mock QMessageBox.question to verify it's NOT called for single file
        with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.Yes) as mock_question, \
                patch.object(self.window._submoduleExecutor, 'submit') as mock_submit:

            self.window._acCheckoutFiles.setData(lvFiles)
            self.window._onCheckoutFiles()
            self.processEvents()

            # Verify confirmation dialog was NOT shown for single file
            mock_question.assert_not_called()

            # Verify submit was called with the checkout function
            mock_submit.assert_called_once()
            args = mock_submit.call_args[0]
            self.assertIn(".", args[0])  # Root submodule
            self.assertIn("test.py", args[0]["."])
            self.assertEqual(args[1], self.window._doCheckoutFiles)

        self.waitForLoaded()

    def testCheckoutMultipleFiles(self):
        """Test checkout action for multiple files"""
        self.waitForLoaded()

        # Create and modify multiple tracked files
        testFiles = ["test.py", "README.md"]
        for fileName in testFiles:
            filePath = os.path.join(self.gitDir.name, fileName)
            with open(filePath, "a+") as f:
                f.write("\n# Modified content\n")

        # Refresh to show the modified files
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        lvFiles = self.window.ui.lvFiles
        filesModel = lvFiles.model()
        self.assertGreater(filesModel.rowCount(), 0)

        # Select all test files
        lvFiles.clearSelection()
        selectionModel = lvFiles.selectionModel()
        selectedCount = 0
        for row in range(filesModel.rowCount()):
            index = filesModel.index(row, 0)
            fileName = filesModel.data(index)
            if fileName in testFiles:
                selectionModel.select(index, QItemSelectionModel.Select)
                selectedCount += 1

        self.assertEqual(selectedCount, len(testFiles),
                         "All test files should be selected")

        # Mock QMessageBox.question to simulate user confirmation
        with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.Yes) as mock_question, \
                patch.object(self.window._submoduleExecutor, 'submit') as mock_submit:

            self.window._acCheckoutFiles.setData(lvFiles)
            self.window._onCheckoutFiles()
            self.processEvents()

            # Verify confirmation dialog was shown
            mock_question.assert_called_once()
            call_args = mock_question.call_args[0]
            # Check that the message mentions multiple files and count
            self.assertIn("2", call_args[2])  # Message should contain "2"
            self.assertIn("selected files", call_args[2])

            # Verify submit was called
            mock_submit.assert_called_once()
            args = mock_submit.call_args[0]
            self.assertIn(".", args[0])
            # Both files should be in the submission
            self.assertGreaterEqual(len(args[0]["."]), 2)

        self.waitForLoaded()

    def testCheckoutMultipleFilesCancel(self):
        """Test canceling checkout for multiple files"""
        self.waitForLoaded()

        # Create and modify multiple tracked files
        testFiles = ["test.py", "README.md"]
        for fileName in testFiles:
            filePath = os.path.join(self.gitDir.name, fileName)
            with open(filePath, "a+") as f:
                f.write("\n# Modified for cancel test\n")

        # Refresh to show the modified files
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        lvFiles = self.window.ui.lvFiles
        filesModel = lvFiles.model()

        # Select test files
        lvFiles.clearSelection()
        selectionModel = lvFiles.selectionModel()
        for row in range(filesModel.rowCount()):
            index = filesModel.index(row, 0)
            fileName = filesModel.data(index)
            if fileName in testFiles:
                selectionModel.select(index, QItemSelectionModel.Select)

        # Mock QMessageBox.question to simulate user canceling
        with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.No) as mock_question, \
                patch.object(self.window._submoduleExecutor, 'submit') as mock_submit:

            self.window._acCheckoutFiles.setData(lvFiles)
            self.window._onCheckoutFiles()
            self.processEvents()

            # Verify confirmation dialog was shown
            mock_question.assert_called_once()

            # Verify submit was NOT called (user canceled)
            mock_submit.assert_not_called()

        self.waitForLoaded()

    def testDoCheckoutFiles(self):
        """Test the actual checkout worker function"""
        self.waitForLoaded()

        # Modify a tracked file
        testFile = "test.py"
        testFilePath = os.path.join(self.gitDir.name, testFile)

        # Read original content
        with open(testFilePath, "r") as f:
            originalContent = f.read()

        # Modify the file
        with open(testFilePath, "a+") as f:
            f.write("\n# This modification should be reverted\n")

        # Verify the file was modified
        with open(testFilePath, "r") as f:
            modifiedContent = f.read()
        self.assertNotEqual(originalContent, modifiedContent)

        # Mock cancel event with a mock thread
        mockThread = mock.MagicMock(spec=QThread)
        mockThread.isInterruptionRequested.return_value = False
        cancelEvent = CancelEvent(mockThread)

        # Call the checkout worker function
        with patch.object(self.window._statusFetcher, 'fetchStatus'):
            self.window._doCheckoutFiles(".", [testFile], cancelEvent)
            self.processEvents()

        # Verify file content was reverted
        with open(testFilePath, "r") as f:
            currentContent = f.read()
        self.assertEqual(originalContent, currentContent)

        self.waitForLoaded()

    def testCheckoutContextMenuVisibility(self):
        """Test that checkout action is visible only for lvFiles, not lvStaged"""
        self.waitForLoaded()

        # Create a test file and stage it
        testFile = os.path.join(self.gitDir.name, "stage_test.txt")
        with open(testFile, "w+") as f:
            f.write("test content")

        # Refresh and stage
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        lvFiles = self.window.ui.lvFiles
        filesModel = lvFiles.model()
        self.assertEqual(filesModel.rowCount(), 1)

        # Select a file in lvFiles
        lvFiles.setCurrentIndex(filesModel.index(0, 0))

        # Mock the menu exec to prevent it from blocking
        with patch.object(self.window._contextMenu, 'exec'):
            # Test context menu for lvFiles (should show checkout)
            self.window._showStatusContextMenu(lvFiles.pos(), lvFiles)
            self.assertTrue(self.window._acCheckoutFiles.isVisible(),
                            "Checkout action should be visible for unstaged files")

        spyFinished = QSignalSpy(self.window._submoduleExecutor.finished)
        QTest.mouseClick(self.window.ui.tbStageAll, Qt.LeftButton)
        self.wait(10000, lambda: spyFinished.count() == 0)

        lvStaged = self.window.ui.lvStaged
        stagedModel = lvStaged.model()
        self.assertEqual(stagedModel.rowCount(), 1)

        # Select a file in lvStaged
        lvStaged.setCurrentIndex(stagedModel.index(0, 0))

        # Mock the menu exec to prevent it from blocking
        with patch.object(self.window._contextMenu, 'exec'):
            # Test context menu for lvStaged (should NOT show checkout)
            self.window._showStatusContextMenu(lvStaged.pos(), lvStaged)
            self.assertFalse(self.window._acCheckoutFiles.isVisible(),
                             "Checkout action should NOT be visible for staged files")

    def testCheckoutActionExists(self):
        """Test that checkout action is properly initialized"""
        self.waitForLoaded()

        # Verify checkout action exists and has correct text
        self.assertIsNotNone(self.window._acCheckoutFiles)
        self.assertIn("Checkout", self.window._acCheckoutFiles.text())

    def testCheckoutFeatureTracking(self):
        """Test that checkout feature usage is tracked"""
        self.waitForLoaded()

        # Create and modify a tracked file
        testFile = os.path.join(self.gitDir.name, "test.py")
        with open(testFile, "a+") as f:
            f.write("\n# Modified content\n")

        # Refresh to show the modified file
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        lvFiles = self.window.ui.lvFiles
        filesModel = lvFiles.model()

        # Find and select the test file
        for row in range(filesModel.rowCount()):
            index = filesModel.index(row, 0)
            fileName = filesModel.data(index)
            if fileName == "test.py":
                lvFiles.setCurrentIndex(index)
                break

        # Mock tracking and test
        with patch.object(self.app, 'trackFeatureUsage') as mock_track, \
                patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.Yes), \
                patch.object(self.window._submoduleExecutor, 'submit'):

            self.window._acCheckoutFiles.setData(lvFiles)
            self.window._onCheckoutFiles()
            self.processEvents()

            # Verify feature usage was tracked
            mock_track.assert_called_once_with("commit.checkout_files")
