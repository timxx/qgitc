# -*- coding: utf-8 -*-

import json

from qgitc.llm import AiModelBase, AiRole
from tests.base import TestBase


class _DummyModel(AiModelBase):
    """Minimal concrete AiModelBase for unit testing parsing/accumulation only."""

    @property
    def name(self):
        return "dummy"


class TestLlmMultipleChoices(TestBase):

    def doCreateRepo(self):
        pass

    def testStreamResponse_MultipleChoices_ContentAndToolCalls_AllAddedToHistory(self):
        """LLM may return multiple choices; we should keep them all and add them to history.

        This test covers the case where one choice is normal text and another is tool_calls.
        """

        model = _DummyModel(url="http://example.invalid")

        # Choice 0: normal assistant content, finished with stop.
        payload_stop = {
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "Hello"},
                    "finish_reason": "stop",
                }
            ]
        }

        # Choice 1: tool_calls, finished with tool_calls.
        payload_tool_calls = {
            "choices": [
                {
                    "index": 1,
                    "delta": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "doThing",
                                    "arguments": "{\"x\":1}",
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }

        model.handleStreamResponse(
            b"data: " + json.dumps(payload_stop).encode("utf-8")
        )
        model.handleStreamResponse(
            b"data: " + json.dumps(payload_tool_calls).encode("utf-8")
        )

        # Should have two history entries (one per choice).
        self.assertEqual(len(model.history), 2)

        # First history entry: content-only.
        msg0 = model.history[0]
        self.assertEqual(msg0.role, AiRole.Assistant)
        self.assertEqual(msg0.message, "Hello")
        self.assertTrue(msg0.toolCalls is None or msg0.toolCalls ==
                        [] or msg0.toolCalls == {})

        # Second history entry: tool_calls.
        msg1 = model.history[1]
        self.assertEqual(msg1.role, AiRole.Assistant)
        self.assertTrue(isinstance(msg1.toolCalls, list)
                        or isinstance(msg1.toolCalls, dict))

        # In current implementation, tool calls stored as a list of call dicts.
        if isinstance(msg1.toolCalls, list):
            self.assertEqual(len(msg1.toolCalls), 1)
            self.assertEqual(msg1.toolCalls[0].get("id"), "call_1")
            self.assertEqual(msg1.toolCalls[0].get("type"), "function")
            self.assertEqual(msg1.toolCalls[0].get(
                "function", {}).get("name"), "doThing")

    def testHandleFinished_FlushesRemainingChoices_WithoutDuplicate(self):
        """If a provider never sends a finish_reason, _handleFinished should still add to history.

        But if we already committed a choice on finish_reason, _handleFinished shouldn't
        duplicate it (the simplified implementation pops/clears per-choice caches).
        """

        model = _DummyModel(url="http://example.invalid")

        # Simulate a choice that produced delta content but no finish_reason.
        payload_delta_only = {
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "Partial"},
                    "finish_reason": None,
                }
            ]
        }
        model.handleStreamResponse(
            b"data: " + json.dumps(payload_delta_only).encode("utf-8")
        )

        # Nothing committed yet.
        self.assertEqual(len(model.history), 0)

        # Now simulate network finished -> flush.
        model._handleFinished()
        self.assertEqual(len(model.history), 1)
        self.assertEqual(model.history[0].message, "Partial")

        # Calling _handleFinished again shouldn't duplicate because caches were popped.
        model._handleFinished()
        self.assertEqual(len(model.history), 1)

    def testStreamResponse_StopChunkWithContent_StillEmitsDeltaAndAddsHistory(self):
        """Regression for da063ca (Gemini 3 Flash).

        Some providers may send the final chunk with finish_reason="stop" AND include content.
        We must still emit that content via responseAvailable and commit it to history.
        """

        model = _DummyModel(url="http://example.invalid")

        received = []

        def _on_response(resp):
            received.append(resp)

        model.responseAvailable.connect(_on_response)

        payload_stop_with_content = {
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "Hello"},
                    "finish_reason": "stop",
                }
            ]
        }

        model.handleStreamResponse(
            b"data: " + json.dumps(payload_stop_with_content).encode("utf-8")
        )
        self.processEvents()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].message, "Hello")

        self.assertEqual(len(model.history), 1)
        self.assertEqual(model.history[0].message, "Hello")
