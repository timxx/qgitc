# -*- coding: utf-8 -*-

import os
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest

from qgitc.amendcommitmodel import AmendCommitInfo
from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.commitwindow import AmendCommitDetectedEvent, CommitWindow
from qgitc.gitutils import Git
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestCommitWindowAmend(TestBase):
    """Test amend commit detection background processing"""

    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(WindowType.CommitWindow)
        self.window.show()
        self.processEvents()
        self.waitForLoaded()

    def tearDown(self):
        if self.window:
            self.window.close()
            self.window = None
        super().tearDown()

    def createSubRepo(self):
        return True

    def createSubmodule(self):
        return True

    def waitForLoaded(self):
        self.wait(10000, self.window._statusFetcher.isRunning)
        self.wait(10000, self.window._infoFetcher.isRunning)
        self.wait(10000, self.window._submoduleExecutor.isRunning)
        self.wait(50)

    def test_amendDetectExecutorInitialized(self):
        """Test that the amend detect executor is properly initialized"""
        self.assertIsNotNone(self.window._amendDetectExecutor)
        self.assertIsInstance(self.window._amendDetectionResults, list)
        self.assertEqual(len(self.window._amendDetectionResults), 0)

    def test_detectAmendCommits_noStagedFiles(self):
        """Test amend detection with no staged files (detects from HEAD)"""
        self.assertEqual(self.window._stagedModel.rowCount(), 0)

        # Execute detection
        spyFinished = QSignalSpy(self.window._amendDetectExecutor.finished)
        self.window._detectAmendCommits()

        # Results should be cleared initially
        self.assertEqual(len(self.window._amendDetectionResults), 0)
        self.wait(1000, lambda: spyFinished.count() == 0)
        self.processEvents()

        self.assertGreaterEqual(len(self.window._amendDetectionResults), 1)

    def test_detectAmendCommits_withStagedFiles(self):
        """Test amend detection with staged files"""
        stagedFile = "staged.txt"
        with open(os.path.join(self.gitDir.name, stagedFile), "w") as f:
            f.write("staged")

        Git.addFiles(repoDir=self.gitDir.name, files=[stagedFile])

        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()
        self.assertGreater(self.window._stagedModel.rowCount(), 0)

        spyFinished = QSignalSpy(self.window._amendDetectExecutor.finished)
        self.window._detectAmendCommits()
        self.wait(1000, lambda: spyFinished.count() == 0)
        self.processEvents()

        self.assertGreaterEqual(len(self.window._amendDetectionResults), 1)
        self.assertTrue(
            any(commit.repoDir is None for commit in self.window._amendDetectionResults))

    def test_doDetectAmendCommits_withValidCommit(self):
        """Test the worker method that detects a single commit"""
        submodule = "."
        # Create a mock thread for CancelEvent
        mockThread = Mock()
        mockThread.isInterruptionRequested.return_value = False
        cancelEvent = CancelEvent(mockThread)

        # Mock Git.commitSummary to return commit data
        mockSummary = {
            "sha1": "abc123",
            "subject": "Test commit",
            "body": "Test body",
            "author": "Test Author",
            "date": "2024-01-01 12:00:00"
        }

        with patch.object(Git, "commitSummary", return_value=mockSummary):
            with patch.object(ApplicationBase.instance(), "postEvent") as mockPost:
                # Execute the worker method
                self.window._doDetectAmendCommits(submodule, None, cancelEvent)

                # Verify event was posted
                mockPost.assert_called_once()
                args = mockPost.call_args[0]
                self.assertEqual(args[0], self.window)
                self.assertIsInstance(args[1], AmendCommitDetectedEvent)
                self.assertEqual(args[1].commitInfo.sha1, "abc123")
                self.assertEqual(args[1].commitInfo.subject, "Test commit")

    def test_doDetectAmendCommits_cancelled(self):
        """Test that worker respects cancel event"""
        submodule = "."
        # Create a mock thread for CancelEvent
        mockThread = Mock()
        mockThread.isInterruptionRequested.return_value = True
        cancelEvent = CancelEvent(mockThread)

        with patch.object(Git, "commitSummary") as mockSummary:
            with patch.object(ApplicationBase.instance(), "postEvent") as mockPost:
                # Execute the worker method
                self.window._doDetectAmendCommits(submodule, None, cancelEvent)

                # Verify Git was not called and no event posted
                mockSummary.assert_not_called()
                mockPost.assert_not_called()

    def test_doDetectAmendCommits_noCommit(self):
        """Test worker when no commit is found"""
        submodule = "."
        # Create a mock thread for CancelEvent
        mockThread = Mock()
        mockThread.isInterruptionRequested.return_value = False
        cancelEvent = CancelEvent(mockThread)

        with patch.object(Git, "commitSummary", return_value=None):
            with patch.object(ApplicationBase.instance(), "postEvent") as mockPost:
                # Execute the worker method
                self.window._doDetectAmendCommits(submodule, None, cancelEvent)

                # Verify no event was posted
                mockPost.assert_not_called()

    def test_handleAmendCommitDetectedEvent(self):
        """Test event handler accumulates results on UI thread"""
        commitInfo1 = AmendCommitInfo(
            repoDir=None,
            sha1="abc123",
            subject="Main commit",
            body="Body1",
            author="Author1",
            date="2024-01-01",
            willAmend=True
        )
        commitInfo2 = AmendCommitInfo(
            repoDir="submodule1",
            sha1="def456",
            subject="Sub commit",
            body="Body2",
            author="Author2",
            date="2024-01-02",
            willAmend=True
        )

        # Clear results
        self.window._amendDetectionResults.clear()

        # Handle events
        self.window._handleAmendCommitDetectedEvent(commitInfo1)
        self.window._handleAmendCommitDetectedEvent(commitInfo2)

        # Verify accumulation
        self.assertEqual(len(self.window._amendDetectionResults), 2)
        self.assertEqual(self.window._amendDetectionResults[0].sha1, "abc123")
        self.assertEqual(self.window._amendDetectionResults[1].sha1, "def456")

    def test_onAmendDetectFinished_withMainCommit(self):
        """Test finished handler with main repo commit"""
        # Prepare detection results
        mainCommit = AmendCommitInfo(
            repoDir=None,
            sha1="abc123",
            subject="Main commit",
            body="Main body",
            author="Author",
            date="2024-01-01",
            willAmend=True
        )
        subCommit = AmendCommitInfo(
            repoDir="submodule1",
            sha1="def456",
            subject="Sub commit",
            body="Sub body",
            author="Author",
            date="2024-01-02",
            willAmend=True
        )

        self.window._amendDetectionResults = [mainCommit, subCommit]
        self.window._stagedModel = Mock()
        self.window._stagedModel.rowCount.return_value = 1  # Has staged files

        with patch.object(ApplicationBase.instance(), "postEvent") as mockPost:
            # Execute finished handler
            self.window._onAmendDetectFinished()

            # Verify template event was posted with main commit body
            mockPost.assert_called_once()
            args = mockPost.call_args[0]
            self.assertEqual(args[0], self.window)

            # Verify model was updated with both commits
            commits = self.window._amendCommitsModel.getAllCommits()
            self.assertEqual(len(commits), 2)

    def test_onAmendDetectFinished_noStagedFiles_filtersByMessage(self):
        """Test finished handler filters by message when no staged files"""
        # Create commits with different subjects
        mainCommit = AmendCommitInfo(
            repoDir=None,
            sha1="abc123",
            subject="Matching commit",
            body="Main body",
            author="Author",
            date="2024-01-01",
            willAmend=True
        )
        subCommit1 = AmendCommitInfo(
            repoDir="submodule1",
            sha1="def456",
            subject="Matching commit",  # Same subject
            body="Sub body 1",
            author="Author",
            date="2024-01-02",
            willAmend=True
        )
        subCommit2 = AmendCommitInfo(
            repoDir="submodule2",
            sha1="ghi789",
            subject="Different commit",  # Different subject
            body="Sub body 2",
            author="Author",
            date="2024-01-03",
            willAmend=True
        )

        self.window._amendDetectionResults = [mainCommit, subCommit1, subCommit2]
        self.window._stagedModel = Mock()
        self.window._stagedModel.rowCount.return_value = 0  # No staged files

        with patch.object(ApplicationBase.instance(), "postEvent"):
            # Execute finished handler
            self.window._onAmendDetectFinished()

            # Verify only commits with matching subject are in model
            commits = self.window._amendCommitsModel.getAllCommits()
            self.assertEqual(len(commits), 2)
            self.assertEqual(commits[0].subject, "Matching commit")
            self.assertEqual(commits[1].subject, "Matching commit")

            self.assertTrue(self.window._amendCommitsModel._allowUncheck)

    def test_onAmendDetectFinished_noCommits(self):
        """Test finished handler with no detected commits"""
        self.window._amendDetectionResults = []
        self.window._stagedModel = Mock()
        self.window._stagedModel.rowCount.return_value = 0

        with patch.object(ApplicationBase.instance(), "postEvent") as mockPost:
            # Execute finished handler
            self.window._onAmendDetectFinished()

            # Verify no template event was posted
            mockPost.assert_not_called()

            # Verify model was cleared
            commits = self.window._amendCommitsModel.getAllCommits()
            self.assertEqual(len(commits), 0)

    def test_amendCommitDetectedEvent_eventPosting(self):
        """Test that AmendCommitDetectedEvent can be posted and received"""
        commitInfo = AmendCommitInfo(
            repoDir=None,
            sha1="abc123",
            subject="Test commit",
            body="Test body",
            author="Test Author",
            date="2024-01-01",
            willAmend=True
        )

        # Clear results
        self.window._amendDetectionResults.clear()

        # Post event
        event = AmendCommitDetectedEvent(commitInfo)
        ApplicationBase.instance().postEvent(self.window, event)

        # Process events
        self.processEvents()

        # Verify event was handled (results should be accumulated)
        self.assertEqual(len(self.window._amendDetectionResults), 1)
        self.assertEqual(self.window._amendDetectionResults[0].sha1, "abc123")

    def test_normalizeRepoDirDisplay(self):
        """Test repo dir display normalization"""
        # "." should normalize to None
        self.assertIsNone(self.window._normalizeRepoDirDisplay("."))

        # Empty/None should normalize to None
        self.assertIsNone(self.window._normalizeRepoDirDisplay(""))
        self.assertIsNone(self.window._normalizeRepoDirDisplay(None))

        # Submodule paths should remain unchanged
        self.assertEqual(self.window._normalizeRepoDirDisplay("submodule1"), "submodule1")
        self.assertEqual(self.window._normalizeRepoDirDisplay("path/to/submodule"), "path/to/submodule")
