# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt

from qgitc.common import pathsEqual
from qgitc.templatemanager import TemplateManageDialog, loadTemplates
from tests.base import TestBase


class TestTemplateManager(TestBase):
    """Test template manager path comparison fixes"""

    def setUp(self):
        super().setUp()
        self.tempDir = tempfile.mkdtemp()
        self.templateDir = os.path.join(self.tempDir, ".qgitc", "templates")
        os.makedirs(self.templateDir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.tempDir):
            shutil.rmtree(self.tempDir, ignore_errors=True)
        super().tearDown()

    def _createTemplateFile(self, name: str, content: str = "Template content"):
        """Helper to create a template file"""
        path = os.path.join(self.templateDir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return os.path.realpath(path)

    @patch("qgitc.templatemanager.templatesDir")
    @patch("qgitc.templatemanager.gitTemplateFile")
    def testLoadTemplates_PathComparison(self, mock_git_template, mock_templates_dir):
        """Test that loadTemplates correctly identifies duplicate paths with different case/separators"""
        mock_templates_dir.return_value = self.templateDir

        # Create a template file
        template_path = self._createTemplateFile("test.txt")

        # On Windows, test case-insensitive comparison
        if os.name == "nt":
            # Git global points to same file but with different case
            git_path_different_case = template_path.upper()
            # Return different case for global, None for local

            def side_effect(isGlobal):
                return git_path_different_case if isGlobal else None
            mock_git_template.side_effect = side_effect

            # Create a proper context mock
            context = MagicMock()
            context.tr = lambda s: s

            templates = loadTemplates(context)

            # Should only appear once (as git global template, not as qgitc template)
            self.assertEqual(len(templates), 1)
            self.assertTrue(templates[0][0].startswith("[Git Global]"))
        else:
            # On Unix, different case means different file
            mock_git_template.return_value = None
            context = MagicMock()
            context.tr = lambda s: s
            templates = loadTemplates(context)
            self.assertEqual(len(templates), 1)

    @patch("qgitc.templatemanager.templatesDir")
    @patch("qgitc.templatemanager.gitTemplateFile")
    def testLoadTemplates_SeparatorComparison(self, mock_git_template, mock_templates_dir):
        """Test that paths with different separators are treated as equal"""
        mock_templates_dir.return_value = self.templateDir

        # Create a template file
        template_path = self._createTemplateFile("test.txt")

        # Use the alternate separator to exercise normalization on any platform
        alt_sep = "/" if os.sep == "\\" else "\\"
        git_path_backslash = template_path.replace(os.sep, alt_sep)

        def side_effect(isGlobal):
            return git_path_backslash if isGlobal else None
        mock_git_template.side_effect = side_effect

        # Create a proper context mock
        context = MagicMock()
        context.tr = lambda s: s

        templates = loadTemplates(context)

        expected_is_duplicate = pathsEqual(template_path, git_path_backslash)
        if expected_is_duplicate:
            # Should only appear once (as git global template)
            self.assertEqual(len(templates), 1)
            self.assertTrue(templates[0][0].startswith("[Git Global]"))
        else:
            # Should appear as both git global and qgitc template on platforms
            # where the alternate separator is not treated as equivalent.
            self.assertEqual(len(templates), 2)
            self.assertTrue(templates[0][0].startswith("[Git Global]"))
            self.assertTrue(any(name == "test.txt" for name, _ in templates))

    @patch("qgitc.templatemanager.templatesDir")
    @patch("qgitc.templatemanager.gitTemplateFile")
    def testTemplateDialog_SelectTemplateComparison(self, mock_git_template, mock_templates_dir):
        """Test that template dialog correctly identifies selected template with different path case"""
        mock_templates_dir.return_value = self.templateDir
        mock_git_template.return_value = None

        # Create template files
        template1 = self._createTemplateFile("template1.txt", "Content 1")
        template2 = self._createTemplateFile("template2.txt", "Content 2")

        # On Windows, use different case for currentTemplateFile
        if os.name == "nt":
            current_template = template1.upper()
        else:
            current_template = template1

        dialog = TemplateManageDialog(current_template)
        self.processEvents()

        # Find the selected item
        selected_items = dialog._templateList.selectedItems()
        self.assertTrue(len(selected_items) > 0,
                        "A template should be auto-selected")

        # Verify correct template is selected
        selected_path = selected_items[0].data(Qt.ToolTipRole)
        self.assertTrue(pathsEqual(selected_path, template1),
                        f"Selected path {selected_path} should match {template1}")

        dialog.close()
        self.processEvents()

    @patch("qgitc.templatemanager.templatesDir")
    @patch("qgitc.templatemanager.gitTemplateFile")
    def testTemplateDialog_FindItemByPath(self, mock_git_template, mock_templates_dir):
        """Test _findItemByPath with case-insensitive path comparison"""
        mock_templates_dir.return_value = self.templateDir
        mock_git_template.return_value = None

        template_path = self._createTemplateFile("findme.txt")

        dialog = TemplateManageDialog()
        self.processEvents()

        # Test finding with exact path
        item = dialog._findItemByPath(template_path)
        self.assertIsNotNone(item, "Should find item with exact path")

        item_upper = dialog._findItemByPath(template_path.upper())
        self.assertEqual(
            item_upper is not None,
            pathsEqual(template_path.upper(), template_path))

        item_lower = dialog._findItemByPath(template_path.lower())
        self.assertEqual(
            item_lower is not None,
            pathsEqual(template_path.lower(), template_path))

        # Test with alternate separator
        alt_sep = "/" if os.sep == "\\" else "\\"
        path_with_backslash = template_path.replace(os.sep, alt_sep)
        item_backslash = dialog._findItemByPath(path_with_backslash)
        self.assertEqual(
            item_backslash is not None,
            pathsEqual(path_with_backslash, template_path))

        dialog.close()
        self.processEvents()

    @patch("qgitc.templatemanager.templatesDir")
    @patch("qgitc.templatemanager.gitTemplateFile")
    def testTemplateDialog_GitTemplateComparison(self, mock_git_template, mock_templates_dir):
        """Test that git template checkbox correctly identifies current template"""
        mock_templates_dir.return_value = self.templateDir

        template_path = self._createTemplateFile("gittemplate.txt")

        # On Windows, return path with different case
        if os.name == "nt":
            git_path = template_path.upper()
        else:
            git_path = template_path

        mock_git_template.side_effect = lambda isGlobal: None if isGlobal else git_path

        dialog = TemplateManageDialog()
        self.processEvents()

        # Select the template
        item = dialog._findItemByPath(template_path)
        self.assertIsNotNone(item)
        dialog._templateList.setCurrentItem(item)
        self.processEvents()

        # Checkbox should be checked since it matches git config
        self.assertTrue(dialog._chkSetDefault.isChecked(),
                        "Checkbox should be checked for current git template")

        dialog.close()
        self.processEvents()


class TestLoadTemplates(unittest.TestCase):
    """Unit tests for loadTemplates function without Qt dependencies"""

    @patch("qgitc.templatemanager.templatesDir")
    @patch("qgitc.templatemanager.gitTemplateFile")
    @patch("os.path.isdir")
    @patch("os.listdir")
    @patch("os.path.isfile")
    def testLoadTemplates_NoDuplicates(self, mock_isfile, mock_listdir,
                                       mock_isdir, mock_git_template, mock_templates_dir):
        """Test that duplicate paths (different case/separators) are not duplicated"""
        temp_dir = "/tmp/templates"
        mock_templates_dir.return_value = temp_dir
        mock_isdir.return_value = True

        # Template file exists in qgitc templates dir
        mock_listdir.return_value = ["mytemplate.txt"]
        mock_isfile.return_value = True

        template_file_path = f"{temp_dir}/mytemplate.txt"

        with patch("os.path.realpath") as mock_realpath:
            mock_realpath.side_effect = lambda p: p

            # Case 1: Git global points to same file (same case)
            def side_effect(isGlobal):
                return template_file_path if isGlobal else None
            mock_git_template.side_effect = side_effect

            context = MagicMock()
            context.tr = lambda s: s

            templates = loadTemplates(context)

            # Should only have 1 entry (git global, not the qgitc copy)
            self.assertEqual(len(templates), 1)
            self.assertTrue(templates[0][0].startswith("[Git Global]"))
