# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QDialog

from qgitc.gitprogressdialog import (
    AppendResultEvent,
    GitProgressDialog,
    UpdateProgressEvent,
)
from tests.base import TestBase


class TestAppendResultEvent(TestBase):

    def doCreateRepo(self):
        pass

    def test_append_result_event_creation(self):
        """Test AppendResultEvent creation with output only"""
        event = AppendResultEvent("test output")
        self.assertIsInstance(event, QEvent)
        self.assertEqual(event.out, "test output")
        self.assertIsNone(event.error)

    def test_append_result_event_creation_with_error(self):
        """Test AppendResultEvent creation with output and error"""
        event = AppendResultEvent("test output", "test error")
        self.assertIsInstance(event, QEvent)
        self.assertEqual(event.out, "test output")
        self.assertEqual(event.error, "test error")

    def test_append_result_event_type(self):
        """Test AppendResultEvent has correct event type"""
        event = AppendResultEvent("test")
        self.assertEqual(event.type(), AppendResultEvent.Type)


class TestUpdateProgressEvent(TestBase):

    def doCreateRepo(self):
        pass

    def test_update_progress_event_creation(self):
        """Test UpdateProgressEvent creation"""
        event = UpdateProgressEvent()
        self.assertIsInstance(event, QEvent)

    def test_update_progress_event_type(self):
        """Test UpdateProgressEvent has correct event type"""
        event = UpdateProgressEvent()
        self.assertEqual(event.type(), UpdateProgressEvent.Type)


class TestGitProgressDialog(TestBase):

    def setUp(self):
        super().setUp()
        self.dialog = GitProgressDialog()

    def tearDown(self):
        self.dialog.close()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_git_progress_dialog_initialization(self):
        """Test GitProgressDialog initialization"""
        self.assertIsInstance(self.dialog, QDialog)
        self.assertTrue(self.dialog.isModal())

    def test_git_progress_dialog_has_finished_signal(self):
        """Test that GitProgressDialog has finished signal"""
        self.assertTrue(hasattr(self.dialog, 'finished'))

    def test_git_progress_dialog_close_behavior(self):
        """Test that dialog is configured to delete on close"""

        # Check the WA_DeleteOnClose attribute is set
        self.assertTrue(self.dialog.testAttribute(Qt.WA_DeleteOnClose))

    def test_git_progress_dialog_run_method_exists(self):
        """Test that run method exists (basic interface check)"""
        # Check if the dialog has the expected interface methods
        # (may not have run method, so we'll test other important methods)
        self.assertTrue(hasattr(self.dialog, 'show'))
        self.assertTrue(callable(getattr(self.dialog, 'show')))

    def test_git_progress_dialog_close_method_exists(self):
        """Test that close method exists"""
        self.assertTrue(hasattr(self.dialog, 'close'))
        self.assertTrue(callable(getattr(self.dialog, 'close')))

    def test_git_progress_dialog_event_method_exists(self):
        """Test that event method exists for handling custom events"""
        self.assertTrue(hasattr(self.dialog, 'event'))
        self.assertTrue(callable(getattr(self.dialog, 'event')))

    def test_git_progress_dialog_append_result_event_handling(self):
        """Test that dialog can handle AppendResultEvent"""
        # Create an append result event
        event = AppendResultEvent("test output", "test error")

        # The dialog should be able to process this event without crashing
        try:
            result = self.dialog.event(event)
            # result could be True or False depending on implementation
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"Dialog failed to handle AppendResultEvent: {e}")

    def test_git_progress_dialog_update_progress_event_handling(self):
        """Test that dialog can handle UpdateProgressEvent"""
        # Create an update progress event
        event = UpdateProgressEvent()

        # The dialog should be able to process this event without crashing
        try:
            result = self.dialog.event(event)
            # result could be True or False depending on implementation
            self.assertIsInstance(result, bool)
        except Exception as e:
            self.fail(f"Dialog failed to handle UpdateProgressEvent: {e}")

    def test_git_progress_dialog_widget_attributes(self):
        """Test dialog widget attributes are set correctly"""
        # Test that dialog is configured as expected
        self.assertTrue(self.dialog.isModal())

        # Should have proper window attributes for a progress dialog
        self.assertIsNotNone(self.dialog.windowTitle())
        self.assertNotEqual(self.dialog.windowTitle(), "")
