# -*- coding: utf-8 -*-

import typing
from unittest.mock import MagicMock

from PySide6.QtCore import QByteArray, QTimer
from PySide6.QtNetwork import QNetworkReply


class MockQNetworkReply():

    @typing.overload
    def __init__(self, error: QNetworkReply.NetworkError): ...

    @typing.overload
    def __init__(self, data: bytes): ...

    def __init__(self, *args):
        self.deleteLater = MagicMock()
        self.readyRead = MagicMock()
        self.finished = MagicMock()
        self.finished.connect = lambda slot: QTimer.singleShot(100, slot)
        self.isRunning = MagicMock(return_value=False)
        self.errorOccurred = MagicMock()

        if len(args) == 1 and isinstance(args[0], QNetworkReply.NetworkError):
            self._mockErrorOccurred(args[0])
        elif len(args) == 1 and isinstance(args[0], bytes):
            self._mockSuccess(args[0])
        else:
            raise TypeError("Invalid arguments")

    def _mockErrorOccurred(self, error: QNetworkReply.NetworkError):
        self.error = MagicMock(return_value=error)
        self.errorOccurred.connect = lambda slot: QTimer.singleShot(
            50, lambda: slot(error))

    def _mockSuccess(self, data: bytes):
        self.error = MagicMock(return_value=QNetworkReply.NetworkError.NoError)
        self.readAll = MagicMock(return_value=QByteArray(data))
        self.readyRead.connect = lambda slot: QTimer.singleShot(0, slot)
