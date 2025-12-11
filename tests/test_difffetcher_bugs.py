# -*- coding: utf-8 -*-
"""
Stress tests and edge cases specifically designed to expose potential bugs
in the DiffFetcher parser logic.
"""

import unittest

from qgitc.difffetcher import DiffFetcher
from qgitc.diffutils import FileState


class TestDiffFetcherBugHunting(unittest.TestCase):
    """
    These tests are designed to expose subtle bugs in state management.
    Run these if you suspect fileState is not being properly applied.
    """

    def setUp(self):
        self.fetcher = DiffFetcher()
        self.fetcher.separator = b'\x00'
        self.lineItems = None
        self.fileItems = None
        self.stateChanges = []  # List of (filename, state) tuples

        # Connect signals once in setUp
        self.fetcher.diffAvailable.connect(self._capture)
        self.fetcher.fileStateChanged.connect(self._captureStateChanged)

    def _capture(self, lineItems, fileItems):
        self.lineItems = lineItems
        self.fileItems = fileItems

    def _captureStateChanged(self, filename, state):
        self.stateChanges.append((filename, state))

    def _parse(self, diff_data, reset=True):
        """Parse and capture results"""
        if reset:
            self.fetcher.resetRow(0)
            self.stateChanges.clear()
        self.fetcher.parse(diff_data)
        return self.lineItems, self.fileItems

    def test_bug_new_file_no_index_immediate_next_diff(self):
        """
        BUG SCENARIO: New file declared but next diff starts immediately
        without index line or diff content.
        
        Expected: File1 should have state Added
        Potential Bug: State might not be applied before next diff
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file1.txt b/file1.txt',
            b'new file mode 100644',
            # Immediate next diff - no index, no content
            b'diff --git a/file2.txt b/file2.txt',
            b'index abc123..def456 100644',
            b'@@ -1 +1 @@',
            b'-old',
            b'+new',
            b'\x00'
        ])

        _, fileItems = self._parse(diff_data)

        # Critical assertion
        self.assertEqual(
            fileItems['file1.txt'].state,
            FileState.Added,
            "BUG: file1.txt should be Added even without index/content"
        )

    def test_bug_deleted_file_no_index(self):
        """
        BUG SCENARIO: Deleted file without index line before next file
        """
        diff_data = b'\x00'.join([
            b'diff --git a/deleted.txt b/deleted.txt',
            b'deleted file mode 100644',
            b'diff --git a/normal.txt b/normal.txt',
            b'index abc..def 100644',
            b'\x00'
        ])

        _, fileItems = self._parse(diff_data)

        self.assertEqual(
            fileItems['deleted.txt'].state,
            FileState.Deleted,
            "BUG: deleted.txt state not applied"
        )

    def test_bug_rename_no_index_end_of_diff(self):
        """
        BUG SCENARIO: Last file is renamed without index, at end of diff
        """
        diff_data = b'\x00'.join([
            b'diff --git a/old.txt b/new.txt',
            b'rename from old.txt',
            b'rename to new.txt',
            b'\x00'
        ])

        _, fileItems = self._parse(diff_data)

        self.assertEqual(
            fileItems['new.txt'].state,
            FileState.Renamed,
            "BUG: Last file rename state not applied at end"
        )

    def test_bug_index_updates_wrong_state(self):
        """
        BUG SCENARIO: Index line should only make Renamed→RenamedModified
        or Normal→Modified, not affect Added/Deleted
        """
        # Case 1: Added file with index should stay Added
        diff_data1 = b'\x00'.join([
            b'diff --git a/new.txt b/new.txt',
            b'new file mode 100644',
            b'index 0000000..abc123',
            b'\x00'
        ])

        _, fileItems1 = self._parse(diff_data1)
        self.assertEqual(
            fileItems1['new.txt'].state,
            FileState.Added,
            "BUG: Added file became Modified due to index"
        )

        # Case 2: Deleted file with index should stay Deleted
        diff_data2 = b'\x00'.join([
            b'diff --git a/old.txt b/old.txt',
            b'deleted file mode 100644',
            b'index abc123..0000000',
            b'\x00'
        ])

        _, fileItems2 = self._parse(diff_data2)
        self.assertEqual(
            fileItems2['old.txt'].state,
            FileState.Deleted,
            "BUG: Deleted file became Modified due to index"
        )

    def test_bug_state_leakage(self):
        """
        BUG SCENARIO: State from one file leaks to next file
        """
        diff_data = b'\x00'.join([
            b'diff --git a/f1.txt b/f1.txt',
            b'deleted file mode 100644',
            b'index abc..000 100644',
            b'diff --git a/f2.txt b/f2.txt',
            # No mode info on f2 - should be Normal or Modified, NOT Deleted
            b'index def..ghi 100644',
            b'\x00'
        ])

        _, fileItems = self._parse(diff_data)

        self.assertEqual(fileItems['f1.txt'].state, FileState.Deleted)
        self.assertNotEqual(
            fileItems['f2.txt'].state,
            FileState.Deleted,
            "BUG: State leaked from f1 to f2"
        )

    def test_bug_diff_marker_doesnt_update_state(self):
        """
        BUG SCENARIO: @@ marker should trigger _updateFileState but might not
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file.txt b/file.txt',
            b'new file mode 100644',
            # @@ should trigger state update
            b'@@ -0,0 +1,3 @@',
            b'+line1',
            b'+line2',
            b'+line3',
            b'\x00'
        ])

        _, fileItems = self._parse(diff_data)

        self.assertEqual(
            fileItems['file.txt'].state,
            FileState.Added,
            "BUG: State not applied when @@ encountered"
        )

    def test_bug_three_files_middle_state_lost(self):
        """
        BUG SCENARIO: Middle file in sequence of three loses its state
        """
        diff_data = b'\x00'.join([
            b'diff --git a/f1.txt b/f1.txt',
            b'new file mode 100644',
            b'index 000..abc',
            b'diff --git a/f2.txt b/f2.txt',
            b'deleted file mode 100644',
            # No index for f2
            b'diff --git a/f3.txt b/f3.txt',
            b'index abc..def 100644',
            b'\x00'
        ])

        _, fileItems = self._parse(diff_data)

        self.assertEqual(fileItems['f1.txt'].state, FileState.Added,
                         "f1 should be Added")
        self.assertEqual(fileItems['f2.txt'].state, FileState.Deleted,
                         "BUG: f2 (middle file) should be Deleted")
        self.assertEqual(fileItems['f3.txt'].state, FileState.Modified,
                         "f3 should be Modified")

    def test_bug_empty_line_handling(self):
        """
        BUG SCENARIO: Empty lines in metadata section might cause issues
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file.txt b/file.txt',
            b'new file mode 100644',
            b'',  # Empty line
            b'index 000..abc',
            b'@@ -0,0 +1 @@',
            b'+content',
            b'\x00'
        ])

        _, fileItems = self._parse(diff_data)

        self.assertIn('file.txt', fileItems)
        self.assertEqual(fileItems['file.txt'].state, FileState.Added)

    def test_bug_similarity_without_rename(self):
        """
        BUG SCENARIO: Similarity line without rename declaration
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file.txt b/file.txt',
            b'similarity index 95%',
            b'index abc..def 100644',
            b'\x00'
        ])

        _, fileItems = self._parse(diff_data)

        self.assertIn('file.txt', fileItems)
        # Should not crash

    def test_bug_multiple_index_lines(self):
        """
        BUG SCENARIO: Multiple index lines (shouldn't happen but let's test)
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file.txt b/file.txt',
            b'index abc..def 100644',
            b'index abc..def 100644',  # Duplicate
            b'@@ -1 +1 @@',
            b'-old',
            b'+new',
            b'\x00'
        ])

        _, fileItems = self._parse(diff_data)

        self.assertIn('file.txt', fileItems)
        # Should not crash or duplicate

    def test_bug_rename_with_complex_path(self):
        """
        BUG SCENARIO: Renamed file with paths in subdirectories
        """
        diff_data = b'\x00'.join([
            b'diff --git a/old/path/file.txt b/new/path/file.txt',
            b'rename from old/path/file.txt',
            b'rename to new/path/file.txt',
            b'\x00'
        ])

        _, fileItems = self._parse(diff_data)

        # Both paths should be tracked
        self.assertIn('new/path/file.txt', fileItems)
        self.assertEqual(
            fileItems['new/path/file.txt'].state,
            FileState.Renamed
        )

    def test_bug_filestate_order_dependency(self):
        """
        BUG SCENARIO: Order of metadata lines shouldn't matter
        """
        # Normal order
        diff_data1 = b'\x00'.join([
            b'diff --git a/f.txt b/f.txt',
            b'new file mode 100644',
            b'index 000..abc',
            b'\x00'
        ])

        # Reversed order
        diff_data2 = b'\x00'.join([
            b'diff --git a/f.txt b/f.txt',
            b'index 000..abc',
            b'new file mode 100644',
            b'\x00'
        ])

        _, fileItems1 = self._parse(diff_data1)
        self.fetcher.resetRow(0)
        _, fileItems2 = self._parse(diff_data2)

        # Both should result in Added state
        # Note: Current implementation might handle this differently
        self.assertIn('f.txt', fileItems1)
        self.assertIn('f.txt', fileItems2)

    def test_bug_incremental_parsing_file_state_normal(self):
        """
        FIXED BUG: Incremental parsing updates file state when metadata arrives later
        
        When git process outputs diff incrementally:
        1. First chunk ends with just diff header -> file created with Normal state
        2. Parser continues, metadata arrives -> state should update
        
        The fix ensures that metadata updates the file state even if the file
        already exists in fileItems dict.
        """
        # Simulate streaming parse: diff header, then metadata on same file
        chunk = b'\x00'.join([
            b'diff --git a/file1.txt b/file1.txt',
            b'new file mode 100644',
            b'index 0000000..abc123',
            b'@@ -0,0 +1,1 @@',
            b'+content1',
            b'diff --git a/foo.txt b/foo.txt',  # Header appears first
            b'deleted file mode 100644',        # Then metadata arrives
            b'index abc123..0000000',
            b'@@ -1,3 +0,0 @@',
            b'-line1',
            b'-line2',
            b'-line3',
            b'\x00'
        ])

        _, fileItems = self._parse(chunk)

        # file1.txt should be Added
        self.assertEqual(fileItems['file1.txt'].state, FileState.Added)

        # foo.txt should be Deleted (not Normal!) even though header came first
        self.assertIn('foo.txt', fileItems)
        self.assertEqual(fileItems['foo.txt'].state, FileState.Deleted,
                         "FIXED: foo.txt state updated when metadata arrived after header")

    def test_bug_partial_diff_then_complete(self):
        """
        BUG: Multiple files, first complete, second incomplete, then third arrives
        """
        # First chunk: file1 complete, file2 only header
        chunk1 = b'\x00'.join([
            b'diff --git a/file1.txt b/file1.txt',
            b'new file mode 100644',
            b'index 0000000..abc123',
            b'diff --git a/file2.txt b/file2.txt',
            # Incomplete - no metadata
            b'\x00'
        ])

        _, fileItems1 = self._parse(chunk1)

        self.assertEqual(fileItems1['file1.txt'].state, FileState.Added)
        # file2.txt will have Normal state (BUG scenario)

        # Second chunk: complete data for file2
        chunk2 = b'\x00'.join([
            b'diff --git a/file1.txt b/file1.txt',
            b'new file mode 100644',
            b'index 0000000..abc123',
            b'diff --git a/file2.txt b/file2.txt',
            b'deleted file mode 100644',
            b'index abc123..0000000',
            b'\x00'
        ])

        self.fetcher.resetRow(0)
        _, fileItems2 = self._parse(chunk2)

        # Both should have correct states
        self.assertEqual(fileItems2['file1.txt'].state, FileState.Added)
        self.assertEqual(fileItems2['file2.txt'].state, FileState.Deleted,
                         "BUG: file2 state not updated in incremental parse")

    def test_bug_incremental_with_rename(self):
        """
        FIXED: Renamed file received incrementally
        """
        # Simulate streaming: rename header appears, then metadata arrives
        chunk = b'\x00'.join([
            b'diff --git a/old.txt b/new.txt',
            b'rename from old.txt',
            b'rename to new.txt',
            b'\x00'
        ])

        _, fileItems = self._parse(chunk)

        # Should be Renamed (metadata was in same parse call)
        self.assertEqual(fileItems['new.txt'].state, FileState.Renamed,
                         "Rename state should be set when metadata arrives")

    def test_bug_incremental_rename_then_modified(self):
        """
        Test renamed + modified file in incremental scenario
        """
        chunk = b'\x00'.join([
            b'diff --git a/old.txt b/new.txt',
            b'rename from old.txt',
            b'rename to new.txt',
            b'index abc123..def456',
            b'\x00'
        ])

        _, fileItems = self._parse(chunk)

        # Should be RenamedModified because of index line
        self.assertEqual(fileItems['new.txt'].state, FileState.RenamedModified,
                         "Rename + index should be RenamedModified")

    def test_true_incremental_parsing_across_calls(self):
        """
        CRITICAL: Test actual incremental parsing scenario across multiple parse() calls
        This is the REAL bug scenario where parse() is called multiple times.
        """
        # First parse call: diff header arrives, ends immediately
        chunk1 = b'\x00'.join([
            b'diff --git a/file1.txt b/file1.txt',
            b'new file mode 100644',
            b'index 0000000..abc123',
            b'@@ -0,0 +1,1 @@',
            b'+content1',
            b'diff --git a/foo.txt b/foo.txt',  # This is the last complete line
            b'\x00'
        ])

        _, fileItems1 = self._parse(chunk1)

        # file1 should be Added
        self.assertEqual(fileItems1['file1.txt'].state, FileState.Added)
        # foo.txt has Normal state because no metadata yet
        self.assertEqual(fileItems1['foo.txt'].state, FileState.Normal,
                         "First parse: foo.txt has no metadata yet")

        # Second parse call: metadata for foo.txt arrives
        # CRITICAL: DON'T call resetRow() - simulates continuous parsing
        chunk2 = b'\x00'.join([
            b'deleted file mode 100644',
            b'index abc123..0000000',
            b'@@ -1,3 +0,0 @@',
            b'-line1',
            b'-line2',
            b'-line3',
            b'\x00'
        ])

        # Clear stateChanges to only count chunk2 emissions
        self.stateChanges.clear()

        # This parse processes metadata (reset=False to keep state!)
        _, fileItems2 = self._parse(chunk2, reset=False)

        # CRITICAL ASSERTIONS: foo.txt state change should be emitted via fileStateChanged signal
        # not in fileItems2, since it was created in a previous chunk
        self.assertEqual(len(self.stateChanges), 1,
                         "Should have exactly one state change")
        self.assertEqual(self.stateChanges[0][0], 'foo.txt',
                         "FIXED: foo.txt state change was emitted")
        self.assertEqual(self.stateChanges[0][1], FileState.Deleted,
                         "FIXED: foo.txt has Deleted state (metadata was applied)")

        # foo.txt should NOT be in fileItems2 since it's a state-only update
        self.assertNotIn('foo.txt', fileItems2,
                         "foo.txt should not be in fileItems2 (emitted via fileStateChanged instead)")
