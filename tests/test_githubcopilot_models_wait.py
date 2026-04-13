# -*- coding: utf-8 -*-
"""Tests that GithubCopilot.queryAsync waits for model capabilities to load
before selecting the API endpoint.

In CLI mode (qgitc commit --ai) the GithubCopilot instance is created
immediately before queryAsync() is called.  The QTimer.singleShot(0, …) that
triggers the model-capabilities fetch has therefore not yet fired.  Without
the fix, _shouldUseResponsesApi() always returns False for that first call,
causing requests intended for /responses to be sent to /chat/completions
instead, which results in API errors.
"""

import json
from unittest.mock import patch

from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtTest import QSignalSpy

from qgitc.llm import AiParameters
from qgitc.models.githubcopilot import GithubCopilot
from tests.base import TestBase
from tests.mockqnetworkreply import MockQNetworkReply

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_TOKEN = "tid=fake_tid;ol=fake_ol;exp=9999999999"
FAKE_ACCESS_TOKEN = "FAKE_ACCESS_TOKEN"

_MODELS_WITH_RESPONSES_API = json.dumps({
    "data": [{
        "id": "gpt-responses-model",
        "name": "GPT Responses Model",
        "model_picker_enabled": True,
        "is_chat_default": True,
        "capabilities": {
            "type": "chat",
            "supports": {"streaming": True, "tool_calls": False},
            "limits": {"max_output_tokens": 8192},
        },
        "supported_endpoints": ["/responses"],
    }]
}).encode()

_MODELS_WITHOUT_RESPONSES_API = json.dumps({
    "data": [{
        "id": "gpt-chat-model",
        "name": "GPT Chat Model",
        "model_picker_enabled": True,
        "is_chat_default": True,
        "capabilities": {
            "type": "chat",
            "supports": {"streaming": True, "tool_calls": False},
            "limits": {"max_output_tokens": 4096},
        },
        "supported_endpoints": ["/chat/completions"],
    }]
}).encode()

# Minimal non-streaming JSON response bodies.
_RESPONSES_API_REPLY = json.dumps({
    "id": "resp_test",
    "output": [{
        "type": "message",
        "content": [{"type": "output_text", "text": "ok"}],
    }],
}).encode()

_CHAT_COMPLETIONS_REPLY = json.dumps({
    "choices": [{
        "index": 0,
        "message": {"role": "assistant", "content": "ok"},
        "finish_reason": "stop",
    }]
}).encode()


def _make_get_error_mock(error: QNetworkReply.NetworkError):
    """Return a QNetworkAccessManager.get replacement that always errors."""

    def _mock_get(mgr: QNetworkAccessManager, request: QNetworkRequest):
        url = request.url().toString()
        if "models" in url:
            return MockQNetworkReply(error)
        raise AssertionError(f"Unexpected GET URL: {url}")

    return _mock_get


def _make_get_mock(models_data: bytes):
    """Return a QNetworkAccessManager.get replacement that serves model data."""

    def _mock_get(mgr: QNetworkAccessManager, request: QNetworkRequest):
        url = request.url().toString()
        if "models" in url:
            return MockQNetworkReply(models_data)
        # Should not be called for any other URL in these tests.
        raise AssertionError(f"Unexpected GET URL: {url}")

    return _mock_get


