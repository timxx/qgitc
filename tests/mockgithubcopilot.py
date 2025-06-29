# -*- coding: utf-8 -*-

from enum import Enum, auto
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QByteArray, QCoreApplication, QTimer
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest

from qgitc.githubcopilotlogindialog import GithubCopilotLoginDialog
from qgitc.settings import Settings


class MockGithubCopilotStep(Enum):
    AllSuccess = auto()
    LoginAccessDenied = auto()


GithubCopilotLoginDialogExec = GithubCopilotLoginDialog.exec
MOCK_STEP = MockGithubCopilotStep.AllSuccess


def _mockLoginExec(dialog: GithubCopilotLoginDialog, *args, **kwargs):
    if MOCK_STEP == MockGithubCopilotStep.LoginAccessDenied:
        def _handleExec():
            while dialog.ui.progressBar.value() != 1:
                QCoreApplication.processEvents()
            dialog.close()
        QTimer.singleShot(0, _handleExec)
    GithubCopilotLoginDialogExec(dialog)


def _mockQNetworkAccessManagerPost(mgr: QNetworkAccessManager, request: QNetworkRequest, data: QByteArray):
    url = request.url().toString()
    if url == "https://github.com/login/device/code":
        reply = MagicMock()
        reply.error = MagicMock(return_value=0)
        reply.readAll = MagicMock(return_value=b'{"device_code": "FAKE_DEVICE_CODE", "user_code": "FAKE_USER_CODE", "verification_uri": "https://github.com/login/device"}')
        reply.readyRead = MagicMock()
        reply.readyRead.connect = lambda slot: QTimer.singleShot(0, slot)
        reply.finished = MagicMock()
        reply.finished.connect = lambda slot: QTimer.singleShot(10, slot)
        return reply

    if url == "https://github.com/login/oauth/access_token":
        reply = MagicMock()
        reply.error = MagicMock(return_value=0)
        if MOCK_STEP == MockGithubCopilotStep.LoginAccessDenied:
            reply.readAll = MagicMock(return_value=b'{"error": "access_denied"}')
        else:
            reply.readAll = MagicMock(return_value=b'{"access_token": "FAKE_ACCESS_TOKEN"}')
        reply.readyRead = MagicMock()
        reply.readyRead.connect = lambda slot: QTimer.singleShot(0, slot)
        reply.finished = MagicMock()
        reply.finished.connect = lambda slot: QTimer.singleShot(10, slot)
        return reply

    if url == "https://api.business.githubcopilot.com/chat/completions":
        reply = MagicMock()
        reply.error = MagicMock(return_value=0)
        stream = request.hasRawHeader("Accept") and request.rawHeader("Accept") == b"text/event-stream"
        if stream:
            reply.readAll = MagicMock(return_value=b'''
data: {"choices":[{"delta":{"role":"assistant"}}]}\n
data: {"choices":[{"delta":{"content":"This"}}]}\n
data: {"choices":[{"delta":{"content":" is"}}]}\n
data: {"choices":[{"delta":{"content":" a"}}]}\n
data: {"choices":[{"delta":{"content":" mock"}}]}\n
data: {"choices":[{"delta":{"content":" response"}}]}\n
data: [DONE]\n
''')

        reply.readyRead = MagicMock()
        reply.readyRead.connect = lambda slot: QTimer.singleShot(0, slot)
        reply.finished = MagicMock()
        reply.finished.connect = lambda slot: QTimer.singleShot(10, slot)
        return reply

    assert False, f"Unexpected URL: {url}"


def _mockQNetworkAccessManagerGet(mgr: QNetworkAccessManager, request: QNetworkRequest):
    url = request.url().toString()
    if url == "https://api.github.com/copilot_internal/v2/token":
        reply = MagicMock()
        reply.error = MagicMock(return_value=0)
        reply.readAll = MagicMock(return_value=b'{"token": "tid=fake_tid;ol=fake_ol;exp=9999999999"}')
        reply.readyRead = MagicMock()
        reply.readyRead.connect = lambda slot: QTimer.singleShot(0, slot)
        reply.finished = MagicMock()
        reply.finished.connect = lambda slot: QTimer.singleShot(10, slot)
        return reply

    assert False, f"Unexpected URL: {url}"


class MockGithubCopilot:

    def __init__(self, testCase: TestCase, step: MockGithubCopilotStep = MockGithubCopilotStep.AllSuccess):
        global MOCK_STEP
        MOCK_STEP = step

        self._testCase = testCase
        self._execPatcher = patch.object(
            GithubCopilotLoginDialog, "exec", new=_mockLoginExec)
        self._openUrlPatcher = patch("PySide6.QtGui.QDesktopServices.openUrl")

        self._postPatcher = patch(
            "PySide6.QtNetwork.QNetworkAccessManager.post", new=_mockQNetworkAccessManagerPost)
        self._getPatcher = patch(
            "PySide6.QtNetwork.QNetworkAccessManager.get", new=_mockQNetworkAccessManagerGet)

        self._openUrlMock = None

    def __enter__(self):
        self._execPatcher.start()
        self._openUrlMock = self._openUrlPatcher.start()
        self._postPatcher.start()
        self._getPatcher.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._postPatcher.stop()
        self._getPatcher.stop()
        self._openUrlPatcher.stop()
        self._execPatcher.stop()

    def assertEverythingOK(self):
        assert (self._openUrlMock is not None)

        settings: Settings = QCoreApplication.instance().settings()

        if MOCK_STEP == MockGithubCopilotStep.AllSuccess:
            self._openUrlMock.assert_called_once()
            self._testCase.assertEqual(
                "FAKE_ACCESS_TOKEN", settings.githubCopilotAccessToken())
            self._testCase.assertEqual(
                "tid=fake_tid;ol=fake_ol;exp=9999999999", settings.githubCopilotToken())
        elif MOCK_STEP == MockGithubCopilotStep.LoginAccessDenied:
            self._openUrlMock.assert_called_once()
            self._testCase.assertEqual(
                "", settings.githubCopilotAccessToken())
            self._testCase.assertEqual(
                "", settings.githubCopilotToken())
