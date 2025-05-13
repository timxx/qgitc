# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

import requests
from PySide6.QtCore import QCoreApplication

from qgitc.settings import Settings

MOCK_SUCCESS = True
LOCAL_LLM_URL = ""


def _mockRequestPost(url: str, **kwargs):
    if not MOCK_SUCCESS:
        raise requests.exceptions.ConnectionError()

    if not url.startswith(LOCAL_LLM_URL):
        return MagicMock(status_code=404, ok=False)

    url_base = url[len(LOCAL_LLM_URL):]
    if url_base == "/chat/completions":
        response = MagicMock()
        response.ok = True
        response.status_code = 200

        if kwargs.get("stream", False):
            mock_chunks = [
                b'data: {"choices":[{"delta":{"role":"assistant"}}]}',
                b'data: {"choices":[{"delta":{"content":"This"}}]}',
                b'data: {"choices":[{"delta":{"content":" is"}}]}',
                b'data: {"choices":[{"delta":{"content":" a"}}]}',
                b'data: {"choices":[{"delta":{"content":" mock"}}]}',
                b'data: {"choices":[{"delta":{"content":" response"}}]}'
            ]

            response.iter_lines = MagicMock(return_value=iter(mock_chunks))

        return response


class MockLocalLLM:

    def __init__(self, mockSuccess: bool = True):
        settings: Settings = QCoreApplication.instance().settings()
        global LOCAL_LLM_URL
        LOCAL_LLM_URL = settings.llmServer()

        global MOCK_SUCCESS
        MOCK_SUCCESS = mockSuccess

        self._postPatcher = patch("requests.post", new=_mockRequestPost)

    def __enter__(self):
        self._postPatcher.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._postPatcher.stop()
