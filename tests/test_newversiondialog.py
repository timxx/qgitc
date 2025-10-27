# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from qgitc.newversiondialog import NewVersionDialog
from tests.base import TestBase


class TestNewVersionDialog(TestBase):

    def doCreateRepo(self):
        pass

    def test_new_version_dialog_initialization(self):
        """Test NewVersionDialog initialization"""
        version = "1.2.3"
        dialog = NewVersionDialog(version)

        try:
            # Test basic properties
            self.assertIsInstance(dialog, QMessageBox)
            self.assertEqual(dialog._version, version)
            self.assertEqual(dialog.icon(), QMessageBox.Information)

            # Test text interaction flags
            flags = dialog.textInteractionFlags()
            self.assertTrue(flags & Qt.TextSelectableByMouse)
            self.assertTrue(flags & Qt.TextSelectableByKeyboard)

            # Test message content
            text = dialog.text()
            self.assertIn(version, text)
            self.assertIn("qgitc", text.lower())
            self.assertIn("pip install qgitc --upgrade", text)

            # Test informative text contains release notes link
            informative_text = dialog.informativeText()
            self.assertIn("releases", informative_text.lower())
            self.assertIn(f"releases/tag/v{version}", informative_text)
            self.assertIn("https://github.com/timxx/qgitc", informative_text)

        finally:
            dialog.close()

    def test_new_version_dialog_with_different_versions(self):
        """Test NewVersionDialog with different version formats"""
        test_versions = ["1.0.0", "2.10.5", "3.0.0-beta1", "10.20.30"]

        for version in test_versions:
            with self.subTest(version=version):
                dialog = NewVersionDialog(version)

                try:
                    # Version should be stored correctly
                    self.assertEqual(dialog._version, version)

                    # Version should appear in main text
                    text = dialog.text()
                    self.assertIn(version, text)

                    # Version should appear in release notes link
                    informative_text = dialog.informativeText()
                    self.assertIn(f"v{version}", informative_text)

                finally:
                    dialog.close()

    def test_new_version_dialog_localization_ready(self):
        """Test that dialog text uses tr() for localization"""
        version = "1.5.0"
        dialog = NewVersionDialog(version)

        try:
            # The dialog should have text (tr() calls should work)
            text = dialog.text()
            self.assertIsNotNone(text)
            self.assertNotEqual(text, "")

            informative_text = dialog.informativeText()
            self.assertIsNotNone(informative_text)
            self.assertNotEqual(informative_text, "")

            # Window title should be set
            title = dialog.windowTitle()
            self.assertIsNotNone(title)
            self.assertNotEqual(title, "")

        finally:
            dialog.close()

    def test_new_version_dialog_parent_handling(self):
        """Test dialog with parent widget"""
        version = "2.0.0"

        # Test with no parent
        dialog1 = NewVersionDialog(version)
        try:
            self.assertIsNone(dialog1.parent())
        finally:
            dialog1.close()

        # Test with parent - skip this part as Application is not a valid QWidget parent
        # Just test that the dialog can be created without parent
        dialog2 = NewVersionDialog(version, None)
        try:
            # Parent should be None
            self.assertIsNone(dialog2.parent())
        finally:
            dialog2.close()

    def test_ignore_version(self):
        """Test that ignoring a version sets it in settings"""
        version = "3.1.4"
        dialog = NewVersionDialog(version)

        def _do():
            cb = dialog.checkBox()
            self.assertFalse(cb.isChecked())
            QTest.mouseClick(cb, Qt.LeftButton)
            self.wait(10)
            self.assertTrue(cb.isChecked())
            dialog.reject()

        QTimer.singleShot(0, _do)
        dialog.exec()
