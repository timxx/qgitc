# -*- coding: utf-8 -*-

import sys
import unittest.mock as mock
from io import StringIO

from PySide6.QtWidgets import QMessageBox

from qgitc.excepthandler import ExceptHandler
from tests.base import TestBase


class TestExceptHandler(TestBase):

    def doCreateRepo(self):
        pass

    def test_except_handler_main_thread(self):
        """Test exception handler in main thread shows message box"""
        # Mock QMessageBox.warning at the module level where it's imported
        with mock.patch('PySide6.QtWidgets.QMessageBox.warning') as mock_warning:
            # Create a mock exception
            try:
                raise ValueError("Test exception")
            except ValueError:
                exc_type, exc_value, exc_tb = sys.exc_info()

                # Call the exception handler
                ExceptHandler(exc_type, exc_value, exc_tb)

                # Verify message box was called
                mock_warning.assert_called_once()
                args = mock_warning.call_args[0]
                self.assertIsNone(args[0])  # parent is None
                self.assertEqual(args[1], "Exception occurred!")
                self.assertIn("ValueError: Test exception", args[2])
                self.assertEqual(args[3], QMessageBox.Ok)

    def test_except_handler_other_thread(self):
        """Test exception handler in other thread prints to stderr"""
        # Capture stderr output
        captured_output = StringIO()

        with mock.patch('sys.stderr', captured_output):
            with mock.patch('PySide6.QtCore.QCoreApplication.instance') as mock_app:
                with mock.patch('PySide6.QtCore.QThread.currentThread') as mock_current_thread:
                    # Mock being in a different thread
                    mock_main_thread = mock.Mock()
                    mock_current_thread_obj = mock.Mock()
                    mock_app.return_value.thread.return_value = mock_main_thread
                    mock_current_thread.return_value = mock_current_thread_obj

                    # Make them different objects so == returns False
                    mock_main_thread.__eq__ = lambda self, other: False

                    try:
                        raise RuntimeError("Thread exception")
                    except RuntimeError:
                        exc_type, exc_value, exc_tb = sys.exc_info()

                        # Call the exception handler
                        ExceptHandler(exc_type, exc_value, exc_tb)

                        # Verify output was printed to stderr
                        output = captured_output.getvalue()
                        self.assertIn("RuntimeError: Thread exception", output)
                        self.assertIn("Traceback", output)

    def test_except_handler_logging(self):
        """Test that exception handler logs the exception"""
        with mock.patch('PySide6.QtWidgets.QMessageBox.warning') as mock_warning:
            with mock.patch('qgitc.excepthandler.logger') as mock_logger:
                try:
                    raise ValueError("Log test exception")
                except ValueError:
                    exc_type, exc_value, exc_tb = sys.exc_info()

                    # Call the exception handler
                    ExceptHandler(exc_type, exc_value, exc_tb)

                    # Verify logger.exception was called
                    mock_logger.exception.assert_called_once_with(
                        "exception occurred",
                        exc_info=(exc_type, exc_value, exc_tb)
                    )