def _make_post_mock(posted_urls: list, reply_data: bytes):
    """Return a QNetworkAccessManager.post replacement that records the URL."""

    def _mock_post(mgr: QNetworkAccessManager, request: QNetworkRequest, data):
        posted_urls.append(request.url().toString())
        return MockQNetworkReply(reply_data)

    return _mock_post


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestGithubCopilotModelsWait(TestBase):

    def doCreateRepo(self):
        return False

    def setUp(self):
        super().setUp()
        # Provide a valid token so the model fetch is attempted.
        settings = self.app.settings()
        settings.setGithubCopilotToken(VALID_TOKEN)
        settings.setGithubCopilotAccessToken(FAKE_ACCESS_TOKEN)
        settings.setDefaultLlmModel("GithubCopilot")

        # Reset class-level model state to simulate a fresh process start.
        GithubCopilot._models = None
        GithubCopilot._capabilities = {}
        GithubCopilot._endPoints = {}
        GithubCopilot._defaultModel = None

    def tearDown(self):
        # Reset class-level model state so other tests are not polluted.
        GithubCopilot._models = None
        GithubCopilot._capabilities = {}
        GithubCopilot._endPoints = {}
        GithubCopilot._defaultModel = None
        super().tearDown()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _runQuery(self, model_id: str, get_mock, posted_urls: list, reply_data: bytes):
        """Create a GithubCopilot instance and immediately call queryAsync
        (before the QTimer.singleShot(0) that starts the model fetch has had
        a chance to fire).  Returns the copilot instance after the query is
        set up."""
        post_mock = _make_post_mock(posted_urls, reply_data)
        with patch("PySide6.QtNetwork.QNetworkAccessManager.get", new=get_mock), \
                patch("PySide6.QtNetwork.QNetworkAccessManager.post", new=post_mock):

            copilot = GithubCopilot(model=model_id)

            # _models is still None here – the QTimer.singleShot(0) has not
            # fired because we have not yet yielded to the event loop.
            self.assertIsNone(GithubCopilot._models)

            params = AiParameters()
            params.prompt = "write a commit message"
            params.stream = False
            params.reasoning = False

            spy = QSignalSpy(copilot.finished)

            copilot.queryAsync(params)

            # Wait for the POST reply to finish so we can clean up safely.
            self.wait(500, lambda: spy.count() == 0)

        return copilot

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_queryUsesResponsesApiAfterModelsLoad(self):
        """When a model advertises /responses, queryAsync must wait for the
        capability data and then POST to the /responses endpoint."""
        posted_urls = []
        get_mock = _make_get_mock(_MODELS_WITH_RESPONSES_API)

        self._runQuery(
            "gpt-responses-model",
            get_mock,
            posted_urls,
            _RESPONSES_API_REPLY,
        )

        self.assertEqual(1, len(posted_urls),
                         f"Expected exactly one POST, got: {posted_urls}")
        self.assertIn("/responses", posted_urls[0],
                      f"Expected POST to /responses endpoint, got: {posted_urls[0]}")

    def test_queryUsesChatCompletionsWithoutResponsesEndpoint(self):
        """When a model does NOT advertise /responses, queryAsync must use
        the /chat/completions endpoint."""
        posted_urls = []
        get_mock = _make_get_mock(_MODELS_WITHOUT_RESPONSES_API)

        self._runQuery(
            "gpt-chat-model",
            get_mock,
            posted_urls,
            _CHAT_COMPLETIONS_REPLY,
        )

        self.assertEqual(1, len(posted_urls),
                         f"Expected exactly one POST, got: {posted_urls}")
        self.assertIn("/chat/completions", posted_urls[0],
                      f"Expected POST to /chat/completions endpoint, got: {posted_urls[0]}")

    def test_queryDoesNotHangWhenModelsFetchFails(self):
        """If /models request fails, queryAsync must not dead-wait for modelsReady."""
        posted_urls = []
        get_mock = _make_get_error_mock(
            QNetworkReply.NetworkError.ConnectionRefusedError)

        self._runQuery(
            "gpt-4.1",
            get_mock,
            posted_urls,
            _CHAT_COMPLETIONS_REPLY,
        )

        self.assertEqual(1, len(posted_urls),
                         f"Expected exactly one POST, got: {posted_urls}")
        self.assertIn("/chat/completions", posted_urls[0],
                      f"Expected POST to /chat/completions endpoint, got: {posted_urls[0]}")

    def test_models_fetch_parses_context_window_limit(self):
        posted_urls = []
        models_data = json.dumps({
            "data": [{
                "id": "gpt-context-model",
                "name": "GPT Context Model",
                "model_picker_enabled": True,
                "is_chat_default": True,
                "capabilities": {
                    "type": "chat",
                    "supports": {"streaming": True, "tool_calls": False},
                    "limits": {
                        "max_output_tokens": 8192,
                        "max_context_window_tokens": 200000,
                    },
                },
                "supported_endpoints": ["/responses"],
            }]
        }).encode()

        get_mock = _make_get_mock(models_data)
        self._runQuery(
            "gpt-context-model",
            get_mock,
            posted_urls,
            _RESPONSES_API_REPLY,
        )

        caps = GithubCopilot._capabilities.get("gpt-context-model")
        self.assertIsNotNone(caps)
        self.assertEqual(200000, caps.context_window)
        self.assertEqual(8192, caps.max_output_tokens)

    def test_models_fetch_fallbacks_for_malformed_limits(self):
        posted_urls = []
        models_data = json.dumps({
            "data": [{
                "id": "gpt-bad-limits-model",
                "name": "GPT Bad Limits Model",
                "model_picker_enabled": True,
                "is_chat_default": True,
                "capabilities": {
                    "type": "chat",
                    "supports": {"streaming": True, "tool_calls": False},
                    "limits": {
                        "max_output_tokens": None,
                        "max_context_window_tokens": "not-a-number",
                    },
                },
                "supported_endpoints": ["/responses"],
            }, {
                "id": "gpt-non-positive-limits-model",
                "name": "GPT Non Positive Limits Model",
                "model_picker_enabled": True,
                "is_chat_default": False,
                "capabilities": {
                    "type": "chat",
                    "supports": {"streaming": True, "tool_calls": False},
                    "limits": {
                        "max_output_tokens": "0",
                        "max_context_window_tokens": -1,
                    },
                },
                "supported_endpoints": ["/responses"],
            }]
        }).encode()

        get_mock = _make_get_mock(models_data)
        self._runQuery(
            "gpt-bad-limits-model",
            get_mock,
            posted_urls,
            _RESPONSES_API_REPLY,
        )

        bad_caps = GithubCopilot._capabilities.get("gpt-bad-limits-model")
        self.assertIsNotNone(bad_caps)
        self.assertEqual(100000, bad_caps.context_window)
        self.assertEqual(4096, bad_caps.max_output_tokens)

        non_positive_caps = GithubCopilot._capabilities.get(
            "gpt-non-positive-limits-model")
        self.assertIsNotNone(non_positive_caps)
        self.assertEqual(100000, non_positive_caps.context_window)
        self.assertEqual(4096, non_positive_caps.max_output_tokens)
