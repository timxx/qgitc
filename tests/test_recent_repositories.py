# -*- coding: utf-8 -*-

import os

from qgitc.repopathinput import FuzzyStringListModel
from qgitc.settings import Settings
from tests.base import TestBase


class TestRecentRepositories(TestBase):
    def setUp(self):
        super().setUp()
        self.settings = Settings(testing=True)

    def tearDown(self):
        del self.settings
        super().tearDown()

    def doCreateRepo(self):
        pass

    def testRecentRepositoriesSettings(self):
        """Test recent repositories functionality in Settings"""
        # Test empty list initially
        recent = self.settings.recentRepositories()
        self.assertEqual(recent, [])

        # Test adding repositories
        self.settings.addRecentRepository("/path/to/repo1")
        self.settings.addRecentRepository("/path/to/repo2")

        recent = self.settings.recentRepositories()
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0], "/path/to/repo2")  # Most recent first
        self.assertEqual(recent[1], "/path/to/repo1")

        # Test adding existing repository (should move to front)
        self.settings.addRecentRepository("/path/to/repo1")
        recent = self.settings.recentRepositories()
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0], "/path/to/repo1")
        self.assertEqual(recent[1], "/path/to/repo2")

        # Test max limit
        for i in range(15):
            self.settings.addRecentRepository(f"/path/to/repo{i}")

        recent = self.settings.recentRepositories()
        self.assertEqual(len(recent), 10)  # Should be limited to 10

    def testFuzzyStringListModel(self):
        """Test fuzzy matching functionality"""
        model = FuzzyStringListModel()

        repos = [
            "/home/user/projects/qgitc",
            "/home/user/projects/myapp",
            "/var/repos/company-website",
            "/opt/git/linux-kernel",
            "/home/user/dev/python-tools"
        ]

        model.setAllStrings(repos)

        # Test empty filter returns all
        matches = model.filterStrings("")
        self.assertEqual(len(matches), 5)

        # Test exact prefix matching
        matches = model.filterStrings("/home/user")
        self.assertEqual(len(matches), 3)

        # Test fuzzy matching
        matches = model.filterStrings("git")
        self.assertTrue(any("qgitc" in match for match in matches))
        self.assertTrue(any("linux-kernel" in match for match in matches))

        # Test substring matching
        matches = model.filterStrings("python")
        self.assertTrue(any("python-tools" in match for match in matches))

    def testFuzzyMatchFunction(self):
        """Test the fuzzy match function directly"""
        model = FuzzyStringListModel()

        # Test basic fuzzy matching
        self.assertTrue(model._fuzzyMatch("qgitc", "git"))
        self.assertTrue(model._fuzzyMatch("qgitc", "qgc"))
        self.assertTrue(model._fuzzyMatch("python-tools", "py"))
        self.assertTrue(model._fuzzyMatch("python-tools", "ptls"))

        # Test non-matching
        self.assertFalse(model._fuzzyMatch("qgitc", "xyz"))
        self.assertFalse(model._fuzzyMatch("short", "verylongpattern"))
