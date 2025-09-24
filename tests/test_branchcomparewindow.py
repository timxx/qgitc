from PySide6.QtCore import QModelIndex

from qgitc.branchcomparewindow import FileStatusEvent
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestBranchCompareWindow(TestBase):

    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(WindowType.BranchCompareWindow)
        self.window.show()

    def tearDown(self):
        self.window.close()
        self.processEvents()
        super().tearDown()

    def testDefaultState(self):
        self.assertTrue(self.window._isBranchDiff)
        self.assertTrue(self.window.ui.cbMergeBase.isChecked())
        self.assertEqual(self.window.ui.cbBaseBranch.currentText(), "")

    def test_compareBranches_sets_branches(self):
        # Add some branches to the comboboxes
        self.window.ui.cbBaseBranch.addItem("main")
        self.window.ui.cbBaseBranch.addItem("dev")
        self.window.ui.cbTargetBranch.addItem("main")
        self.window.ui.cbTargetBranch.addItem("dev")

        self.window.compareBranches(targetBranch="dev", baseBranch="main")
        self.assertEqual(self.window.ui.cbTargetBranch.currentText(), "dev")
        self.assertEqual(self.window.ui.cbBaseBranch.currentText(), "main")

    def test_setBranch_sets_existing_branch(self):
        combo = self.window.ui.cbBaseBranch
        combo.addItem("main")
        self.window._setBranch(combo, "main")
        self.assertEqual(combo.currentText(), "main")

    def test_setBranch_sets_non_existing_branch(self):
        combo = self.window.ui.cbBaseBranch
        self.window._setBranch(combo, "nonexistent")
        self.assertEqual(combo.currentText(), "nonexistent")

    def test_handleFileStatusEvent_adds_file_and_mergebase(self):
        event = FileStatusEvent("file.txt", "repo", "M", "old.txt", "mergebase123")
        self.window._handleFileStatusEvent(event)
        self.assertIn("repo", self.window._repoMergeBase)
        self.assertEqual(self.window._repoMergeBase["repo"], "mergebase123")

    def test_restoreState_and_saveState(self):
        # Save state should return True if super().saveState() returns True
        self.assertTrue(self.window.saveState())
        self.assertTrue(self.window.restoreState())

    def test_onSelectFileChanged_invalid_index(self):
        # Should not raise if index is invalid
        self.window._onSelectFileChanged(QModelIndex(), QModelIndex())

    def test_onFilesContextMenuRequested_does_nothing(self):
        # Should not raise
        self.window._onFilesContextMenuRequested(None)

    def test_event_handles_FileStatusEvent(self):
        event = FileStatusEvent("file.txt", "repo", "M")
        result = self.window.event(event)
        self.assertTrue(result)
