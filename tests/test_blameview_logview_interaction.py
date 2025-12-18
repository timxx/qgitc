# -*- coding: utf-8 -*-
import os
from unittest.mock import patch

from qgitc.blameline import BlameLine
from qgitc.gitutils import Git
from qgitc.logview import LogView
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestBlameViewLogViewInteraction(TestBase):
    """Test BlameCommitPanel and LogView interaction"""

    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(WindowType.BlameWindow)
        self.window.showMaximized()
        self.blameView = self.window._view
        self.commitPanel = self.blameView.commitPanel
        self.logView = self.commitPanel.logView

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def test_switchToCommit_with_delay_parameter(self):
        """Test switchToCommit respects delay parameter when fetcher is loading"""
        # Setup: Show logs for a file
        file = os.path.join(self.gitDir.name, "test.py")
        self.commitPanel.showLogs(self.gitDir.name, file)

        # Wait for fetch to complete
        self.wait(3000, lambda: self.logView.fetcher.isLoading())

        # Ensure data is available
        self.assertGreater(len(self.logView.data), 0)

        # Get the SHA1 of the first commit in the log
        firstCommit = self.logView.data[0]
        sha1 = firstCommit.sha1

        # Test 1: switchToCommit with delay=False
        # This should try to switch immediately
        self.assertFalse(self.logView.fetcher.isLoading())
        result = self.logView.switchToCommit(sha1, delay=False)
        self.assertTrue(
            result, "switchToCommit should return True when commit is found")

        # Test 2: switchToCommit with delay parameter set to True
        # When delay=True AND commit is NOT found, preferSha1 should be set
        # Reset first
        self.logView.setCurrentIndex(-1)
        self.logView.preferSha1 = None

        # Use a non-existent commit to trigger the delay path
        fake_sha1 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        result = self.logView.switchToCommit(fake_sha1, delay=True)
        self.assertTrue(
            result, "switchToCommit with delay=True should return True even if commit not found")
        # The key behavior: when delay=True and commit not found, it sets preferSha1
        self.assertEqual(self.logView.preferSha1, fake_sha1,
                         "preferSha1 should be set when delay=True and commit not found")

    def test_switchToCommit_when_fetcher_loading(self):
        """Test switchToCommit behavior when fetcher is actively loading"""
        file = os.path.join(self.gitDir.name, "test.py")

        # Get a valid SHA1
        sha1 = Git.checkOutput(
            ["log", "-1", "--pretty=format:%H", file]).rstrip().decode()

        # Mock fetcher to return isLoading=True
        with patch.object(self.logView.fetcher, 'isLoading', return_value=True):
            # When fetcher is loading and commit not yet in data, should set preferSha1
            result = self.logView.switchToCommit(sha1, delay=True)

            # Should set preferSha1 and return True when loading
            self.assertTrue(result)
            self.assertEqual(self.logView.preferSha1, sha1)

    def test_showRevision_with_loading_fetcher(self):
        """Test that showRevision correctly handles fetcher loading state"""
        file = os.path.join(self.gitDir.name, "test.py")

        # Get commit info before loading
        sha1 = Git.checkOutput(
            ["log", "-1", "--pretty=format:%H", file]).rstrip().decode()

        # Create a BlameLine for a commit not yet in data
        blameLine = BlameLine()
        blameLine.sha1 = sha1
        blameLine.previous = None

        # Mock fetcher.isLoading() to return True to test delay path
        with patch.object(self.logView.fetcher, 'isLoading', return_value=True):
            # Call showRevision while "fetcher is loading" and data is empty
            # This tests the fix: passing self.logView.fetcher.isLoading() to switchToCommit
            self.commitPanel.showRevision(blameLine)

            # Should have set preferSha1 because isLoading() returned True and commit not found
            self.assertEqual(self.logView.preferSha1, sha1)

    def test_no_endFetch_connection_in_BlameCommitPanel(self):
        """Test that BlameCommitPanel doesn't connect to logView.endFetch signal"""
        # This test verifies that the problematic endFetch connection is removed
        # We can't directly check signal connections, but we can verify behavior

        file = os.path.join(self.gitDir.name, "test.py")
        sha1_list = []

        # Get multiple commits
        output = Git.checkOutput(
            ["log", "--pretty=format:%H", "--all"],
            repoDir=self.gitDir.name
        ).decode()
        sha1_list = output.strip().split('\n')

        self.assertGreater(len(sha1_list), 0)

        # Setup logs
        self.commitPanel.showLogs(self.gitDir.name, file)
        self.wait(3000, lambda: self.logView.fetcher.isLoading())

        # Create blame line for first commit
        blameLine = BlameLine()
        blameLine.sha1 = sha1_list[0]
        blameLine.previous = None

        # Show the revision
        self.commitPanel.showRevision(blameLine)
        self.wait(300)

        # Trigger another log fetch
        self.logView.setCurrentIndex(-1)
        self.commitPanel.showLogs(self.gitDir.name, file, rev="HEAD~1")

        # Wait for the new fetch to complete
        self.wait(3000, lambda: self.logView.fetcher.isLoading())

        # The key test: After endFetch, the current index should NOT be automatically
        # changed by a now-removed _onLogFetchFinished handler
        # Since _selectOnFetch is False, it should remain -1
        finalIndex = self.logView.currentIndex()

        # With the fix, the index should remain -1 or be controlled by our explicit calls,
        # not automatically set by the endFetch signal
        # If _selectOnFetch is False and we don't explicitly call setCurrentIndex,
        # it should not auto-select on fetch finish
        self.assertEqual(finalIndex, -1)

    def test_race_condition_blame_finishes_before_log(self):
        """
        Test the race condition fix: when blame fetch finishes before log fetch
        
        This was the original bug: if blame fetch completed first, the active line
        could be incorrect because _onLogFetchFinished would update the selection.
        
        With the fix:
        - setAllowSelectOnFetch(False) prevents automatic selection
        - switchToCommit uses delay when fetcher is loading
        - No endFetch handler interferes with the selection
        """
        file = os.path.join(self.gitDir.name, "test.py")

        # Get commit SHA1
        sha1 = Git.checkOutput(
            ["log", "-1", "--pretty=format:%H", file]).rstrip().decode()

        # Create a BlameLine
        blameLine = BlameLine()
        blameLine.sha1 = sha1
        blameLine.previous = None

        # Mock fetcher to simulate it's still loading (race condition scenario)
        with patch.object(self.logView.fetcher, 'isLoading', return_value=True):
            # Start showing logs
            self.commitPanel.showLogs(self.gitDir.name, file)

            # Show revision while "fetcher is loading" (simulating blame fetch completing first)
            self.commitPanel.showRevision(blameLine)

            # Verify that preferSha1 is set (delay path taken)
            self.assertEqual(self.logView.preferSha1, sha1)

        # Now complete the actual fetch
        self.wait(3000, lambda: self.logView.fetcher.isLoading())

        # After fetch completes, preferSha1 should have been used to select the commit
        currentIndex = self.logView.currentIndex()
        self.assertNotEqual(currentIndex, -1)
        currentCommit = self.logView.getCommit(currentIndex)
        self.assertEqual(currentCommit.sha1, sha1)

    def test_selectOnFetch_false_no_auto_selection_on_empty(self):
        """Test that with _selectOnFetch=False, no auto-selection occurs even with data"""
        # This tests the specific code path in __onFetchFinished
        # where _selectOnFetch is checked

        self.assertFalse(self.logView._selectOnFetch)
        self.assertEqual(self.logView.currentIndex(), -1)

        file = os.path.join(self.gitDir.name, "test.py")

        # Show logs without setting preferSha1
        self.logView.preferSha1 = None
        self.commitPanel.showLogs(self.gitDir.name, file)
        self.wait(3000, lambda: self.logView.fetcher.isLoading())

        self.assertEqual(self.logView.currentIndex(), -1)
        self.assertGreater(len(self.logView.data), 0)

    def test_switchToCommit_same_commit_already_selected(self):
        """Test switchToCommit when the same commit is already selected"""
        file = os.path.join(self.gitDir.name, "test.py")

        # Setup: fetch logs and select a commit
        self.commitPanel.showLogs(self.gitDir.name, file)
        self.wait(3000, lambda: self.logView.fetcher.isLoading())

        # Select first commit
        self.logView.setCurrentIndex(0)
        firstCommit = self.logView.getCommit(0)
        sha1 = firstCommit.sha1

        # Try to switch to the same commit
        result = self.logView.switchToCommit(sha1, delay=False)

        # Should return True and stay on same index
        self.assertTrue(result)
        self.assertEqual(self.logView.currentIndex(), 0)

    def test_switchToCommit_commit_not_found(self):
        """Test switchToCommit when commit is not in the log"""
        file = os.path.join(self.gitDir.name, "test.py")

        # Setup: fetch logs
        self.commitPanel.showLogs(self.gitDir.name, file)
        self.wait(3000, lambda: self.logView.fetcher.isLoading())

        # Try to switch to a non-existent commit
        fake_sha1 = "0000000000000000000000000000000000000000"
        result = self.logView.switchToCommit(fake_sha1, delay=False)

        # Should return False when commit not found and not loading
        self.assertFalse(result)

    def test_switchToCommit_commit_not_found_while_loading(self):
        """Test switchToCommit when commit not found but fetcher is loading"""
        # Try to switch to a commit while loading
        fake_sha1 = "1111111111111111111111111111111111111111"

        # Mock fetcher to simulate loading state
        with patch.object(self.logView.fetcher, 'isLoading', return_value=True):
            # Should set preferSha1 and return True even if commit not found yet
            result = self.logView.switchToCommit(fake_sha1, delay=True)
            self.assertTrue(result)
            self.assertEqual(self.logView.preferSha1, fake_sha1)

    def test_switchToCommit_with_fetcher_not_loading(self):
        """Test switchToCommit with delay=True when fetcher is NOT loading"""
        # Setup: fetch logs first
        file = os.path.join(self.gitDir.name, "test.py")
        self.commitPanel.showLogs(self.gitDir.name, file)
        self.wait(3000, lambda: self.logView.fetcher.isLoading())

        fake_sha1 = "2222222222222222222222222222222222222222"

        # Mock fetcher to ensure it's NOT loading
        with patch.object(self.logView.fetcher, 'isLoading', return_value=False):
            # With delay=True but commit not found and not loading
            # it should still set preferSha1 (because delay=True)
            result = self.logView.switchToCommit(fake_sha1, delay=True)
            self.assertTrue(result)
            self.assertEqual(self.logView.preferSha1, fake_sha1)

    def test_showRevision_with_fetcher_not_loading(self):
        """Test showRevision when fetcher is NOT loading"""
        file = os.path.join(self.gitDir.name, "test.py")

        # Setup: fetch logs first
        self.commitPanel.showLogs(self.gitDir.name, file)
        self.wait(3000, lambda: self.logView.fetcher.isLoading())

        # Get a commit
        sha1 = self.logView.data[0].sha1
        blameLine = BlameLine()
        blameLine.sha1 = sha1
        blameLine.previous = None

        # Mock fetcher.isLoading() to return False
        with patch.object(self.logView.fetcher, 'isLoading', return_value=False):
            self.commitPanel.showRevision(blameLine)

            # Should have switched immediately, not set preferSha1
            # (because delay parameter would be False when not loading)
            self.assertIsNone(self.logView.preferSha1)
            # And current index should be set
            self.assertEqual(self.logView.currentIndex(), 0)
