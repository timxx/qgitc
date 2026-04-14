# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QTest

from qgitc.aichatwindow import AiChatWidget
from qgitc.llm import AiChatMessage, AiModelBase, AiRole
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestAiChatLoadHistory(TestBase):

    def setUp(self):
        super().setUp()

        # Mock chat model to avoid real LLM instantiation.
        self._mockChatModel = MagicMock(spec=AiModelBase)
        self._mockChatModel.name = "Test AI Model"
        self._mockChatModel.modelId = "test-model"
        self._mockChatModel.history = []
        self._mockChatModel.isLocal.return_value = True
        self._mockChatModel.isRunning.return_value = False
        self._mockChatModel.queryAsync = MagicMock()
        self._mockChatModel.models.return_value = [
            ("test-model", "Test Model")]
        self._mockChatModel.supportsToolCalls.return_value = True
        self._mockChatModel.modelKey = "GithubCopilot"

        def _clear():
            self._mockChatModel.history.clear()

        def _addHistory(role, message, **kwargs):
            self._mockChatModel.history.append(
                AiChatMessage(role, message, **kwargs))

        self._mockChatModel.clear.side_effect = _clear
        self._mockChatModel.addHistory.side_effect = _addHistory

        self._modelCreatePatcher = patch(
            'qgitc.llmprovider.AiModelProvider.createSpecificModel',
            return_value=self._mockChatModel,
        )
        self._modelCreatePatcher.start()
        self.addCleanup(self._modelCreatePatcher.stop)

        self.window = self.app.getWindow(WindowType.AiAssistant)
        self.chatWidget: AiChatWidget = self.window.centralWidget()
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)

        # Wait for creating new conversation
        self.wait(
            200, lambda: self.chatWidget._historyPanel.currentHistory() is None)

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_load_simple_history(self):
        """Load a simple user/assistant conversation."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "content": resp.message,
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)

        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        append_calls = [c for c in calls if c["type"] == "append"]
        self.assertEqual(2, len(append_calls))
        self.assertEqual("user", append_calls[0]["role"])
        self.assertEqual("hello", append_calls[0]["content"])
        self.assertEqual("assistant", append_calls[1]["role"])
        self.assertEqual("hi there", append_calls[1]["content"])

    def test_load_history_sets_agent_loop_messages(self):
        """Loading history should set messages on the agent loop."""
        messages = [
            {"role": "user", "content": "show me the status"},
            {"role": "assistant", "content": "Here is the status."},
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=False)

        # Agent loop should have been created and messages set
        loop = self.chatWidget._agentLoop
        self.assertIsNotNone(loop)
        self.assertEqual(2, len(loop.messages()))

    def test_load_history_with_tool_calls_and_results(self):
        """Load history with tool calls and results."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "content": resp.message,
                "description": resp.description or "",
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)

        messages = [
            {"role": "user", "content": "show me the status"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "type": "function", "function": {
                        "name": "git_status", "arguments": "{}"}},
                ],
            },
            {
                "role": "tool",
                "content": "On branch main\nnothing to commit",
                "description": "tool output",
                "tool_calls": {"tool_call_id": "tc1"},
            },
            {"role": "assistant", "content": "The repo is clean."},
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Verify basic structure: user, tool call, tool result, assistant
        append_calls = [c for c in calls if c["type"] == "append"]
        self.assertGreaterEqual(len(append_calls), 3)

        # First should be user message
        self.assertEqual("user", append_calls[0]["role"])
        self.assertEqual("show me the status", append_calls[0]["content"])

    def test_load_history_with_reasoning(self):
        """History with reasoning should show reasoning block."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "content": resp.message,
                "description": resp.description or "",
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)

        messages = [
            {"role": "user", "content": "explain git rebase"},
            {
                "role": "assistant",
                "content": "Git rebase is...",
                "reasoning": "The user is asking about git rebase.",
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Verify reasoning block is present
        reasoning_msgs = [
            c for c in calls
            if c["type"] == "append" and "Reasoning" in c["description"]
        ]
        self.assertEqual(1, len(reasoning_msgs))

    def test_setup_model_names_fallback_to_default_id_for_empty_local_models(self):
        self._mockChatModel.models.return_value = []
        self._mockChatModel.modelId = "fallback-local-model"
        self._mockChatModel.isLocal.return_value = True

        panel = self.chatWidget._contextPanel
        panel.setupModelNames(self._mockChatModel)

        self.assertEqual(1, panel.cbModelNames.count())
        self.assertEqual("fallback-local-model", panel.cbModelNames.itemData(0))

    def test_load_history_addToChatBot_false(self):
        """With addToChatBot=False, no UI updates should occur."""
        self.chatWidget.messages.appendResponse = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock()

        messages = [
            {"role": "user", "content": "show me status"},
            {
                "role": "assistant",
                "content": "I'll check the repo status.",
                "tool_calls": [
                    {
                        "id": "tc1",
                        "type": "function",
                        "function": {"name": "git_status", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "content": "clean",
                "tool_calls": {"tool_call_id": "tc1"},
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=False)

        # No UI updates should occur in this mode.
        self.chatWidget.messages.appendResponse.assert_not_called()
        self.chatWidget.messages.insertToolConfirmation.assert_not_called()

        # But agent loop messages should be set
        loop = self.chatWidget._agentLoop
        self.assertIsNotNone(loop)
        self.assertGreater(len(loop.messages()), 0)

    def test_restore_tool_call_with_assistant_content(self):
        """Restoring history shows assistant text + tool calls in correct shape."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "content": resp.message,
                "description": resp.description or "",
                "collapsed": bool(collapsed),
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock()

        messages = [
            {"role": "user", "content": "please commit"},
            {
                "role": "assistant",
                "content": "I'll commit your changes now.",
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_content_1",
                        "type": "function",
                        "function": {
                            "name": "git_commit",
                            "arguments": '{"message": "test"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": "done",
                "description": "tool output",
                "tool_calls": {"tool_call_id": "tc_content_1"},
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        append_calls = [c for c in calls if c["type"] == "append"]
        self.assertGreaterEqual(len(append_calls), 3)

        self.assertEqual(append_calls[0]["role"], "user")
        self.assertEqual(append_calls[0]["content"], "please commit")

        # The assistant message content should be shown
        assistant_calls = [c for c in append_calls if c["role"] == "assistant"]
        self.assertTrue(
            any(c["content"] == "I'll commit your changes now." for c in assistant_calls)
        )

    def test_unknown_tool_in_history_does_not_crash(self):
        """Unknown tools should not crash when loading history."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "role": resp.role.name.lower(),
                "description": resp.description or "",
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)

        messages = [
            {"role": "user", "content": "run missing tool"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_missing", "type": "function", "function": {
                        "name": "missing_tool", "arguments": "{}"}},
                ],
            },
            {
                "role": "tool",
                "content": "tool output",
                "tool_calls": {"tool_call_id": "tc_missing"},
            },
        ]

        # Should not raise
        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        tool_calls = [
            c for c in calls
            if c.get("role") == "tool" and "run `missing_tool`" in c.get("description", "")
        ]
        self.assertEqual(1, len(tool_calls))
