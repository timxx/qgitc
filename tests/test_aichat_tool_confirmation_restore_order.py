# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QTest

from qgitc.aichatwindow import AiChatWidget
from qgitc.llm import AiChatMessage, AiModelBase
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestAiChatToolConfirmationRestoreOrder(TestBase):
    def setUp(self):
        super().setUp()

        # Avoid instantiating real LLM models (network/model discovery).
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

    def test_restore_tool_calls_renders_each_tool(self):
        """Restored UI should show each tool call as a separate entry."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append(
                ("append", resp.role.name.lower(), resp.description or ""))

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)

        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {
                        "name": "git_checkout", "arguments": "{}"}},
                    {"id": "c2", "type": "function", "function": {
                        "name": "git_commit", "arguments": "{}"}},
                    {"id": "c3", "type": "function", "function": {
                        "name": "git_add", "arguments": "{}"}},
                ],
            },
            {
                "role": "tool",
                "content": "ok",
                "tool_calls": {"tool_call_id": "c1"},
            },
            {
                "role": "tool",
                "content": "ok",
                "tool_calls": {"tool_call_id": "c2"},
            },
            {
                "role": "tool",
                "content": "ok",
                "tool_calls": {"tool_call_id": "c3"},
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Verify tool call UI entries are present
        tool_run_calls = [
            c for c in calls
            if c[0] == "append" and c[1] == "tool" and "run `" in c[2]
        ]
        self.assertEqual(3, len(tool_run_calls))

    def test_restore_tool_calls_with_results_renders_results(self):
        """Restored tool calls with results should show both call and result."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append(
                ("append", resp.role.name.lower(), resp.message or "",
                 resp.description or ""))

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)

        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "w1", "type": "function", "function": {
                        "name": "git_checkout", "arguments": "{}"}},
                    {"id": "r1", "type": "function", "function": {
                        "name": "git_status", "arguments": "{}"}},
                ],
            },
            {
                "role": "tool",
                "content": "switched to main",
                "tool_calls": {"tool_call_id": "w1"},
            },
            {
                "role": "tool",
                "content": "clean working tree",
                "tool_calls": {"tool_call_id": "r1"},
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Verify tool run previews are shown
        tool_run_calls = [
            c for c in calls
            if c[0] == "append" and c[1] == "tool" and "run `" in c[3]
        ]
        self.assertEqual(2, len(tool_run_calls))

        # Verify tool results are shown
        tool_result_calls = [
            c for c in calls
            if c[0] == "append" and c[1] == "tool" and "run `" not in c[3]
        ]
        self.assertGreaterEqual(len(tool_result_calls), 2)

    def test_agent_loop_messages_set_on_restore(self):
        """Agent loop should have messages set after restoring history."""
        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {
                        "name": "git_status", "arguments": "{}"}},
                ],
            },
            {
                "role": "tool",
                "content": "clean",
                "tool_calls": {"tool_call_id": "c1"},
            },
            {"role": "assistant", "content": "All clean!"},
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=False)

        loop = self.chatWidget._agentLoop
        self.assertIsNotNone(loop)
        # Messages should be converted and set
        agent_messages = loop.messages()
        self.assertGreater(len(agent_messages), 0)
