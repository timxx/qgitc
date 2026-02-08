# -*- coding: utf-8 -*-

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from qgitc.applicationbase import ApplicationBase
from qgitc.models.cursor_internal.utils import CURSOR_API_URL, makeHeaders


class ModelsFetcher(QObject):

    finished = Signal()

    def __init__(self, bearerToken: str, parent=None):
        super().__init__(parent)
        self._bearerToken = bearerToken
        self.models = []

    def start(self):
        url = f"{CURSOR_API_URL}/aiserver.v1.AiService/AvailableModels"
        headers = makeHeaders(self._bearerToken)

        mgr = ApplicationBase.instance().networkManager
        request = QNetworkRequest()
        request.setUrl(url)

        for key, value in headers.items():
            request.setRawHeader(key, value)

        self._reply = mgr.post(request, b'')
        self._reply.finished.connect(self._onFinished)

    def _onFinished(self):
        reply = self._reply
        reply.deleteLater()
        self._reply = None
        if reply.error() != QNetworkReply.NoError:
            return

        data = reply.readAll().data()
        if not data:
            return

        # TODO: decode data and populate self.models
