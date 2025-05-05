# -*- coding: utf-8 -*-

from enum import Enum, auto
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication, QTimer

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


def _mockRequestPost(url: str, **kwargs):
    if url == "https://github.com/login/device/code":
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "device_code": "FAKE_DEVICE_CODE",
            "user_code": "FAKE_USER_CODE",
            "verification_uri": "https://github.com/login/device"
        }
        return response

    if url == "https://github.com/login/oauth/access_token":
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "access_token": "FAKE_ACCESS_TOKEN"
        }
        if MOCK_STEP == MockGithubCopilotStep.LoginAccessDenied:
            response.json.return_value["error"] = "access_denied"
        return response

    if url == "https://api.business.githubcopilot.com/chat/completions":
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
                b'data: {"choices":[{"delta":{"content":" response"}}]}',
                b'data: [DONE]'
            ]

            response.iter_lines = MagicMock(return_value=iter(mock_chunks))

        return response

    assert False, f"Unexpected URL: {url}"


def _mockRequestGet(url: str, **kwargs):
    if url == "https://api.github.com/copilot_internal/v2/token":
        response = MagicMock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "token": "tid=fake_tid;ol=fake_ol;exp=9999999999"
        }
        return response

    assert False, f"Unexpected URL: {url}"


class MockGithubCopilot:

    def __init__(self, testCase: TestCase, step: MockGithubCopilotStep = MockGithubCopilotStep.AllSuccess):
        global MOCK_STEP
        MOCK_STEP = step

        self._testCase = testCase
        self._execPatcher = patch.object(
            GithubCopilotLoginDialog, "exec", new=_mockLoginExec)
        self._openUrlPatcher = patch("PySide6.QtGui.QDesktopServices.openUrl")

        self._postPatcher = patch("requests.post", new=_mockRequestPost)
        self._getPatcher = patch("requests.get", new=_mockRequestGet)

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
