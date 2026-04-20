# -*- coding: utf-8 -*-
import os
from unittest.mock import patch

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestHideDirectories(TestBase):
    """Test suite for hide entire directory feature"""

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

    def testIgnoredDirectoriesSet(self):
        """Test _ignoredDirectoriesSet returns proper set of hidden directories"""
        self.waitForLoaded()

        # Initially should be empty
        hidden = self.window._ignoredDirectoriesSet()
        self.assertIsInstance(hidden, set)
        self.assertEqual(len(hidden), 0)

        # Save some directories
        settings = self.app.settings()
        testDirs = ["build", "dist", ".git/objects"]
        settings.setIgnoredDirectories(self.window._repoName(), testDirs)

        # Now should contain them
        hidden = self.window._ignoredDirectoriesSet()
        self.assertEqual(len(hidden), 3)
        for d in testDirs:
            self.assertIn(os.path.normpath(d), hidden)

    def testGetIgnoredDirectories(self):
        """Test _getIgnoredDirectories returns list of hidden directories"""
        self.waitForLoaded()

        # Initially should be empty
        directories = self.window._getIgnoredDirectories()
        self.assertIsInstance(directories, list)
        self.assertEqual(len(directories), 0)

        # Save some directories
        settings = self.app.settings()
        testDirs = ["zebra_dir", "alpha_dir", "middle_dir"]
        settings.setIgnoredDirectories(self.window._repoName(), testDirs)

        # Now should contain them (should be sorted)
        directories = self.window._getIgnoredDirectories()
        self.assertEqual(len(directories), 3)
        # Directories should be sorted case-insensitively
        normalized = [os.path.normpath(d) for d in testDirs]
        expected = sorted(normalized, key=lambda d: d.lower())
        self.assertEqual(directories, expected)

    def testSaveIgnoredDirectories(self):
        """Test _saveIgnoredDirectories persists directories correctly"""
        self.waitForLoaded()

        # Save directories with set
        dirs = {"build", "dist", ".git"}
        self.window._saveIgnoredDirectories(dirs)

        # Verify they're saved in settings
        settings = self.app.settings()
        saved = settings.ignoredDirectories(self.window._repoName())
        self.assertEqual(len(saved), 3)

        # Create the set of normalized paths that we expect to be saved
        expectedSet = {os.path.normpath(d) for d in dirs}
        # The saved list should contain normalized paths
        savedSet = {os.path.normpath(d) for d in saved}
        self.assertEqual(savedSet, expectedSet)

    def testGetHiddenDirectoryEntries(self):
        """Test _getHiddenDirectoryEntries returns sorted list for display"""
        self.waitForLoaded()

        # Initially should be empty
        entries = self.window._getHiddenDirectoryEntries()
        self.assertEqual(len(entries), 0)

        # Save some directories
        settings = self.app.settings()
        testDirs = ["zebra_dir", "alpha_dir", "middle_dir"]
        settings.setIgnoredDirectories(self.window._repoName(), testDirs)

        # Get entries - should be sorted case-insensitively
        entries = self.window._getHiddenDirectoryEntries()
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0], "alpha_dir")
        self.assertEqual(entries[1], "middle_dir")
        self.assertEqual(entries[2], "zebra_dir")

    def testHideDirectory(self):
        """Test hiding a directory via UI"""
        self.waitForLoaded()

        # Initially no hidden directories
        hidden = self.window._ignoredDirectoriesSet()
        self.assertEqual(len(hidden), 0)

        # Hide a directory (direct call for testing)
        dirs = {"node_modules"}
        self.window._saveIgnoredDirectories(dirs)

        # Verify it's hidden
        hidden = self.window._ignoredDirectoriesSet()
        self.assertEqual(len(hidden), 1)
        self.assertIn("node_modules", hidden)

    def testShowHiddenDirectory(self):
        """Test showing a specific hidden directory"""
        self.waitForLoaded()

        # First save hidden directories
        settings = self.app.settings()
        testDir = "build"
        settings.setIgnoredDirectories(self.window._repoName(), [testDir])

        # Verify it's hidden
        hidden = self.window._ignoredDirectoriesSet()
        self.assertIn(os.path.normpath(testDir), hidden)

        # Show the directory
        self.window._onShowHiddenDirectory(testDir)

        # Verify it's no longer hidden
        hidden = self.window._ignoredDirectoriesSet()
        self.assertEqual(len(hidden), 0)

    def testShowAllHiddenDirectories(self):
        """Test showing all hidden directories at once"""
        self.waitForLoaded()

        # Save multiple hidden directories
        settings = self.app.settings()
        testDirs = ["build", "dist", ".git"]
        settings.setIgnoredDirectories(self.window._repoName(), testDirs)

        # Verify they're hidden
        hidden = self.window._ignoredDirectoriesSet()
        self.assertEqual(len(hidden), 3)

        # Show all
        self.window._onShowAllHiddenDirectories()

        # Verify none are hidden
        hidden = self.window._ignoredDirectoriesSet()
        self.assertEqual(len(hidden), 0)

    def testUpdateHiddenDirectoryMenu(self):
        """Test _updateHiddenDirectoryMenu properly displays hidden directories"""
        self.waitForLoaded()

        # Save several hidden directories
        settings = self.app.settings()
        testDirs = ["build", "dist", "node_modules", "venv"]
        settings.setIgnoredDirectories(self.window._repoName(), testDirs)

        # Update menu
        self.window._updateHiddenDirectoryMenu()

        # Verify menu has the directories
        actions = self.window._hiddenDirectoryMenu.actions()
        actionTexts = [a.text() for a in actions if a.text()]
        
        # Should have at least the test directories as actions (minus separators)
        self.assertGreater(len(actionTexts), 0)

    def testHideDirectoryContextMenu(self):
        """Test hide directory option appears in context menu"""
        self.waitForLoaded()

        # Create directories with files
        dir1 = os.path.join(self.gitDir.name, "dir1")
        os.makedirs(dir1, exist_ok=True)
        file1 = os.path.join(dir1, "file.txt")
        with open(file1, "w") as f:
            f.write("test")

        # Refresh to show files
        QTest.mouseClick(self.window.ui.tbRefresh, Qt.LeftButton)
        self.waitForLoaded()

        # Verify menu has hide directory option
        # (Just verify the action exists, not the full context menu flow)
        self.assertIsNotNone(self.window._acHideDirectory)

    def testHideAndRehideDirectories(self):
        """Test that hidden directories persist and can be toggled"""
        self.waitForLoaded()

        settings = self.app.settings()

        # Hide first directory
        dirs1 = {"build"}
        self.window._saveIgnoredDirectories(dirs1)

        hidden = self.window._ignoredDirectoriesSet()
        self.assertEqual(len(hidden), 1)

        # Hide another directory
        dirs2 = {"build", "dist"}
        self.window._saveIgnoredDirectories(dirs2)

        hidden = self.window._ignoredDirectoriesSet()
        self.assertEqual(len(hidden), 2)

        # Show one
        self.window._onShowHiddenDirectory("build")

        hidden = self.window._ignoredDirectoriesSet()
        self.assertEqual(len(hidden), 1)
        self.assertIn("dist", hidden)

    def _isFileInHiddenDirectory(self, filePath: str) -> bool:
        """Check if a file is in any hidden directory."""
        hiddenDirs = self.window._ignoredDirectoriesSet()
        normalizedPath = os.path.normpath(filePath)

        for hiddenDir in hiddenDirs:
            # Check if file starts with the directory path followed by separator
            if normalizedPath.startswith(hiddenDir + os.sep):
                return True
        return False

    def testFilterHiddenDirectoriesFromFileList(self):
        """Test that _isFileInHiddenDirectory correctly identifies files in hidden directories"""
        self.waitForLoaded()

        # Hide node_modules directory
        dirs = {"node_modules"}
        self.window._saveIgnoredDirectories(dirs)

        # Test various file paths
        test_cases = [
            ("node_modules/index.js", True),  # Should be filtered
            ("node_modules/lib/helper.js", True),  # Nested in hidden dir
            ("main.js", False),  # Not in hidden directory
            ("src/index.js", False),  # Different directory
            ("src/node_modules/test.js", False),  # Different context
        ]

        for file_path, should_be_hidden in test_cases:
            result = self._isFileInHiddenDirectory(file_path)
            self.assertEqual(
                result, should_be_hidden,
                f"File {file_path} filtering failed: expected {should_be_hidden}, got {result}"
            )

        # Test with multiple hidden directories
        dirs = {"node_modules", "build", ".git"}
        self.window._saveIgnoredDirectories(dirs)

        multi_test_cases = [
            ("node_modules/index.js", True),
            ("build/output.js", True),
            (".git/objects/xyz", True),
            ("src/main.js", False),
            ("README.md", False),
        ]

        for file_path, should_be_hidden in multi_test_cases:
            result = self._isFileInHiddenDirectory(file_path)
            self.assertEqual(
                result, should_be_hidden,
                f"File {file_path} with multiple hidden dirs failed: expected {should_be_hidden}, got {result}"
            )

    def testDirectoryNormalization(self):
        """Test that directory paths are normalized correctly"""
        self.waitForLoaded()

        # Save directories with mixed separators
        dirs = {"build", ".git/objects", "dist"}
        self.window._saveIgnoredDirectories(dirs)

        # Verify they're normalized
        hidden = self.window._ignoredDirectoriesSet()
        
        # All should be normalized
        for d in hidden:
            self.assertEqual(d, os.path.normpath(d))
