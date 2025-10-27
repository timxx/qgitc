# -*- coding: utf-8 -*-

import json
import unittest.mock as mock

from PySide6.QtCore import QByteArray
from PySide6.QtNetwork import QNetworkReply

from qgitc.versionchecker import VersionChecker
from tests.base import TestBase


class MockNetworkReply(QNetworkReply):
    def __init__(self, data=None, error=QNetworkReply.NoError):
        super().__init__()
        self._data = QByteArray(data.encode() if data else b"")
        self._error = error
        self._pos = 0

    def readAll(self):
        return self._data

    def error(self):
        return self._error

    def deleteLater(self):
        pass


class TestVersionChecker(TestBase):

    def setUp(self):
        super().setUp()
        self.checker = VersionChecker()

    def doCreateRepo(self):
        pass

    def test_initialization(self):
        """Test VersionChecker initialization"""
        checker = VersionChecker()
        self.assertIsInstance(checker, VersionChecker)

    def test_start_check_creates_network_request(self):
        """Test that startCheck creates a network request"""
        with mock.patch('qgitc.versionchecker.QNetworkAccessManager') as mock_manager:
            mock_reply = mock.Mock()
            mock_manager_instance = mock.Mock()
            mock_manager_instance.get.return_value = mock_reply
            mock_manager.return_value = mock_manager_instance

            self.checker.startCheck()

            # Verify manager was created and get was called
            mock_manager.assert_called_once_with(self.checker)
            mock_manager_instance.get.assert_called_once()

            # Verify the request URL
            call_args = mock_manager_instance.get.call_args[0]
            request = call_args[0]
            self.assertEqual(request.url().toString(),
                             "https://pypi.org/pypi/qgitc/json")

    def test_start_check_handles_null_reply(self):
        """Test that startCheck handles null reply gracefully"""
        with mock.patch('qgitc.versionchecker.QNetworkAccessManager') as mock_manager:
            mock_manager_instance = mock.Mock()
            mock_manager_instance.get.return_value = None  # Null reply
            mock_manager.return_value = mock_manager_instance

            # Should not crash
            self.checker.startCheck()

    def test_get_version_valid_json(self):
        """Test _getVersion with valid JSON data"""
        test_data = {
            "info": {
                "version": "1.2.3"
            }
        }
        json_data = json.dumps(test_data).encode()

        version = self.checker._getVersion(json_data)
        self.assertEqual(version, "1.2.3")

    def test_get_version_invalid_json(self):
        """Test _getVersion with invalid JSON data"""
        invalid_json = b"not valid json"

        version = self.checker._getVersion(invalid_json)
        self.assertEqual(version, "")

    def test_get_version_missing_info(self):
        """Test _getVersion with missing info section"""
        test_data = {"other": "data"}
        json_data = json.dumps(test_data).encode()

        version = self.checker._getVersion(json_data)
        self.assertEqual(version, "")

    def test_get_version_missing_version(self):
        """Test _getVersion with missing version in info"""
        test_data = {
            "info": {
                "name": "qgitc"
            }
        }
        json_data = json.dumps(test_data).encode()

        version = self.checker._getVersion(json_data)
        self.assertEqual(version, "")

    def test_get_version_non_string_version(self):
        """Test _getVersion with non-string version"""
        test_data = {
            "info": {
                "version": 123  # Not a string
            }
        }
        json_data = json.dumps(test_data).encode()

        version = self.checker._getVersion(json_data)
        self.assertEqual(version, "")

    def test_on_finished_network_error(self):
        """Test _onFinished with network error"""
        signals_emitted = []

        def track_signal(signal_name):
            def handler(*args):
                signals_emitted.append((signal_name, args))
            return handler

        self.checker.finished.connect(track_signal("finished"))
        self.checker.newVersionAvailable.connect(
            track_signal("newVersionAvailable"))

        # Mock reply with error
        mock_reply = MockNetworkReply(
            error=QNetworkReply.ConnectionRefusedError)

        with mock.patch.object(self.checker, 'sender', return_value=mock_reply):
            self.checker._onFinished()

        # Should emit finished signal but not newVersionAvailable
        self.assertEqual(len(signals_emitted), 1)
        self.assertEqual(signals_emitted[0][0], "finished")

    def test_on_finished_empty_data(self):
        """Test _onFinished with empty response data"""
        signals_emitted = []

        def track_signal(signal_name):
            def handler(*args):
                signals_emitted.append((signal_name, args))
            return handler

        self.checker.finished.connect(track_signal("finished"))
        self.checker.newVersionAvailable.connect(
            track_signal("newVersionAvailable"))

        # Mock reply with empty data
        mock_reply = MockNetworkReply("")

        with mock.patch.object(self.checker, 'sender', return_value=mock_reply):
            self.checker._onFinished()

        # Should emit finished signal but not newVersionAvailable
        self.assertEqual(len(signals_emitted), 1)
        self.assertEqual(signals_emitted[0][0], "finished")

    def test_on_finished_newer_version_available(self):
        """Test _onFinished when a newer version is available"""
        signals_emitted = []

        def track_signal(signal_name):
            def handler(*args):
                signals_emitted.append((signal_name, args))
            return handler

        self.checker.finished.connect(track_signal("finished"))
        self.checker.newVersionAvailable.connect(
            track_signal("newVersionAvailable"))

        # Mock current version to be older
        with mock.patch('qgitc.versionchecker.__version__', "1.0.0"):
            test_data = {
                "info": {
                    "version": "2.0.0"  # Newer version
                }
            }
            response_data = json.dumps(test_data)
            mock_reply = MockNetworkReply(response_data)

            with mock.patch.object(self.checker, 'sender', return_value=mock_reply):
                self.checker._onFinished()

            # Should emit both signals
            self.assertEqual(len(signals_emitted), 2)

            # Check newVersionAvailable signal
            new_version_signal = next(
                s for s in signals_emitted if s[0] == "newVersionAvailable")
            self.assertEqual(new_version_signal[1][0], "2.0.0")

            # Check finished signal
            finished_signal = next(
                s for s in signals_emitted if s[0] == "finished")
            self.assertEqual(len(finished_signal[1]), 0)  # No arguments

    def test_on_finished_same_version(self):
        """Test _onFinished when current version is same as remote"""
        signals_emitted = []

        def track_signal(signal_name):
            def handler(*args):
                signals_emitted.append((signal_name, args))
            return handler

        self.checker.finished.connect(track_signal("finished"))
        self.checker.newVersionAvailable.connect(
            track_signal("newVersionAvailable"))

        # Mock current version to be same as remote
        with mock.patch('qgitc.versionchecker.__version__', "1.5.0"):
            test_data = {
                "info": {
                    "version": "1.5.0"  # Same version
                }
            }
            response_data = json.dumps(test_data)
            mock_reply = MockNetworkReply(response_data)

            with mock.patch.object(self.checker, 'sender', return_value=mock_reply):
                self.checker._onFinished()

            # Should only emit finished signal
            self.assertEqual(len(signals_emitted), 1)
            self.assertEqual(signals_emitted[0][0], "finished")

    def test_on_finished_older_remote_version(self):
        """Test _onFinished when remote version is older than current"""
        signals_emitted = []

        def track_signal(signal_name):
            def handler(*args):
                signals_emitted.append((signal_name, args))
            return handler

        self.checker.finished.connect(track_signal("finished"))
        self.checker.newVersionAvailable.connect(
            track_signal("newVersionAvailable"))

        # Mock current version to be newer than remote
        with mock.patch('qgitc.versionchecker.__version__', "2.0.0"):
            test_data = {
                "info": {
                    "version": "1.0.0"  # Older version
                }
            }
            response_data = json.dumps(test_data)
            mock_reply = MockNetworkReply(response_data)

            with mock.patch.object(self.checker, 'sender', return_value=mock_reply):
                self.checker._onFinished()

            # Should only emit finished signal
            self.assertEqual(len(signals_emitted), 1)
            self.assertEqual(signals_emitted[0][0], "finished")

    def test_on_finished_invalid_version_format(self):
        """Test _onFinished with invalid version format"""
        signals_emitted = []

        def track_signal(signal_name):
            def handler(*args):
                signals_emitted.append((signal_name, args))
            return handler

        self.checker.finished.connect(track_signal("finished"))
        self.checker.newVersionAvailable.connect(
            track_signal("newVersionAvailable"))

        test_data = {
            "info": {
                "version": "invalid.version.format"
            }
        }
        response_data = json.dumps(test_data)
        mock_reply = MockNetworkReply(response_data)

        with mock.patch.object(self.checker, 'sender', return_value=mock_reply):
            with mock.patch('qgitc.versionchecker.logger') as mock_logger:
                self.checker._onFinished()

                # Should log the exception
                mock_logger.exception.assert_called_once()

        # Should only emit finished signal (due to exception handling)
        self.assertEqual(len(signals_emitted), 1)
        self.assertEqual(signals_emitted[0][0], "finished")
