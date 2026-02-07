# -*- coding: utf-8 -*-

import json
import os
from unittest.mock import Mock, patch

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QMessageBox

from qgitc.common import Commit
from qgitc.gitutils import Git
from qgitc.logview import LogView, MarkType
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestLogViewDragDrop(TestBase):
    """Test LogView drag and drop functionality"""

    def setUp(self):
        super().setUp()

        # Mock all QMessageBox methods to prevent blocking
        self.msgbox_patcher = patch.multiple(
            QMessageBox,
            critical=Mock(return_value=QMessageBox.Ok),
            warning=Mock(return_value=QMessageBox.Ok),
            question=Mock(return_value=QMessageBox.Yes),
            information=Mock(return_value=QMessageBox.Ok)
        )
        self.msgbox_patcher.start()

        self.window = self.app.getWindow(WindowType.LogWindow)
        self.logview = self.window.ui.gitViewA.ui.logView
        self.waitForLoaded()

    def tearDown(self):
        self.msgbox_patcher.stop()
        self.window.close()
        self.processEvents()
        super().tearDown()

    def waitForLoaded(self):
        """Wait for log window to be fully loaded"""
        spySubmodule = QSignalSpy(self.app.submoduleSearchCompleted)

        self.window.show()
        QTest.qWaitForWindowExposed(self.window)

        delayTimer = self.window._delayTimer
        self.wait(10000, delayTimer.isActive)
        self.wait(10000, lambda: spySubmodule.count() == 0)

        self.wait(10000, self.logview.fetcher.isLoading)
        self.wait(50)

    def _createMockCommit(self, sha1, comments="Test commit", repoDir=None, subCommits=None):
        """Create a mock commit for testing"""
        commit = Commit(
            sha1=sha1,
            comments=comments,
            author="Test Author <test@example.com>",
            authorDate="2025-01-01 12:00:00 +0000",
            committer="Test Committer <commit@example.com>",
            committerDate="2025-01-01 12:00:00 +0000",
            parents=[]
        )
        commit.repoDir = repoDir
        commit.subCommits = subCommits or []
        return commit

    def _createMouseEvent(self, eventType, pos, button=Qt.LeftButton, buttons=Qt.LeftButton):
        """Create a QMouseEvent for testing"""
        return QMouseEvent(
            eventType,
            QPointF(pos[0], pos[1]),
            QPointF(pos[0], pos[1]),
            button,
            buttons,
            Qt.NoModifier
        )

    def _createDragEvent(self, mimeData, pos=(100, 50), source=None):
        """Create a QDragEnterEvent or QDropEvent for testing"""
        return QDragEnterEvent(
            QPoint(pos[0], pos[1]),
            Qt.CopyAction,
            mimeData,
            Qt.LeftButton,
            Qt.NoModifier
        )

    def _createDropEvent(self, mimeData, pos=(100, 50)):
        """Create a QDropEvent for testing"""
        return QDropEvent(
            QPoint(pos[0], pos[1]),
            Qt.CopyAction,
            mimeData,
            Qt.LeftButton,
            Qt.NoModifier,
            QDropEvent.Drop
        )

    # ============================================================================
    # Test Drag Initiation
    # ============================================================================

    def test_mousePressEvent_stores_drag_start_position(self):
        """Test that mousePressEvent stores the drag start position"""
        self.assertGreater(len(self.logview.data), 0,
                           "LogView should have data")

        # Simulate mouse press
        pos = self.logview.itemRect(0).center()
        event = self._createMouseEvent(
            QMouseEvent.MouseButtonPress, (pos.x(), pos.y()))

        self.logview.mousePressEvent(event)

        self.assertIsNotNone(self.logview._dragStartPos)
        self.assertEqual(self.logview._dragStartPos, pos)

    def test_mousePressEvent_resets_on_non_left_button(self):
        """Test that non-left button press resets drag state"""
        # First set a drag start position
        pos = self.logview.itemRect(0).center()
        event = self._createMouseEvent(
            QMouseEvent.MouseButtonPress, (pos.x(), pos.y()))
        self.logview.mousePressEvent(event)
        self.assertIsNotNone(self.logview._dragStartPos)

        # Now press right button
        event = self._createMouseEvent(
            QMouseEvent.MouseButtonPress, (pos.x(), pos.y()),
            button=Qt.RightButton, buttons=Qt.RightButton
        )
        self.logview.mousePressEvent(event)

        self.assertIsNone(self.logview._dragStartPos)

    def test_mouseMoveEvent_starts_drag_after_threshold(self):
        """Test that mouseMoveEvent starts drag after moving threshold distance"""
        # Select an item
        self.logview.setCurrentIndex(0)
        self.logview.selectedIndices.add(0)

        center = self.logview.itemRect(0).center()
        # Store initial position
        event = self._createMouseEvent(
            QMouseEvent.MouseButtonPress, (center.x(), center.y()))
        self.logview.mousePressEvent(event)

        # Mock _startDrag to verify it's called
        with patch.object(self.logview, '_startDrag') as mock_start_drag:
            # Move mouse beyond threshold (>= 10 pixels)
            event = self._createMouseEvent(
                QMouseEvent.MouseMove, (center.x() + 20, center.y()),
                buttons=Qt.LeftButton
            )
            self.logview.mouseMoveEvent(event)

            mock_start_drag.assert_called_once()
            # Verify it's called with selected indices
            args = mock_start_drag.call_args[0]
            self.assertIn(0, args[0])

    def test_mouseMoveEvent_drags_unselected_item_only(self):
        """Test dragging an unselected item drags only that item"""
        # Select item 0, but drag from item 1 (unselected)
        self.logview.setCurrentIndex(0)
        self.logview.selectedIndices.add(0)

        # Calculate position for item 1
        lineHeight = self.logview.lineHeight
        pos_y = int(lineHeight * 1.5)

        event = self._createMouseEvent(
            QMouseEvent.MouseButtonPress, (100, pos_y))
        self.logview.mousePressEvent(event)

        with patch.object(self.logview, '_startDrag') as mock_start_drag:
            event = self._createMouseEvent(
                QMouseEvent.MouseMove, (120, pos_y),
                buttons=Qt.LeftButton
            )
            self.logview.mouseMoveEvent(event)

            mock_start_drag.assert_called_once()
            # Should drag only item 1
            args = mock_start_drag.call_args[0]
            self.assertEqual([1], args[0])

    def test_mouseMoveEvent_drags_all_selected_items(self):
        """Test dragging a selected item drags all selected items"""
        # Select items 0, 1
        self.logview.setCurrentIndex(0)
        self.logview.selectedIndices.update([0, 1])

        center = self.logview.itemRect(0).center()

        event = self._createMouseEvent(
            QMouseEvent.MouseButtonPress, (center.x(), center.y()))
        self.logview.mousePressEvent(event)

        with patch.object(self.logview, '_startDrag') as mock_start_drag:
            event = self._createMouseEvent(
                QMouseEvent.MouseMove, (center.x() + 20, center.y()),
                buttons=Qt.LeftButton
            )
            self.logview.mouseMoveEvent(event)

            mock_start_drag.assert_called_once()
            # Should drag all selected items
            args = mock_start_drag.call_args[0]
            self.assertEqual(sorted([0, 1]), sorted(args[0]))

    # ============================================================================
    # Test Drag Data Creation
    # ============================================================================

    def test_startDrag_creates_proper_mime_data(self):
        """Test that _startDrag creates proper MIME data"""
        # Mock QDrag to capture the MIME data
        with patch('qgitc.logview.QDrag') as mock_drag_class:
            mock_drag = Mock()
            mock_drag_class.return_value = mock_drag

            self.logview._startDrag([0])

            # Verify QDrag was created
            mock_drag_class.assert_called_once_with(self.logview)

            # Verify setMimeData was called
            self.assertTrue(mock_drag.setMimeData.called)

            # Get the MIME data
            mime_data = mock_drag.setMimeData.call_args[0][0]

            # Verify MIME data has the custom format
            self.assertTrue(mime_data.hasFormat("application/x-qgitc-commits"))

            # Verify text format (SHA1 list)
            text = mime_data.text()
            self.assertIsNotNone(text)

            # Verify JSON data
            json_bytes = mime_data.data("application/x-qgitc-commits")
            drag_data = json.loads(json_bytes.data().decode("utf-8"))

            self.assertIn("repoUrl", drag_data)
            self.assertIn("repoDir", drag_data)
            self.assertIn("branch", drag_data)
            self.assertIn("commits", drag_data)
            self.assertEqual(len(drag_data["commits"]), 1)

            # Verify commit data structure
            commit_data = drag_data["commits"][0]
            self.assertIn("sha1", commit_data)
            self.assertIn("repoDir", commit_data)

    def test_startDrag_includes_subcommits(self):
        """Test that _startDrag includes subcommits in MIME data"""
        # Create a mock commit with subcommits
        main_commit = self._createMockCommit("abc123", repoDir=".")
        sub_commit = self._createMockCommit("def456", repoDir="submodule")
        main_commit.subCommits = [sub_commit]

        # Temporarily replace data
        original_data = self.logview.data
        self.logview.data = [main_commit]

        try:
            with patch('qgitc.logview.QDrag') as mock_drag_class:
                mock_drag = Mock()
                mock_drag_class.return_value = mock_drag

                self.logview._startDrag([0])

                mime_data = mock_drag.setMimeData.call_args[0][0]
                json_bytes = mime_data.data("application/x-qgitc-commits")
                drag_data = json.loads(json_bytes.data().decode("utf-8"))

                # Verify subcommits are included
                self.assertIn("subCommits", drag_data["commits"][0])
                self.assertEqual(len(drag_data["commits"][0]["subCommits"]), 1)
                self.assertEqual(
                    drag_data["commits"][0]["subCommits"][0]["sha1"], "def456")
        finally:
            self.logview.data = original_data

    def test_startDrag_handles_empty_indices(self):
        """Test that _startDrag handles empty indices gracefully"""
        with patch('qgitc.logview.QDrag') as mock_drag_class:
            self.logview._startDrag([])

            # Should not create drag
            mock_drag_class.assert_not_called()

    # ============================================================================
    # Test Drop Acceptance
    # ============================================================================

    def test_dragEnterEvent_accepts_commits_from_different_logview(self):
        """Test that dragEnterEvent accepts commits from different LogView"""
        mime_data = QMimeData()
        drag_data = {
            "repoUrl": Git.repoUrl(),
            "repoDir": self.gitDir.name,
            "branch": "other-branch",
            "commits": [{"sha1": "abc123", "repoDir": "."}]
        }
        mime_data.setData("application/x-qgitc-commits",
                          json.dumps(drag_data).encode("utf-8"))

        event = self._createDragEvent(mime_data)

        # Mock source to be a different LogView
        other_logview = Mock(spec=LogView)
        with patch.object(event, 'source', return_value=other_logview):
            self.logview.dragEnterEvent(event)

            # Should accept
            self.assertTrue(event.isAccepted())

    def test_dragEnterEvent_accepts_commits_from_external_app(self):
        """Test that dragEnterEvent accepts commits from external app (source is None)"""
        mime_data = QMimeData()
        drag_data = {
            "repoUrl": Git.repoUrl(),
            "repoDir": self.gitDir.name,
            "branch": "other-branch",
            "commits": [{"sha1": "abc123", "repoDir": "."}]
        }
        mime_data.setData("application/x-qgitc-commits",
                          json.dumps(drag_data).encode("utf-8"))

        event = self._createDragEvent(mime_data)

        # Mock source to be None (external)
        with patch.object(event, 'source', return_value=None):
            self.logview.dragEnterEvent(event)

            # Should accept
            self.assertTrue(event.isAccepted())

    def test_dragEnterEvent_rejects_commits_from_same_logview(self):
        """Test that dragEnterEvent rejects commits from same LogView"""
        mime_data = QMimeData()
        drag_data = {
            "repoUrl": Git.repoUrl(),
            "repoDir": self.gitDir.name,
            "branch": "other-branch",
            "commits": [{"sha1": "abc123", "repoDir": "."}]
        }
        mime_data.setData("application/x-qgitc-commits",
                          json.dumps(drag_data).encode("utf-8"))

        event = self._createDragEvent(mime_data)

        # Mock source to be the same LogView
        with patch.object(event, 'source', return_value=self.logview):
            self.logview.dragEnterEvent(event)

            # Should not accept
            self.assertFalse(event.isAccepted())

    def test_dragEnterEvent_rejects_invalid_mime_type(self):
        """Test that dragEnterEvent rejects invalid MIME type"""
        mime_data = QMimeData()
        mime_data.setText("some text")

        event = self._createDragEvent(mime_data)

        with patch.object(event, 'source', return_value=None):
            self.logview.dragEnterEvent(event)

            # Should not accept
            self.assertFalse(event.isAccepted())

    # ============================================================================
    # Test Drop Position Calculation
    # ============================================================================

    def test_findDropPosition_returns_correct_position(self):
        """Test that _findDropPosition returns correct line index"""
        # Find position for HEAD or after LCC/LUC
        pos = self.logview._findDropPosition(QPointF(100, 50))

        # Should return a valid position
        self.assertGreaterEqual(pos, 0)
        self.assertLessEqual(pos, len(self.logview.data))

    def test_findDropPosition_after_local_changes(self):
        """Test that _findDropPosition works correctly with local changes"""
        # Create test file to generate local changes
        test_file = os.path.join(self.gitDir.name, "drop_test.txt")
        with open(test_file, "w") as f:
            f.write("test content for drop")

        Git.addFiles(repoDir=self.gitDir.name, files=["drop_test.txt"])

        # Reload to get local changes
        self.logview.reloadLogs()
        self.wait(5000, self.logview.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(self.logview.data[0].sha1, Git.LCC_SHA1)

        pos = self.logview._findDropPosition(QPointF(100, 50))
        # Should return position after LCC
        self.assertEqual(pos, 1)

    # ============================================================================
    # Test Drop Handling
    # ============================================================================

    def test_dropEvent_rejects_invalid_mime_data(self):
        """Test that dropEvent rejects invalid MIME data"""
        mime_data = QMimeData()
        mime_data.setText("invalid data")

        event = self._createDropEvent(mime_data)

        with patch.object(QMessageBox, 'critical'):
            self.logview.dropEvent(event)

            # Should not accept
            self.assertFalse(event.isAccepted())

    def test_dropEvent_rejects_different_repo(self):
        """Test that dropEvent rejects commits from different repository"""
        mime_data = QMimeData()
        drag_data = {
            "repoUrl": "https://different.repo/url.git",
            "repoDir": "/different/repo",
            "branch": "other-branch",
            "commits": [{"sha1": "abc123", "repoDir": "."}]
        }
        mime_data.setData("application/x-qgitc-commits",
                          json.dumps(drag_data).encode("utf-8"))

        event = self._createDropEvent(mime_data)

        with patch.object(QMessageBox, 'warning') as mock_warning:
            with patch.object(event, 'source', return_value=None):
                self.logview.dropEvent(event)

                # Should show warning
                mock_warning.assert_called_once()
                # Should not accept
                self.assertFalse(event.isAccepted())

    def test_dropEvent_rejects_same_branch(self):
        """Test that dropEvent rejects commits to same branch"""
        mime_data = QMimeData()
        drag_data = {
            "repoUrl": Git.repoUrl(),
            "repoDir": self.gitDir.name,
            "branch": self.logview.curBranch,  # Same branch
            "commits": [{"sha1": "abc123", "repoDir": "."}]
        }
        mime_data.setData("application/x-qgitc-commits",
                          json.dumps(drag_data).encode("utf-8"))

        event = self._createDropEvent(mime_data)

        with patch.object(QMessageBox, 'warning') as mock_warning:
            with patch.object(event, 'source', return_value=None):
                self.logview.dropEvent(event)

                # Should show warning
                mock_warning.assert_called_once()
                # Should not accept
                self.assertFalse(event.isAccepted())

    def test_dropEvent_rejects_unchecked_branch(self):
        """Test that dropEvent rejects when branch is not checked out"""
        # Set branchDir to non-existent path
        original_branch_dir = self.logview._branchDir
        self.logview._branchDir = "/non/existent/path"

        try:
            mime_data = QMimeData()
            drag_data = {
                "repoUrl": Git.repoUrl(),
                "repoDir": self.gitDir.name,
                "branch": "other-branch",
                "commits": [{"sha1": "abc123", "repoDir": "."}]
            }
            mime_data.setData("application/x-qgitc-commits",
                              json.dumps(drag_data).encode("utf-8"))

            event = self._createDropEvent(mime_data)

            with patch.object(QMessageBox, 'warning') as mock_warning:
                with patch.object(event, 'source', return_value=None):
                    self.logview.dropEvent(event)

                    # Should show warning
                    mock_warning.assert_called_once()
                    # Should not accept
                    self.assertFalse(event.isAccepted())
        finally:
            self.logview._branchDir = original_branch_dir

    # ============================================================================
    # Test Cherry-Pick Operations (Progress Dialog Flow)
    # ============================================================================

    def test_executeCherryPick_builds_items_oldest_first(self):
        """Test that _executeCherryPick passes items in oldest->newest order."""
        commits = [
            {"sha1": "newest", "repoDir": "."},
            {"sha1": "middle", "repoDir": "."},
            {"sha1": "oldest", "repoDir": "."},
        ]

        with patch('qgitc.logview.CherryPickProgressDialog') as MockDlg:
            dlg = Mock()
            MockDlg.return_value = dlg
            dlg.startSession.return_value = 0

            with patch.object(self.logview, 'reloadLogs'):
                self.logview._executeCherryPick(
                    commits, None, self.gitDir.name, None)

            dlg.startSession.assert_called_once()
            kwargs = dlg.startSession.call_args.kwargs
            items = kwargs.get('items', [])
            self.assertEqual([i.sha1 for i in items], [
                             "oldest", "middle", "newest"])
            self.assertTrue(kwargs.get('allowPatchPick'))

    def test_executeCherryPick_includes_subcommits(self):
        """Test that _executeCherryPick includes subCommits in items list."""
        commits = [
            {
                "sha1": "main1",
                "repoDir": ".",
                "subCommits": [
                    {"sha1": "sub1", "repoDir": "submodule"},
                    {"sha1": "sub2", "repoDir": "submodule"},
                ],
            }
        ]

        with patch('qgitc.logview.CherryPickProgressDialog') as MockDlg:
            dlg = Mock()
            MockDlg.return_value = dlg
            dlg.startSession.return_value = 0

            with patch.object(self.logview, 'reloadLogs'):
                self.logview._executeCherryPick(
                    commits, None, self.gitDir.name, None)

            kwargs = dlg.startSession.call_args.kwargs
            items = kwargs.get('items', [])
            self.assertEqual([i.sha1 for i in items], [
                             "main1", "sub1", "sub2"])

    def test_executeCherryPick_sets_callbacks_for_source_view(self):
        """Test that sourceView enables mark/apply-local-changes callbacks."""
        commits = [{"sha1": "abc123", "repoDir": "."}]

        with patch('qgitc.logview.CherryPickProgressDialog') as MockDlg:
            dlg = Mock()
            MockDlg.return_value = dlg
            dlg.startSession.return_value = 0

            with patch.object(self.logview, 'reloadLogs'):
                self.logview._executeCherryPick(
                    commits, self.logview, self.gitDir.name, None)

            dlg.setMarkCallback.assert_called_once()
            dlg.setApplyLocalChangesCallback.assert_called_once()
            kwargs = dlg.startSession.call_args.kwargs
            self.assertFalse(kwargs.get('allowPatchPick'))

    # ============================================================================
    # Test Mark Status
    # ============================================================================

    def test_markPickStatus_marks_picked_commit(self):
        """Test that _markPickStatus marks commit as picked"""
        sha1 = self.logview.data[0].sha1

        LogView._markPickStatus(self.logview, sha1, MarkType.PICKED)

        marker = self.logview.marker
        self.assertEqual(len(marker._ranges), 1)
        self.assertEqual(marker._ranges[0].markType, MarkType.PICKED)
        self.assertEqual(marker._ranges[0].begin, 0)
        self.assertEqual(marker._ranges[0].end, 0)

    def test_markPickStatus_marks_failed_commit(self):
        """Test that _markPickStatus marks commit as failed"""
        sha1 = self.logview.data[0].sha1

        LogView._markPickStatus(self.logview, sha1, MarkType.FAILED)

        marker = self.logview.marker
        self.assertEqual(len(marker._ranges), 1)
        self.assertEqual(marker._ranges[0].markType, MarkType.FAILED)
        self.assertEqual(marker._ranges[0].begin, 0)
        self.assertEqual(marker._ranges[0].end, 0)

    def test_markPickStatus_handles_none_source(self):
        """Test that _markPickStatus handles None source gracefully"""
        # Should not raise exception
        LogView._markPickStatus(None, "abc123", MarkType.PICKED)
        marker = self.logview.marker
        self.assertEqual(len(marker._ranges), 0)

    # ============================================================================
    # ============================================================================
    # Test Local Changes Application
    # ============================================================================

    @patch('qgitc.gitutils.Git.commitRawDiff')
    @patch('qgitc.gitutils.Git.run')
    def test_applyLocalChanges_success(self, mock_run, mock_diff):
        """Test successful application of local changes"""
        mock_diff.return_value = b"diff content"

        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("", "")
        mock_run.return_value = mock_process

        result = self.logview._applyLocalChanges(
            self.gitDir.name, Git.LUC_SHA1, self.gitDir.name, None
        )

        self.assertTrue(result)
        mock_diff.assert_called_once()
        mock_run.assert_called_once()

    @patch('qgitc.gitutils.Git.commitRawDiff')
    def test_applyLocalChanges_no_changes(self, mock_diff):
        """Test application of local changes with no changes"""
        mock_diff.return_value = b""

        with patch.object(QMessageBox, 'warning') as mock_warning:
            result = self.logview._applyLocalChanges(
                self.gitDir.name, Git.LUC_SHA1, self.gitDir.name, None
            )

            self.assertFalse(result)
            mock_warning.assert_called_once()

    @patch('qgitc.gitutils.Git.commitRawDiff')
    @patch('qgitc.gitutils.Git.run')
    def test_applyLocalChanges_apply_failed(self, mock_run, mock_diff):
        """Test failed application of local changes"""
        mock_diff.return_value = b"diff content"

        mock_process = Mock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = ("", "apply failed")
        mock_run.return_value = mock_process

        with patch.object(QMessageBox, 'critical'):
            result = self.logview._applyLocalChanges(
                self.gitDir.name, Git.LUC_SHA1, self.gitDir.name, None
            )

            self.assertFalse(result)

    @patch('qgitc.gitutils.Git.commitRawDiff')
    @patch('qgitc.gitutils.Git.run')
    def test_applyLocalChanges_applies_cached_correctly(self, mock_run, mock_diff):
        """Test that cached changes use --cached flag"""
        mock_diff.return_value = b"diff content"

        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("", "")
        mock_run.return_value = mock_process

        self.logview._applyLocalChanges(
            self.gitDir.name, Git.LCC_SHA1, self.gitDir.name, None
        )

        args = mock_run.call_args[0][0]
        self.assertIn("--index", args)

    # ============================================================================
    # Test Edge Cases
    # ============================================================================

    def test_dragEnterEvent_initializes_drop_indicator(self):
        """Test that dragEnterEvent initializes drop indicator state"""
        mime_data = QMimeData()
        drag_data = {
            "repoUrl": Git.repoUrl(),
            "repoDir": self.gitDir.name,
            "branch": "other-branch",
            "commits": [{"sha1": "abc123", "repoDir": "."}]
        }
        mime_data.setData("application/x-qgitc-commits",
                          json.dumps(drag_data).encode("utf-8"))

        event = self._createDragEvent(mime_data)

        with patch.object(event, 'source', return_value=None):
            self.logview.dragEnterEvent(event)

            # Verify drop indicator was initialized
            self.assertEqual(self.logview._dropIndicatorAlpha, 0.0)
            self.assertEqual(self.logview._dropIndicatorOffset, 0.0)

    def test_dragLeaveEvent_clears_drop_indicator(self):
        """Test that dragLeaveEvent clears drop indicator"""
        # Set some drop indicator state
        self.logview._dropIndicatorLine = 5
        self.logview._dropIndicatorAlpha = 0.5
        self.logview._dropIndicatorOffset = 0.3

        event = Mock()
        self.logview.dragLeaveEvent(event)

        # Verify drop indicator was cleared
        self.assertEqual(self.logview._dropIndicatorLine, -1)
        self.assertEqual(self.logview._dropIndicatorAlpha, 0.0)
        self.assertEqual(self.logview._dropIndicatorOffset, 0.0)

    def test_dropEvent_clears_drop_indicator(self):
        """Test that dropEvent clears drop indicator after drop"""
        mime_data = QMimeData()
        mime_data.setText("invalid")

        event = self._createDropEvent(mime_data)

        # Set some drop indicator state
        self.logview._dropIndicatorLine = 5
        self.logview._dropIndicatorAlpha = 0.5

        self.logview.dropEvent(event)

        # Verify drop indicator was cleared
        self.assertEqual(self.logview._dropIndicatorLine, -1)
        self.assertEqual(self.logview._dropIndicatorAlpha, 0.0)

    def test_createDragPreview_handles_empty_commits(self):
        """Test that _createDragPreview handles empty commit list"""
        pixmap = self.logview._createDragPreview([])
        self.assertIsNone(pixmap)

    def test_createDragPreview_handles_single_commit(self):
        """Test that _createDragPreview handles single commit"""
        commit = self._createMockCommit("abc123", "Test commit")
        pixmap = self.logview._createDragPreview([commit])

        self.assertIsNotNone(pixmap)
        self.assertGreater(pixmap.width(), 0)
        self.assertGreater(pixmap.height(), 0)

    def test_createDragPreview_handles_many_commits(self):
        """Test that _createDragPreview handles many commits"""
        commits = [
            self._createMockCommit(f"commit{i}", f"Commit {i}")
            for i in range(10)
        ]

        pixmap = self.logview._createDragPreview(commits)

        self.assertIsNotNone(pixmap)
        # Should show preview with "... and X more" indicator
