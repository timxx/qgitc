# -*- coding: utf-8 -*-

import tempfile
from pathlib import Path

import openpyxl

from qgitc.conflictlog import ConflictLogXlsx, MergeInfo
from tests.base import TestBase


class TestMergeInfo(TestBase):

    def doCreateRepo(self):
        pass

    def test_merge_info_creation(self):
        """Test MergeInfo object creation"""
        info = MergeInfo("local_branch", "remote_branch", "author_name")
        self.assertEqual(info.local, "local_branch")
        self.assertEqual(info.remote, "remote_branch")
        self.assertEqual(info.author, "author_name")


class TestConflictLogXlsx(TestBase):

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        # Create a temporary Excel file for testing
        self.temp_file = tempfile.NamedTemporaryFile(
            suffix='.xlsx', delete=False)
        self.temp_file.close()

        # Create a basic workbook
        workbook = openpyxl.Workbook()
        workbook.save(self.temp_file.name)
        workbook.close()

    def tearDown(self):
        try:
            Path(self.temp_file.name).unlink(missing_ok=True)
        except:
            pass
        super().tearDown()

    def test_xlsx_initialization(self):
        """Test ConflictLogXlsx initialization"""
        log_xlsx = ConflictLogXlsx(self.temp_file.name)
        self.assertEqual(log_xlsx.logFile, self.temp_file.name)
        self.assertIsNotNone(log_xlsx.book)
        self.assertIsNotNone(log_xlsx.sheet)
        self.assertEqual(log_xlsx._curRow, 6)
        self.assertIsNone(log_xlsx._curFile)

    def test_xlsx_edit(self):
        """Test editing file in xlsx log"""
        log_xlsx = ConflictLogXlsx(self.temp_file.name)
        result = log_xlsx.addFile("test_file.py")
        self.assertTrue(result)
        self.assertEqual(log_xlsx._curFile, "test_file.py")

        log_xlsx.setResolveMethod("test_file.py", "manual")
        cell_value = log_xlsx.sheet["D7"].value  # curRow is 6, so row 7
        self.assertEqual(cell_value, "manual")

        info = MergeInfo("local_branch", "remote_branch", "author_name")
        log_xlsx.setMergeInfo(info)
        self.assertEqual(log_xlsx.sheet["B1"].value, "local_branch")
        self.assertEqual(log_xlsx.sheet["B2"].value, "remote_branch")
        self.assertEqual(log_xlsx.sheet["B3"].value, "author_name")

        log_xlsx.save()

    def test_xlsx_add_commit_branch_a(self):
        """Test adding commit to branch A in xlsx log"""
        log_xlsx = ConflictLogXlsx(self.temp_file.name)
        log_xlsx.addFile("test_file.py")

        commit = {
            "sha1": "abc123def456",
            "subject": "Fix bug in parser",
            "author": "John Doe",
            "date": "2023-01-01",
            "branchA": True
        }

        result = log_xlsx.addCommit(commit)
        self.assertTrue(result)
        # Should be cleared after adding commit
        self.assertIsNone(log_xlsx._curFile)

        # Check that file was added to cell A7 (curRow was 6, incremented to 7)
        self.assertEqual(log_xlsx.sheet["A7"].value, "test_file.py")

        # Check that commit was added to cell B7 (branchA = True)
        expected_msg = 'abc123def456 ("Fix bug in parser", John Doe, 2023-01-01)'
        self.assertEqual(log_xlsx.sheet["B7"].value, expected_msg)

    def test_xlsx_add_commit_branch_b(self):
        """Test adding commit to branch B in xlsx log"""
        log_xlsx = ConflictLogXlsx(self.temp_file.name)
        log_xlsx.addFile("another_file.py")

        commit = {
            "sha1": "def456abc123",
            "subject": "Add new feature",
            "author": "Jane Smith",
            "date": "2023-01-02",
            "branchA": False
        }

        result = log_xlsx.addCommit(commit)
        self.assertTrue(result)

        # Check that commit was added to cell C7 (branchA = False)
        expected_msg = 'def456abc123 ("Add new feature", Jane Smith, 2023-01-02)'
        self.assertEqual(log_xlsx.sheet["C7"].value, expected_msg)

    def test_xlsx_add_multiple_commits_same_cell(self):
        """Test adding multiple commits to same cell appends text"""
        log_xlsx = ConflictLogXlsx(self.temp_file.name)
        log_xlsx.addFile("multi_commit_file.py")

        commit1 = {
            "sha1": "commit1abc",
            "subject": "First commit",
            "author": "Author 1",
            "date": "2023-01-01",
            "branchA": True
        }

        commit2 = {
            "sha1": "commit2def",
            "subject": "Second commit",
            "author": "Author 2",
            "date": "2023-01-02",
            "branchA": True
        }

        log_xlsx.addCommit(commit1)
        # No file added, should append to same cell
        log_xlsx.addCommit(commit2)

        # Check that both commits are in the same cell, separated by newline
        cell_value = log_xlsx.sheet["B7"].value
        self.assertIn(
            'commit1abc ("First commit", Author 1, 2023-01-01)', cell_value)
        self.assertIn(
            'commit2def ("Second commit", Author 2, 2023-01-02)', cell_value)
        self.assertIn("\r\n", cell_value)

    def test_xlsx_add_commit_without_file(self):
        """Test adding commit without setting file first"""
        log_xlsx = ConflictLogXlsx(self.temp_file.name)

        commit = {
            "sha1": "nofileabc123",
            "subject": "Commit without file",
            "author": "Test Author",
            "date": "2023-01-01",
            "branchA": True
        }

        result = log_xlsx.addCommit(commit)
        self.assertTrue(result)

        # File cell should be empty since no file was set
        self.assertIsNone(log_xlsx.sheet["A7"].value)
