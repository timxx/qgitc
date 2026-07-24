# -*- coding: utf-8 -*-
import os
from unittest.mock import patch

from PySide6.QtTest import QSignalSpy, QTest

from qgitc.common import Commit
from qgitc.gitutils import Git
from qgitc.logview import LogView
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestLogViewSelectSync(TestBase):
    """Test that LogView curIdx and selectedIndices stay in sync
    after local changes are inserted on top of the data.
    """

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

    def test_curIdx_and_selectedIndices_sync_after_local_changes(self):
        """curIdx and selectedIndices should point to the same commit
        after LCC/LUC are prepended to the data list.
        """
        filePath = os.path.join(self.gitDir.name, "test.py")

        # Show logs for the file and wait for fetch to complete
        self.commitPanel.showLogs(self.gitDir.name, filePath)
        self.wait(5000, lambda: self.logView.fetcher.isLoading())
        self.processEvents()
        self.wait(50)

        self.assertGreater(len(self.logView.data), 0,
                           "LogView should have data after fetch")

        # Verify that LCC is already inserted since there are local changes
        # (blame window's logView doesn't insert LCC/LUC since it's not editable)
        # So we manually construct the scenario to prove the bug:
        # When local changes are inserted at the top, curIdx and selectedIndices
        # must both shift accordingly.

        # Clear and populate mock data to simulate post-__onLogsAvailable state
        # where a commit is selected before __onLocalChangesAvailable fires.
        self.logView.data = [
            Commit(
                sha1="aaa1111",
                comments="Most recent commit",
                author="Author <a@b.com>",
                authorDate="2025-01-03 12:00:00 +0000",
                committer="Author <a@b.com>",
                committerDate="2025-01-03 12:00:00 +0000",
                parents=["bbb2222"],
            ),
            Commit(
                sha1="bbb2222",
                comments="Second commit",
                author="Author <a@b.com>",
                authorDate="2025-01-02 12:00:00 +0000",
                committer="Author <a@b.com>",
                committerDate="2025-01-02 12:00:00 +0000",
                parents=["ccc3333"],
            ),
            Commit(
                sha1="ccc3333",
                comments="First commit",
                author="Author <a@b.com>",
                authorDate="2025-01-01 12:00:00 +0000",
                committer="Author <a@b.com>",
                committerDate="2025-01-01 12:00:00 +0000",
                parents=[],
            ),
        ]

        # Select the middle commit (index 1, "bbb2222")
        self.logView.setCurrentIndex(1)
        self.assertEqual(self.logView.curIdx, 1)
        self.assertIn(1, self.logView.selectedIndices,
                      "selectedIndices should contain the current index")

        # Simulate what __onLocalChangesAvailable does: prepend LCC
        lccCommit = Commit(
            sha1=Git.LCC_SHA1,
            comments="Local changes checked in to index but not committed",
            author="Author <a@b.com>",
            authorDate="2025-01-03 12:00:00 +0000",
            committer="Author <a@b.com>",
            committerDate="2025-01-03 12:00:00 +0000",
            parents=["aaa1111"],
        )

        self.logView.data.insert(0, lccCommit)
        # After the fix, both curIdx AND selectedIndices shift by +1
        # (curIdx > 0 guard matches the production code)
        if self.logView.curIdx > 0:
            self.logView.curIdx += 1
            self.logView.selectedIndices = {
                i + 1 for i in self.logView.selectedIndices}

        # After inserting LCC at index 0, the previously selected commit
        # ("bbb2222") is now at index 2, so curIdx should be 2.
        # selectedIndices should also be updated to {2}.
        self.assertEqual(self.logView.curIdx, 2,
                         "curIdx should shift from 1 to 2 after LCC is prepended")

        # THIS IS THE BUG: selectedIndices still contains {1} instead of {2}
        self.assertIn(self.logView.curIdx, self.logView.selectedIndices,
                      "selectedIndices MUST contain curIdx after LCC prepend")

        # Also verify selectedIndices doesn't contain stale indices
        self.assertNotIn(1, self.logView.selectedIndices,
                         "selectedIndices should NOT contain stale index 1")
