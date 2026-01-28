# -*- coding: utf-8 -*-
import os
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QMessageBox

from qgitc.gitutils import Git
from qgitc.pickbranchwindow import CommitsAvailableEvent, PickBranchWindow
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestPickBranchWindow(TestBase):
    """Test cases for PickBranchWindow - cherry-pick commits from one branch to another"""

    def setUp(self):
        super().setUp()
        self.window: PickBranchWindow = self.app.getWindow(
            WindowType.PickBranchWindow)
        self.window.show()
        self.processEvents()

    def tearDown(self):
        self.window.close()
        self.processEvents()
        super().tearDown()

    def _createTestBranches(self):
        """Create test branches for testing"""
        # Create and commit to dev branch
        Git.checkOutput(["checkout", "-b", "dev"], repoDir=self.gitDir.name)
        with open(os.path.join(self.gitDir.name, "dev.txt"), "w") as f:
            f.write("dev file")
        Git.addFiles(repoDir=self.gitDir.name, files=["dev.txt"])
        Git.commit("Add dev.txt", repoDir=self.gitDir.name)

        # Create another commit on dev
        with open(os.path.join(self.gitDir.name, "dev2.txt"), "w") as f:
            f.write("dev file 2")
        Git.addFiles(repoDir=self.gitDir.name, files=["dev2.txt"])
        Git.commit("Add dev2.txt", repoDir=self.gitDir.name)

        # Switch back to main
        Git.checkOutput(["checkout", "main"], repoDir=self.gitDir.name)

    def _waitForBranchesLoaded(self):
        """Wait for branches to load"""
        self.wait(100)
        self.processEvents()

    def _waitForCommitsLoaded(self):
        """Wait for commits to be loaded"""
        self.wait(5000, lambda: self.window.ui.logView.fetcher.isLoading())
        self.processEvents()

    def testDefaultState(self):
        """Test initial window state"""
        self.assertIsNotNone(self.window.ui)

        # Wait for initial branch load triggered by showEvent
        self._waitForBranchesLoaded()

        # After loading, should have branches from the test repo
        self.assertGreater(self.window.ui.cbSourceBranch.count(), 0)
        self.assertGreater(self.window.ui.cbTargetBranch.count(), 0)
        self.assertGreater(self.window.ui.cbBaseBranch.count(), 0)

        # Buttons should be disabled initially (no commits loaded)
        self.assertFalse(self.window.ui.btnCherryPick.isEnabled())

        # Enabling it should show the embedded AI chat dock
        self.window.ui.cbAutoResolveAi.setChecked(True)
        self.processEvents()
        self.assertIsNotNone(self.window._aiChat)
        self.assertTrue(self.window._aiChat.isVisible())

    def testReloadBranches(self):
        """Test loading branches from git"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Should have loaded branches
        self.assertGreater(self.window.ui.cbSourceBranch.count(), 0)
        self.assertGreater(self.window.ui.cbTargetBranch.count(), 0)
        self.assertGreater(self.window.ui.cbBaseBranch.count(), 0)

        # Should find 'main' branch
        mainIndex = self.window.ui.cbSourceBranch.findText("main")
        self.assertNotEqual(mainIndex, -1)

        # Should find 'dev' branch
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        self.assertNotEqual(devIndex, -1)

    def testSetSourceBranch(self):
        """Test setting source branch programmatically"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Set source branch to 'dev'
        self.window.setSourceBranch("dev")
        self._waitForCommitsLoaded()

        self.assertEqual(self.window.ui.cbSourceBranch.currentText(), "dev")

    def testSetSourceBranchBeforeLoad(self):
        """Test setting source branch before branches are loaded"""
        # Create a new window that hasn't been shown yet
        newWindow = PickBranchWindow()

        # Set branch before showing (before auto-load)
        newWindow.setSourceBranch("dev")

        # Should store as pending since branches aren't loaded
        self.assertEqual(newWindow._pendingSourceBranch, "dev")

        # Now create branches and show window to trigger loading
        self._createTestBranches()
        newWindow.show()
        self.processEvents()
        self.wait(200)  # Wait for auto-load from showEvent

        # Should apply pending branch
        self.assertEqual(newWindow.ui.cbSourceBranch.currentText(), "dev")
        self.assertIsNone(newWindow._pendingSourceBranch)

        newWindow.close()
        self.processEvents()

    def testSetSourceBranchNonExistent(self):
        """Test setting a non-existent source branch"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Try to set non-existent branch
        self.window.setSourceBranch("nonexistent")
        self._waitForCommitsLoaded()

        # Should not change current selection
        self.assertEqual(self.window.ui.cbSourceBranch.currentIndex(), -1)

    def testLoadCommitsWithValidBranches(self):
        """Test loading commits when source and base branches are set"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Set source to 'dev' and base to 'main'
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")

        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)

        self.window._loadCommits()
        self._waitForCommitsLoaded()

        # Should have loaded commits (2 commits on dev not in main)
        commitCount = self.window.ui.logView.getCount()
        self.assertEqual(commitCount, 2)

    def testLoadCommitsWithSameBranch(self):
        """Test loading commits when source and base are the same"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Set both to 'main'
        mainIndex = self.window.ui.cbSourceBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(mainIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)

        self.window._loadCommits()
        self._waitForCommitsLoaded()

        # Should show error status
        self.assertIn("must be different", self.window.ui.labelStatus.text())
        self.assertEqual(self.window.ui.logView.getCount(), 0)

    def testLoadCommitsWithEmptyBranches(self):
        """Test loading commits when branches are not selected"""
        self.window._loadCommits()
        self._waitForCommitsLoaded()

        # Should show error status
        self.assertIn("select both", self.window.ui.labelStatus.text())

    def testSelectAllCommits(self):
        """Test selecting all commits"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()

        # Select all
        self.window._selectAllCommits()
        self.processEvents()

        # All commits should be marked
        self.assertTrue(self.window.ui.logView.marker.hasMark())
        markedCount = self.window.ui.logView.marker.countMarked()
        commitCount = self.window.ui.logView.getCount()
        self.assertEqual(markedCount, commitCount)

    def testSelectNoneCommits(self):
        """Test deselecting all commits"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits and select all
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()
        self.window._selectAllCommits()

        # Deselect all
        self.window._selectNoneCommits()
        self.processEvents()

        # No commits should be marked
        self.assertFalse(self.window.ui.logView.marker.hasMark())

    def testButtonStatesWithNoCommits(self):
        """Test button states when no commits are available"""
        self.window._updateButtonStates()

        self.assertFalse(self.window.ui.btnSelectAll.isEnabled())
        self.assertFalse(self.window.ui.btnSelectNone.isEnabled())
        self.assertFalse(self.window.ui.btnFilterCommits.isEnabled())
        self.assertFalse(self.window.ui.btnCherryPick.isEnabled())

    def testButtonStatesWithCommitsNotMarked(self):
        """Test button states when commits are available but not marked"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits without marking
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()

        # Clear any default marks
        self.window._selectNoneCommits()
        self.window._updateButtonStates()

        # Select All should be enabled, others disabled
        self.assertTrue(self.window.ui.btnSelectAll.isEnabled())
        self.assertFalse(self.window.ui.btnSelectNone.isEnabled())
        self.assertFalse(self.window.ui.btnFilterCommits.isEnabled())
        self.assertFalse(self.window.ui.btnCherryPick.isEnabled())

    def testButtonStatesWithMarkedCommits(self):
        """Test button states when commits are marked"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits and mark them
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()
        self.window._selectAllCommits()
        self.window._updateButtonStates()

        # All buttons should be enabled
        # All already selected
        self.assertFalse(self.window.ui.btnSelectAll.isEnabled())
        self.assertTrue(self.window.ui.btnSelectNone.isEnabled())
        self.assertTrue(self.window.ui.btnFilterCommits.isEnabled())
        self.assertTrue(self.window.ui.btnCherryPick.isEnabled())

    def testCommitsAvailableEvent(self):
        """Test handling of CommitsAvailableEvent"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()

        # Clear marks to test event
        self.window._selectNoneCommits()

        # Send event
        event = CommitsAvailableEvent()
        result = self.window.event(event)

        self.assertTrue(result)
        # Should mark all by default
        self.assertTrue(self.window.ui.logView.marker.hasMark())

    def testFilterCommitsNoPatterns(self):
        """Test filtering commits when no filter patterns are configured"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits and mark them
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()
        self.window._selectAllCommits()

        # Filter without patterns
        self.window._filterCommits()
        self.processEvents()

        # Should show message about no filters
        self.assertIn("No commits matched the filter criteria", self.window.ui.labelStatus.text())

    def testFilterCommitsWithPattern(self):
        """Test filtering commits with text patterns"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits and mark them
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()
        self.window._selectAllCommits()

        # Set filter pattern
        settings = self.app.settings()
        settings.setFilterCommitPatterns(["dev2.txt"])
        settings.setFilterUseRegex(False)

        # Filter commits
        self.window._filterCommits()
        self.processEvents()

        # One commit should be filtered out
        markedCount = self.window.ui.logView.marker.countMarked()
        self.assertEqual(markedCount, 1)  # Only "Add dev.txt" should remain

    def testFilterCommitsWithRevertPattern(self):
        """Test filtering reverted commits"""
        self._createTestBranches()

        # Create a revert commit
        Git.checkOutput(["checkout", "dev"], repoDir=self.gitDir.name)
        lastCommitSha = Git.checkOutput(
            ["rev-parse", "HEAD"], repoDir=self.gitDir.name).strip()

        # Create a revert commit
        Git.checkOutput(["revert", "--no-edit", lastCommitSha],
                        repoDir=self.gitDir.name)
        Git.checkOutput(["checkout", "main"], repoDir=self.gitDir.name)

        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits and mark them
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()
        self.window._selectAllCommits()

        # Enable revert filter
        settings = self.app.settings()
        settings.setFilterRevertedCommits(True)

        # Filter commits
        self.window._filterCommits()
        self.processEvents()

        # Revert commit should be filtered out
        markedCount = self.window.ui.logView.marker.countMarked()
        self.assertLess(markedCount, self.window.ui.logView.getCount())

    def testOnCommitSelected(self):
        """Test commit selection shows diff"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()

        # Select first commit
        self.window._onCommitSelected(0)
        self.processEvents()

        # DiffView should show something (we can't easily verify content)
        # Just verify the method doesn't crash

    def testOnCommitSelectedInvalidIndex(self):
        """Test commit selection with invalid index"""
        # Should not crash
        self.window._onCommitSelected(-1)
        self.window._onCommitSelected(999)

    def testCherryPickWithSameBranch(self):
        """Test cherry-pick fails when target equals source"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits and mark them - use different base
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(
            mainIndex)  # Use main as base to get commits
        self.window._loadCommits()
        self._waitForCommitsLoaded()
        self.window._selectAllCommits()

        # Set target to same as source
        self.window.ui.cbTargetBranch.setCurrentIndex(devIndex)

        # Try to cherry-pick
        with patch.object(QMessageBox, 'warning') as mockWarning:
            self.window._onCherryPickClicked()
            mockWarning.assert_called_once()
            args = mockWarning.call_args[0]
            self.assertIn("same as source", args[2])

    def testCherryPickWithNoMarkedCommits(self):
        """Test cherry-pick does nothing with no marked commits"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits but don't mark any
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()
        self.window._selectNoneCommits()

        # Try to cherry-pick - should do nothing
        self.window._onCherryPickClicked()
        # No exception means success

    def testCherryPickWithUncheckedTarget(self):
        """Test cherry-pick fails when target branch is not checked out"""
        self._createTestBranches()
        self.window._reloadBranches()
        self._waitForBranchesLoaded()

        # Load commits and mark them
        devIndex = self.window.ui.cbSourceBranch.findText("dev")
        mainIndex = self.window.ui.cbBaseBranch.findText("main")
        self.window.ui.cbSourceBranch.setCurrentIndex(devIndex)
        self.window.ui.cbBaseBranch.setCurrentIndex(mainIndex)
        self.window._loadCommits()
        self._waitForCommitsLoaded()
        self.window._selectAllCommits()

        # Set target to main (different from source=dev)
        # Then mock branchDir to return None (not checked out)
        self.window.ui.cbTargetBranch.setCurrentIndex(mainIndex)

        # Mock branchDir to return None (not checked out)
        with patch.object(Git, 'branchDir', return_value=None):
            with patch.object(QMessageBox, 'warning') as mockWarning:
                self.window._onCherryPickClicked()
                mockWarning.assert_called_once()
                args = mockWarning.call_args[0]
                self.assertIn("not checked out", args[2])

    def testRecordOriginCheckbox(self):
        """Test record origin checkbox updates settings"""
        initialValue = self.app.settings().recordOrigin()

        # Toggle checkbox
        self.window.ui.cbRecordOrigin.setChecked(not initialValue)
        self.processEvents()

        # Setting should be updated
        self.assertEqual(self.app.settings().recordOrigin(), not initialValue)

    def testOpenSettings(self):
        """Test opening settings dialog"""
        with patch('qgitc.pickbranchwindow.Preferences') as MockPreferences:
            mockDialog = Mock()
            mockDialog.exec.return_value = 0  # Rejected
            mockDialog.ui.tabWidget = Mock()
            mockDialog.ui.tabCherryPick = Mock()
            MockPreferences.return_value = mockDialog

            self.window._openSettings()

            MockPreferences.assert_called_once()
            mockDialog.exec.assert_called_once()

    def testShowLogWindow(self):
        """Test showing log window"""
        with patch.object(self.app, 'postEvent') as mockPost:
            self.window._showLogWindow()
            mockPost.assert_called_once()

    def testUpdateStatus(self):
        """Test updating status message"""
        testMessage = "Test status message"
        self.window._updateStatus(testMessage)
        self.assertEqual(self.window.ui.labelStatus.text(), testMessage)

    def testDelayLoadCommits(self):
        """Test delayed commit loading"""
        self.assertFalse(self.window._loadCommitsDelayTimer.isActive())
        self.window._delayLoadCommits()
        self.assertTrue(self.window._loadCommitsDelayTimer.isActive())

    def testSpinnerStartStop(self):
        """Test spinner shows during commit loading"""
        self.assertFalse(self.window.ui.spinnerCommits.isSpinning())

        self.window._onCommitsFetchStarted()
        # Spinner delay timer should start
        self.assertTrue(self.window._commitSpinnerDelayTimer.isActive())

        self.window._onCommitsFetchFinished()
        # Timer should be stopped
        self.assertFalse(self.window._commitSpinnerDelayTimer.isActive())

    def testBranchComboboxSetup(self):
        """Test branch combobox configuration"""
        # Check all comboboxes are editable with completion
        self.assertTrue(self.window.ui.cbSourceBranch.isEditable())
        self.assertTrue(self.window.ui.cbTargetBranch.isEditable())
        self.assertTrue(self.window.ui.cbBaseBranch.isEditable())

        self.assertIsNotNone(self.window.ui.cbSourceBranch.completer())
        self.assertIsNotNone(self.window.ui.cbTargetBranch.completer())
        self.assertIsNotNone(self.window.ui.cbBaseBranch.completer())
