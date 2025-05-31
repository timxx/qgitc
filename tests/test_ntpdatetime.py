# -*- coding: utf-8 -*-

import socket
import struct
import unittest
from datetime import datetime, timezone
from unittest import mock

from PySide6.QtCore import QDateTime, QTimeZone

from qgitc import ntpdatetime


def make_ntp_response(unix_timestamp):
    ntp_time = unix_timestamp + ntpdatetime.TIME1970
    data = bytearray(48)
    data[40:44] = struct.pack("!I", ntp_time)
    return bytes(data)


class TestNtpDateTime(unittest.TestCase):

    @mock.patch("qgitc.ntpdatetime.socket.socket")
    def testSuccess(self, mock_socket_class):
        mock_socket = mock.Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        unix_timestamp = 1704067200
        ntp_response = make_ntp_response(unix_timestamp)
        mock_socket.recvfrom.return_value = (
            ntp_response, ("pool.ntp.org", 123))

        result = ntpdatetime.getNtpDateTime()
        self.assertIsInstance(result, QDateTime)
        expected_utc = datetime.fromtimestamp(unix_timestamp, timezone.utc)
        expected_qdt = QDateTime(
            expected_utc.date(), expected_utc.time(), QTimeZone.UTC).toLocalTime()
        self.assertEqual(result.toSecsSinceEpoch(),
                         expected_qdt.toSecsSinceEpoch())

    @mock.patch("qgitc.ntpdatetime.socket.socket")
    def testInvalidResponseLength(self, mock_socket_class):
        mock_socket = mock.Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recvfrom.return_value = (b"short", ("pool.ntp.org", 123))
        self.assertIsNone(ntpdatetime.getNtpDateTime())

    @mock.patch("qgitc.ntpdatetime.socket.socket")
    def testSocketException(self, mock_socket_class):
        mock_socket = mock.Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recvfrom.side_effect = OSError("network error")
        self.assertIsNone(ntpdatetime.getNtpDateTime())

    @mock.patch("qgitc.ntpdatetime.socket.socket")
    def testStructUnpackError(self, mock_socket_class):
        # Provide 48 bytes but with not enough bytes for unpacking
        mock_socket = mock.Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        data = bytearray(48)
        # Remove last 4 bytes to cause struct.unpack error
        mock_socket.recvfrom.return_value = (
            bytes(data[:43]), ("pool.ntp.org", 123))
        self.assertIsNone(ntpdatetime.getNtpDateTime())

    @mock.patch("qgitc.ntpdatetime.socket.socket")
    def testInvalidTimestamp(self, mock_socket_class):
        # Simulate a timestamp before 1970 (negative unix timestamp)
        mock_socket = mock.Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        unix_timestamp = -1000
        ntp_response = make_ntp_response(unix_timestamp)
        mock_socket.recvfrom.return_value = (
            ntp_response, ("pool.ntp.org", 123))
        # Should still return a QDateTime, but with a date before 1970
        result = ntpdatetime.getNtpDateTime()
        self.assertIsInstance(result, QDateTime)

    @mock.patch("qgitc.ntpdatetime.socket.socket")
    def testTimeout(self, mock_socket_class):
        mock_socket = mock.Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recvfrom.side_effect = socket.timeout("timed out")
        self.assertIsNone(ntpdatetime.getNtpDateTime())

    @mock.patch("qgitc.ntpdatetime.socket.socket")
    def testSendtoRaises(self, mock_socket_class):
        mock_socket = mock.Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.sendto.side_effect = OSError("sendto failed")
        self.assertIsNone(ntpdatetime.getNtpDateTime())

    def testEqualLocalTime(self):
        dt = ntpdatetime.getNtpDateTime()
        localDt = QDateTime.currentDateTime()
        # trust that the local time is within 60 seconds of the NTP time
        self.assertTrue(dt is None or (abs(dt.secsTo(localDt)) < 60))
