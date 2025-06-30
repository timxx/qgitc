# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtCore import QByteArray, QCoreApplication
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from qgitc.settings import Settings
from tests.mockqnetworkreply import MockQNetworkReply

MOCK_SUCCESS = True
LOCAL_LLM_URL = ""


def _mockQNetworkAccessManagerPost(mgr: QNetworkAccessManager, request: QNetworkRequest, data: QByteArray):
    if not MOCK_SUCCESS:
        return MockQNetworkReply(QNetworkReply.ConnectionRefusedError)

    url = request.url().toString()
    if not url.startswith(LOCAL_LLM_URL):
        return MagicMock(status_code=404, ok=False)

    url_base = url[len(LOCAL_LLM_URL):]
    if url_base == "/chat/completions":
        data = b'''data: {"choices":[{"delta":{"role":"assistant"}}]}\n
data: {"choices":[{"delta":{"content":"This"}}]}\n
data: {"choices":[{"delta":{"content":" is"}}]}\n
data: {"choices":[{"delta":{"content":" a"}}]}\n
data: {"choices":[{"delta":{"content":" mock"}}]}\n
data: {"choices":[{"delta":{"content":" response"}}]}\n
data: [DONE]\n
'''
        return MockQNetworkReply(data)


class MockLocalLLM:

    def __init__(self, mockSuccess: bool = True):
        settings: Settings = QCoreApplication.instance().settings()
        global LOCAL_LLM_URL
        LOCAL_LLM_URL = settings.localLlmServer()

        global MOCK_SUCCESS
        MOCK_SUCCESS = mockSuccess

        self._postPatcher = patch(
            "PySide6.QtNetwork.QNetworkAccessManager.post", new=_mockQNetworkAccessManagerPost)

    def __enter__(self):
        self._postPatcher.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._postPatcher.stop()
