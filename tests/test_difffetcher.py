# -*- coding: utf-8 -*-

import unittest

from qgitc.difffetcher import DiffFetcher
from qgitc.diffutils import DiffType, FileState


class TestDiffFetcher(unittest.TestCase):
    """Test suite for DiffFetcher parse() method"""

    def setUp(self):
        """Set up test fixtures"""
        self.fetcher = DiffFetcher()
        self.fetcher.separator = b'\x00'

    def _parse_and_get_results(self, diff_data):
        """Helper method to parse diff and capture emitted signals"""
        self.lineItems = None
        self.fileItems = None

        def capture(lineItems, fileItems):
            self.lineItems = lineItems
            self.fileItems = fileItems

        self.fetcher.diffAvailable.connect(capture)
        self.fetcher.resetRow(0)
        self.fetcher.parse(diff_data)

        return self.lineItems, self.fileItems

    def test_added_file(self):
        """Test parsing of a newly added file"""
        diff_data = b'\x00'.join([
            b'diff --git a/newfile.txt b/newfile.txt',
            b'new file mode 100644',
            b'index 0000000..e69de29',
            b'@@ -0,0 +1,3 @@',
            b'+line1',
            b'+line2',
            b'+line3',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIsNotNone(lineItems)
        self.assertIsNotNone(fileItems)
        self.assertIn('newfile.txt', fileItems)
        self.assertEqual(fileItems['newfile.txt'].state, FileState.Added,
                         "File state should be Added")

    def test_deleted_file(self):
        """Test parsing of a deleted file"""
        diff_data = b'\x00'.join([
            b'diff --git a/oldfile.txt b/oldfile.txt',
            b'deleted file mode 100644',
            b'index e69de29..0000000',
            b'@@ -1,3 +0,0 @@',
            b'-line1',
            b'-line2',
            b'-line3',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('oldfile.txt', fileItems)
        self.assertEqual(fileItems['oldfile.txt'].state, FileState.Deleted,
                         "File state should be Deleted")

    def test_modified_file(self):
        """Test parsing of a modified file"""
        diff_data = b'\x00'.join([
            b'diff --git a/modified.txt b/modified.txt',
            b'index abc123..def456 100644',
            b'@@ -1,3 +1,3 @@',
            b' line1',
            b'-line2',
            b'+line2 modified',
            b' line3',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('modified.txt', fileItems)
        self.assertEqual(fileItems['modified.txt'].state, FileState.Modified,
                         "File state should be Modified")

    def test_renamed_file_only(self):
        """Test parsing of a file that was only renamed (no content change)"""
        diff_data = b'\x00'.join([
            b'diff --git a/oldname.txt b/newname.txt',
            b'rename from oldname.txt',
            b'rename to newname.txt',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        # Both old and new names should be in fileItems
        self.assertIn('newname.txt', fileItems)
        self.assertEqual(fileItems['newname.txt'].state, FileState.Renamed,
                         "File state should be Renamed")

    def test_renamed_and_modified_file(self):
        """Test parsing of a file that was renamed AND modified"""
        diff_data = b'\x00'.join([
            b'diff --git a/oldname.txt b/newname.txt',
            b'rename from oldname.txt',
            b'rename to newname.txt',
            b'index abc123..def456 100644',
            b'@@ -1,3 +1,3 @@',
            b' line1',
            b'-line2',
            b'+line2 modified',
            b' line3',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('newname.txt', fileItems)
        self.assertEqual(fileItems['newname.txt'].state, FileState.RenamedModified,
                         "File state should be RenamedModified")

    def test_multiple_files_different_states(self):
        """Test parsing multiple files with different states"""
        diff_data = b'\x00'.join([
            b'diff --git a/added.txt b/added.txt',
            b'new file mode 100644',
            b'index 0000000..abc123',
            b'@@ -0,0 +1 @@',
            b'+new content',
            b'diff --git a/modified.txt b/modified.txt',
            b'index abc123..def456 100644',
            b'@@ -1 +1 @@',
            b'-old',
            b'+new',
            b'diff --git a/deleted.txt b/deleted.txt',
            b'deleted file mode 100644',
            b'index abc123..0000000',
            b'@@ -1 +0,0 @@',
            b'-content',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertEqual(len(fileItems), 3)
        self.assertEqual(fileItems['added.txt'].state, FileState.Added)
        self.assertEqual(fileItems['modified.txt'].state, FileState.Modified)
        self.assertEqual(fileItems['deleted.txt'].state, FileState.Deleted)

    def test_submodule_diff(self):
        """Test parsing of submodule changes"""
        diff_data = b'\x00'.join([
            b'Submodule mysubmodule abc1234..def5678:',
            b'  > Commit message',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('mysubmodule', fileItems)

    def test_merge_conflict_diff(self):
        """Test parsing of merge conflict diff (--cc)"""
        diff_data = b'\x00'.join([
            b'diff --cc conflict.txt',
            b'index abc123,def456..0000000',
            b'@@@ -1,1 -1,1 +1,1 @@@',
            b'++resolved content',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('conflict.txt', fileItems)

    def test_empty_diff(self):
        """Test parsing of empty diff data"""
        diff_data = b'\x00'

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        # Empty diff may not emit signal
        if lineItems is not None:
            self.assertEqual(len(lineItems), 0)
            self.assertEqual(len(fileItems), 0)

    def test_added_blank_file(self):
        """Test edge case: added blank file with no diff content"""
        diff_data = b'\x00'.join([
            b'diff --git a/blank.txt b/blank.txt',
            b'new file mode 100644',
            b'index 0000000..e69de29',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('blank.txt', fileItems)
        self.assertEqual(fileItems['blank.txt'].state, FileState.Added,
                         "Blank added file should have Added state")

    def test_renamed_with_similarity(self):
        """Test renamed file with similarity index"""
        diff_data = b'\x00'.join([
            b'diff --git a/old.txt b/new.txt',
            b'similarity index 100%',
            b'rename from old.txt',
            b'rename to new.txt',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('new.txt', fileItems)
        self.assertEqual(fileItems['new.txt'].state, FileState.Renamed)

    def test_file_state_bug_scenario(self):
        """
        Test edge case that exposes the fileState bug:
        When a file has mode info but no diff content before next file
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file1.txt b/file1.txt',
            b'new file mode 100644',
            b'index 0000000..e69de29',
            b'diff --git a/file2.txt b/file2.txt',
            b'index abc123..def456 100644',
            b'@@ -1 +1 @@',
            b'-old',
            b'+new',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        # BUG: file1.txt state might not be set correctly
        self.assertIn('file1.txt', fileItems)
        self.assertEqual(fileItems['file1.txt'].state, FileState.Added,
                         "file1.txt should be Added even without diff content")
        self.assertIn('file2.txt', fileItems)
        self.assertEqual(fileItems['file2.txt'].state, FileState.Modified)

    def test_normal_file_no_mode_change(self):
        """Test file without special mode changes (should remain Normal before diff)"""
        diff_data = b'\x00'.join([
            b'diff --git a/normal.txt b/normal.txt',
            b'@@ -1 +1 @@',
            b'-old',
            b'+new',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('normal.txt', fileItems)
        # Should be Normal initially, but might become Modified
        # depending on implementation

    def test_repodir_submodule_path(self):
        """Test makeFilePath with repoDir set"""
        self.fetcher.repoDir = "submodule/path"

        file_path = self.fetcher.makeFilePath(b'test.txt')

        self.assertEqual(file_path, b'submodule/path/test.txt')

    def test_repodir_none(self):
        """Test makeFilePath without repoDir"""
        self.fetcher.repoDir = None

        file_path = self.fetcher.makeFilePath(b'test.txt')

        self.assertEqual(file_path, b'test.txt')

    def test_line_types(self):
        """Test that line types are correctly identified"""
        diff_data = b'\x00'.join([
            b'diff --git a/test.txt b/test.txt',
            b'index abc123..def456 100644',
            b'@@ -1,3 +1,3 @@',
            b' context line',
            b'-removed line',
            b'+added line',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        # Check that we have the right mix of types
        types = [item[0] for item in lineItems]
        self.assertIn(DiffType.File, types)
        self.assertIn(DiffType.FileInfo, types)
        self.assertIn(DiffType.Diff, types)

    def test_multiple_hunks(self):
        """Test file with multiple diff hunks"""
        diff_data = b'\x00'.join([
            b'diff --git a/file.txt b/file.txt',
            b'index abc123..def456 100644',
            b'@@ -1,3 +1,3 @@',
            b' line1',
            b'-line2',
            b'+line2 modified',
            b' line3',
            b'@@ -10,3 +10,3 @@',
            b' line10',
            b'-line11',
            b'+line11 modified',
            b' line12',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('file.txt', fileItems)
        # Count diff hunks
        diff_markers = [
            item for item in lineItems if item[1].startswith(b'@@')]
        self.assertEqual(len(diff_markers), 2)

    def test_consecutive_mode_changes(self):
        """
        Test edge case: multiple files with mode changes in sequence
        This tests the _updateFileState() logic between files
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file1.txt b/file1.txt',
            b'new file mode 100644',
            b'diff --git a/file2.txt b/file2.txt',
            b'deleted file mode 100644',
            b'diff --git a/file3.txt b/file3.txt',
            b'index abc123..def456 100644',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        # Each file should have its own state
        self.assertEqual(fileItems['file1.txt'].state, FileState.Added,
                         "file1.txt state should be Added")
        self.assertEqual(fileItems['file2.txt'].state, FileState.Deleted,
                         "file2.txt state should be Deleted")
        self.assertEqual(fileItems['file3.txt'].state, FileState.Modified,
                         "file3.txt state should be Modified")

    def test_binary_file_diff(self):
        """Test handling of binary file diffs"""
        diff_data = b'\x00'.join([
            b'diff --git a/image.png b/image.png',
            b'index abc123..def456 100644',
            b'Binary files a/image.png and b/image.png differ',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('image.png', fileItems)

    def test_filestate_not_reset_bug(self):
        """
        Test critical bug: fileState persists between files incorrectly.
        If file has 'new file mode' but next file starts before _updateFileState,
        the state might not be applied.
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file1.txt b/file1.txt',
            b'new file mode 100644',
            # No index line here - directly to next file
            b'diff --git a/file2.txt b/file2.txt',
            b'index abc123..def456 100644',
            b'@@ -1 +1 @@',
            b'-old',
            b'+new',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        # This should catch if fileState isn't properly applied
        self.assertIn('file1.txt', fileItems)
        self.assertEqual(fileItems['file1.txt'].state, FileState.Added,
                         "BUG: file1.txt state was not applied before next diff started")

    def test_filestate_with_only_metadata(self):
        """
        Test when file has metadata (deleted/new) but no actual diff content
        """
        diff_data = b'\x00'.join([
            b'diff --git a/deleted.txt b/deleted.txt',
            b'deleted file mode 100644',
            b'diff --git a/added.txt b/added.txt',
            b'new file mode 100644',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('deleted.txt', fileItems)
        self.assertEqual(fileItems['deleted.txt'].state, FileState.Deleted,
                         "deleted.txt should be Deleted even without diff content")
        self.assertIn('added.txt', fileItems)
        self.assertEqual(fileItems['added.txt'].state, FileState.Added,
                         "added.txt should be Added even without diff content")

    def test_renamed_then_normal_file(self):
        """
        Test that rename state doesn't leak to next file
        """
        diff_data = b'\x00'.join([
            b'diff --git a/old.txt b/new.txt',
            b'rename from old.txt',
            b'rename to new.txt',
            b'diff --git a/normal.txt b/normal.txt',
            b'index abc123..def456 100644',
            b'@@ -1 +1 @@',
            b'-old',
            b'+new',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertEqual(fileItems['new.txt'].state, FileState.Renamed)
        self.assertEqual(fileItems['normal.txt'].state, FileState.Modified,
                         "normal.txt should not inherit Renamed state")

    def test_index_before_diff_marker(self):
        """
        Test that 'index' line correctly triggers state from Normal to Modified
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file.txt b/file.txt',
            b'index abc123..def456 100644',
            b'@@ -1 +1 @@',
            b'-old',
            b'+new',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertEqual(fileItems['file.txt'].state, FileState.Modified)

    def test_index_without_diff_content(self):
        """
        Test edge case: index line but no actual diff content follows
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file.txt b/file.txt',
            b'index abc123..def456 100644',
            # No @@ marker, no diff
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('file.txt', fileItems)
        self.assertEqual(fileItems['file.txt'].state, FileState.Modified,
                         "File with index should be Modified even without diff content")

    def test_updatefilestate_at_end(self):
        """
        Test that _updateFileState is called at the end of parsing
        to handle the last file's state
        """
        diff_data = b'\x00'.join([
            b'diff --git a/last.txt b/last.txt',
            b'deleted file mode 100644',
            b'index abc123..0000000',
            # No diff content, ends here
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('last.txt', fileItems)
        self.assertEqual(fileItems['last.txt'].state, FileState.Deleted,
                         "Last file's state must be applied even at end of parse")

    def test_multiple_files_state_isolation(self):
        """
        Comprehensive test: ensure each file's state is independent
        """
        diff_data = b'\x00'.join([
            b'diff --git a/f1.txt b/f1.txt',
            b'new file mode 100644',
            b'index 0000000..abc123',
            b'diff --git a/f2.txt b/f2.txt',
            b'deleted file mode 100644',
            b'index abc123..0000000',
            b'diff --git a/old.txt b/new.txt',
            b'rename from old.txt',
            b'rename to new.txt',
            b'diff --git a/oldmod.txt b/newmod.txt',
            b'rename from oldmod.txt',
            b'rename to newmod.txt',
            b'index abc123..def456',
            b'diff --git a/f3.txt b/f3.txt',
            b'index abc123..def456 100644',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertEqual(fileItems['f1.txt'].state, FileState.Added,
                         "f1.txt should be Added")
        self.assertEqual(fileItems['f2.txt'].state, FileState.Deleted,
                         "f2.txt should be Deleted")
        self.assertEqual(fileItems['new.txt'].state, FileState.Renamed,
                         "new.txt should be Renamed")
        self.assertEqual(fileItems['newmod.txt'].state, FileState.RenamedModified,
                         "newmod.txt should be RenamedModified")
        self.assertEqual(fileItems['f3.txt'].state, FileState.Modified,
                         "f3.txt should be Modified")

    def test_state_transitions(self):
        """
        Test the state machine transitions:
        - Normal -> Added (new file mode)
        - Normal -> Deleted (deleted file mode)
        - Normal -> Renamed (rename)
        - Normal -> Modified (index)
        - Renamed -> RenamedModified (rename + index)
        """
        # Already covered by other tests, but let's be explicit
        test_cases = [
            # (description, diff_input, expected_state)
            ("new file", [b'diff --git a/f.txt b/f.txt',
             b'new file mode 100644'], FileState.Added),
            ("deleted file", [b'diff --git a/f.txt b/f.txt',
             b'deleted file mode 100644'], FileState.Deleted),
            ("renamed", [b'diff --git a/f.txt b/f.txt',
             b'rename from f.txt'], FileState.Renamed),
            ("modified", [b'diff --git a/f.txt b/f.txt',
             b'index abc..def 100644'], FileState.Modified),
        ]

        for desc, diff_lines, expected in test_cases:
            with self.subTest(desc=desc):
                self.fetcher.resetRow(0)
                diff_data = b'\x00'.join(diff_lines + [b'\x00'])
                lineItems, fileItems = self._parse_and_get_results(diff_data)
                self.assertIn('f.txt', fileItems)
                self.assertEqual(fileItems['f.txt'].state, expected,
                                 f"{desc}: expected state {expected}")

    def test_realistic_git_diff_output(self):
        """
        Test with realistic git diff output format
        """
        diff_data = b'\x00'.join([
            b'diff --git a/qgitc/difffetcher.py b/qgitc/difffetcher.py',
            b'index 1234567..89abcde 100644',
            b'--- a/qgitc/difffetcher.py',
            b'+++ b/qgitc/difffetcher.py',
            b'@@ -120,6 +120,7 @@ class DiffFetcher(DataFetcher):',
            b'         fullFileAStr = None',
            b'         fullFileBStr = None',
            b'         fileState = FileState.Normal',
            b'+        # Fixed bug',
            b' ',
            b'         def _updateFileState():',
            b'             nonlocal fullFileAStr, fullFileBStr, fileState',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('qgitc/difffetcher.py', fileItems)
        self.assertEqual(
            fileItems['qgitc/difffetcher.py'].state, FileState.Modified)

    def test_file_with_spaces_in_name(self):
        """
        Test handling of files with spaces (should be quoted in git output)
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file with spaces.txt b/file with spaces.txt',
            b'new file mode 100644',
            b'index 0000000..abc123',
            b'@@ -0,0 +1 @@',
            b'+content',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('file with spaces.txt', fileItems)
        self.assertEqual(
            fileItems['file with spaces.txt'].state, FileState.Added)

    def test_permission_change_only(self):
        """
        Test file with only permission change (mode change)
        """
        diff_data = b'\x00'.join([
            b'diff --git a/script.sh b/script.sh',
            b'old mode 100644',
            b'new mode 100755',
            b'index abc123..abc123',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('script.sh', fileItems)
        # Permission change might be detected as Modified

    def test_copy_file(self):
        """
        Test copied file (similar to rename)
        """
        diff_data = b'\x00'.join([
            b'diff --git a/original.txt b/copy.txt',
            b'similarity index 100%',
            b'copy from original.txt',
            b'copy to copy.txt',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('copy.txt', fileItems)

    def test_no_newline_at_end_of_file(self):
        """
        Test diff with 'No newline at end of file' marker
        """
        diff_data = b'\x00'.join([
            b'diff --git a/file.txt b/file.txt',
            b'index abc123..def456 100644',
            b'@@ -1 +1 @@',
            b'-old',
            b'\\ No newline at end of file',
            b'+new',
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('file.txt', fileItems)

    def test_very_long_diff(self):
        """
        Test parsing performance with a long diff
        """
        lines = [b'diff --git a/bigfile.txt b/bigfile.txt',
                 b'index abc123..def456 100644',
                 b'@@ -1,1000 +1,1000 @@']

        # Add 1000 lines of diff content
        for i in range(500):
            lines.append(f' context line {i}'.encode())
            lines.append(f'-removed line {i}'.encode())
            lines.append(f'+added line {i}'.encode())

        lines.append(b'\x00')
        diff_data = b'\x00'.join(lines)

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('bigfile.txt', fileItems)
        # Should complete without timeout or crash

    def test_unicode_in_diff(self):
        """
        Test handling of unicode characters in diff content
        """
        diff_data = b'\x00'.join([
            b'diff --git a/unicode.txt b/unicode.txt',
            b'index abc123..def456 100644',
            b'@@ -1 +1 @@',
            b'-\xe4\xb8\xad\xe6\x96\x87',  # Chinese characters in UTF-8
            b'+\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e',  # Japanese in UTF-8
            b'\x00'
        ])

        lineItems, fileItems = self._parse_and_get_results(diff_data)

        self.assertIn('unicode.txt', fileItems)
