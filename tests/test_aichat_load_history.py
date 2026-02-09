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

        # Track tool executor calls
        self._originalExecuteAsync = self.chatWidget._agentExecutor.executeAsync
        self.chatWidget._agentExecutor.executeAsync = MagicMock(
            return_value=True)

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_readonly_tool_without_result_gets_cancelled(self):
        """READ_ONLY tools without results should be cancelled, not auto-run."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "content": resp.message,
                "description": resp.description or "",
            })

        def _insertToolConfirmation(**kwargs):
            calls.append({
                "type": "confirm",
                "tool": kwargs.get("toolName"),
                "id": kwargs.get("toolCallId"),
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

        # History with a READ_ONLY tool (git_status) without result
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
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Verify tool executor was NOT called
        self.chatWidget._agentExecutor.executeAsync.assert_not_called()

        # Verify auto-run queue is empty
        self.assertEqual(0, len(self.chatWidget._autoToolQueue))
        self.assertEqual(0, len(self.chatWidget._autoToolGroups))

        # Verify no pending confirmations
        self.assertEqual(0, len(self.chatWidget._awaitingToolResults))

        # Find the cancelled tool result in calls
        cancelled_calls = [
            c for c in calls
            if c["type"] == "append" and c["role"] == "tool" and "cancelled" in c["description"].lower()
        ]
        self.assertEqual(1, len(cancelled_calls))
        self.assertIn("git_status", cancelled_calls[0]["description"])

        # Verify model history includes cancelled entry
        tool_history = [
            h for h in self._mockChatModel.history if h.role == AiRole.Tool]
        self.assertEqual(1, len(tool_history))
        self.assertIn("cancelled", tool_history[0].message.lower())

    def test_write_tool_without_result_shows_confirmation(self):
        """WRITE/DANGEROUS tools without results should restore confirmation UI."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "description": resp.description or "",
            })

        def _insertToolConfirmation(**kwargs):
            calls.append({
                "type": "confirm",
                "tool": kwargs.get("toolName"),
                "id": kwargs.get("toolCallId"),
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

        # History with a WRITE tool (git_commit) without result
        messages = [
            {"role": "user", "content": "commit the changes"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc2", "type": "function", "function": {
                        "name": "git_commit", "arguments": '{"message": "test"}'}},
                ],
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Verify tool executor was NOT called
        self.chatWidget._agentExecutor.executeAsync.assert_not_called()

        # Verify confirmation was inserted
        confirm_calls = [c for c in calls if c["type"] == "confirm"]
        self.assertEqual(1, len(confirm_calls))
        self.assertEqual("git_commit", confirm_calls[0]["tool"])
        self.assertEqual("tc2", confirm_calls[0]["id"])

        # Verify awaiting tool results
        self.assertIn("tc2", self.chatWidget._awaitingToolResults)
        self.assertIn("tc2", self.chatWidget._toolCallMeta)

        # Verify NO cancelled entry was added
        tool_history = [
            h for h in self._mockChatModel.history if h.role == AiRole.Tool]
        self.assertEqual(0, len(tool_history))

    def test_mixed_tools_without_results(self):
        """Mix of READ_ONLY and WRITE tools: READ_ONLY cancelled, WRITE confirmed."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "content": resp.message,
                "description": resp.description or "",
            })

        def _insertToolConfirmation(**kwargs):
            calls.append({
                "type": "confirm",
                "tool": kwargs.get("toolName"),
                "id": kwargs.get("toolCallId"),
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

        messages = [
            {"role": "user", "content": "status and commit"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "r1", "type": "function", "function": {
                        "name": "git_status", "arguments": "{}"}},
                    {"id": "w1", "type": "function", "function": {
                        "name": "git_commit", "arguments": '{"message": "test"}'}},
                    {"id": "r2", "type": "function", "function": {
                        "name": "git_log", "arguments": "{}"}},
                ],
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # No tool executor calls
        self.chatWidget._agentExecutor.executeAsync.assert_not_called()

        # Check for cancelled READ_ONLY tools
        cancelled_calls = [
            c for c in calls
            if c["type"] == "append" and c["role"] == "tool" and "cancelled" in c["description"].lower()
        ]
        self.assertEqual(2, len(cancelled_calls))
        cancelled_tools = [c["description"] for c in cancelled_calls]
        self.assertTrue(any("git_status" in desc for desc in cancelled_tools))
        self.assertTrue(any("git_log" in desc for desc in cancelled_tools))

        # Check for WRITE tool confirmation
        confirm_calls = [c for c in calls if c["type"] == "confirm"]
        self.assertEqual(1, len(confirm_calls))
        self.assertEqual("git_commit", confirm_calls[0]["tool"])
        self.assertEqual("w1", confirm_calls[0]["id"])

        # Verify only the WRITE tool is awaiting confirmation
        self.assertEqual(1, len(self.chatWidget._awaitingToolResults))
        self.assertIn("w1", self.chatWidget._awaitingToolResults)

    def test_unknown_tool_in_history_uses_fallback_name(self):
        """Unknown tools should not crash and should show fallback tool name."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "role": resp.role.name.lower(),
                "description": resp.description or "",
            })

        def _insertToolConfirmation(**kwargs):
            calls.append({
                "type": "confirm",
                "tool": kwargs.get("toolName"),
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

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
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        tool_calls = [
            c for c in calls
            if c.get("role") == "tool" and "run `missing_tool`" in c.get("description", "")
        ]
        self.assertEqual(1, len(tool_calls))

        confirm_calls = [c for c in calls if c.get("type") == "confirm"]
        self.assertEqual(1, len(confirm_calls))
        self.assertEqual("missing_tool", confirm_calls[0]["tool"])

    def test_tool_calls_reasoning_not_duplicated_per_tool(self):
        """Regression: reasoning should render once for a tool_call batch.

        When restoring history, an assistant message can contain a single
        `tool_calls` list with multiple tools. If the message also carries
        `reasoning`, it   must be appended once (not once per tool call).
        """
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "message": resp.message or "",
                "description": resp.description or "",
            })

        def _insertToolConfirmation(**kwargs):
            calls.append({
                "type": "confirm",
                "tool": kwargs.get("toolName"),
                "id": kwargs.get("toolCallId"),
                "toolDesc": kwargs.get("toolDesc"),
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

        # One assistant message with 2 tool calls and a single reasoning payload.
        messages = [
            {
                "role": "assistant",
                "content": "",
                "reasoning": "some reasoning text",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {
                        "name": "git_checkout", "arguments": "{}"}},
                    {"id": "c2", "type": "function", "function": {
                        "name": "git_commit", "arguments": "{}"}},
                ],
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        reasoning_msgs = [
            c for c in calls
            if c["type"] == "append" and c["role"] == "assistant" and "Reasoning" in (c["description"] or "")
        ]
        self.assertEqual(1, len(reasoning_msgs))

        # Sanity: confirmation UI restored for both WRITE tools.
        confirm_calls = [c for c in calls if c["type"] == "confirm"]
        self.assertEqual(2, len(confirm_calls))

    def test_tool_with_existing_result_not_cancelled(self):
        """Tools that already have results should not be cancelled or re-confirmed."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "content": resp.message,
                "description": resp.description or "",
            })

        def _insertToolConfirmation(**kwargs):
            calls.append({
                "type": "confirm",
                "tool": kwargs.get("toolName"),
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

        # History with READ_ONLY tool that HAS a result
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
                "description": "✓ `git_status` output",
                "tool_calls": {"tool_call_id": "tc1"},
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # No tool executor calls
        self.chatWidget._agentExecutor.executeAsync.assert_not_called()

        # No cancelled entries should be added
        cancelled_calls = [
            c for c in calls
            if c["type"] == "append" and c["role"] == "tool" and "cancelled" in c["description"].lower()
        ]
        self.assertEqual(0, len(cancelled_calls))

        # No confirmations should be inserted
        confirm_calls = [c for c in calls if c["type"] == "confirm"]
        self.assertEqual(0, len(confirm_calls))

        # Verify tool result was displayed
        tool_output_calls = [
            c for c in calls
            if c["type"] == "append" and c["role"] == "tool" and "output" in c["description"]
        ]
        self.assertGreaterEqual(len(tool_output_calls), 1)

    def test_restore_tool_call_with_assistant_content(self):
        """Restoring history shows assistant text + tool calls in correct shape.

        Assistant tool-calls messages should not carry regular `content`.
        Instead, the assistant explanation should be represented as a separate
        assistant message immediately before the tool_calls message.
        """
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
        # Avoid depending on exact tool confirmation internals for this test.
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
            # Tool result exists in history.
            {
                "role": "tool",
                "content": "done",
                "description": "✓ `git_commit`",
                "tool_calls": {"tool_call_id": "tc_content_1"},
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Expect: user message, assistant content message, tool-call UI entry, tool message.
        append_calls = [c for c in calls if c["type"] == "append"]
        self.assertGreaterEqual(len(append_calls), 4)

        self.assertEqual(append_calls[0]["role"], "user")
        self.assertEqual(append_calls[0]["content"], "please commit")

        # The assistant message content should be shown before the tool-call UI entry.
        self.assertEqual(append_calls[1]["role"], "assistant")
        self.assertEqual(append_calls[1]["content"],
                         "I'll commit your changes now.")

        # Ensure the tool result appears somewhere after.
        tool_roles = [c["role"] for c in append_calls]
        self.assertIn("tool", tool_roles)

        # Ensure the model history still contains the assistant content message.
        assistant_history = [
            h for h in self._mockChatModel.history if h.role == AiRole.Assistant
        ]
        self.assertTrue(
            any(h.message == "I'll commit your changes now." for h in assistant_history)
        )

    def test_tool_calls_content_not_appended_when_addToChatBot_false(self):
        """Regression: switching models must not append stray UI messages.

        When restoring history with `addToChatBot=False` (used when the model is
        switched), we must not append assistant `content` from a message that
        also contains `tool_calls`.
        """
        self.chatWidget.messages.appendResponse = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock()

        messages = [
            {"role": "user", "content": "show me status"},
            {
                "role": "assistant",
                "content": "I'll check the repo status.",
                "tool_calls": [
                    {
                        "id": "tc_content_ro_1",
                        "type": "function",
                        "function": {"name": "git_status", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "content": "clean",
                "tool_calls": {"tool_call_id": "tc_content_ro_1"},
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=False)

        # No UI updates should occur in this mode.
        self.chatWidget.messages.appendResponse.assert_not_called()
        self.chatWidget.messages.insertToolConfirmation.assert_not_called()

        # The underlying model history is still reconstructed.
        assistant_history = [
            h for h in self._mockChatModel.history if h.role == AiRole.Assistant
        ]
        self.assertTrue(
            any(h.message == "I'll check the repo status." for h in assistant_history)
        )

    def test_write_tool_cancelled_if_conversation_continued(self):
        """WRITE tools without results should be cancelled if conversation continued after."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "content": resp.message,
                "description": resp.description or "",
            })

        def _insertToolConfirmation(**kwargs):
            calls.append({
                "type": "confirm",
                "tool": kwargs.get("toolName"),
                "id": kwargs.get("toolCallId"),
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

        # History with WRITE tool without result, followed by more conversation
        messages = [
            {"role": "user", "content": "commit the changes"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "type": "function", "function": {
                        "name": "git_commit", "arguments": '{"message": "test"}'}},
                ],
            },
            {"role": "user", "content": "actually, let's do something else"},
            {"role": "assistant", "content": "Sure, what would you like to do?"},
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Verify tool executor was NOT called
        self.chatWidget._agentExecutor.executeAsync.assert_not_called()

        # NO confirmation should be inserted (conversation moved on)
        confirm_calls = [c for c in calls if c["type"] == "confirm"]
        self.assertEqual(0, len(confirm_calls))

        # Verify cancelled entry was added instead
        cancelled_calls = [
            c for c in calls
            if c["type"] == "append" and c["role"] == "tool" and "cancelled" in c["description"].lower()
        ]
        self.assertEqual(1, len(cancelled_calls))
        self.assertIn("git_commit", cancelled_calls[0]["description"])

        # Verify no pending confirmations
        self.assertEqual(0, len(self.chatWidget._awaitingToolResults))

        # Verify model history includes cancelled entry
        tool_history = [
            h for h in self._mockChatModel.history if h.role == AiRole.Tool]
        self.assertEqual(1, len(tool_history))
        self.assertIn("cancelled", tool_history[0].message.lower())

    def test_write_tool_confirmation_only_at_end_of_history(self):
        """WRITE tools without results only show confirmation if they're the last message."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "description": resp.description or "",
            })

        def _insertToolConfirmation(**kwargs):
            calls.append({
                "type": "confirm",
                "tool": kwargs.get("toolName"),
                "id": kwargs.get("toolCallId"),
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

        # Two WRITE tools: first one has more messages after, second one is at the end
        messages = [
            {"role": "user", "content": "first commit"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "type": "function", "function": {
                        "name": "git_commit", "arguments": '{"message": "first"}'}},
                ],
            },
            {"role": "user", "content": "second commit"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc2", "type": "function", "function": {
                        "name": "git_commit", "arguments": '{"message": "second"}'}},
                ],
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Only ONE confirmation should be inserted (for tc2 at the end)
        confirm_calls = [c for c in calls if c["type"] == "confirm"]
        self.assertEqual(1, len(confirm_calls))
        self.assertEqual("git_commit", confirm_calls[0]["tool"])
        self.assertEqual("tc2", confirm_calls[0]["id"])

        # ONE cancelled entry for tc1
        cancelled_calls = [
            c for c in calls
            if c["type"] == "append" and c["role"] == "tool" and "cancelled" in c["description"].lower()
        ]
        self.assertEqual(1, len(cancelled_calls))

        # Only tc2 should be awaiting confirmation
        self.assertEqual(1, len(self.chatWidget._awaitingToolResults))
        self.assertIn("tc2", self.chatWidget._awaitingToolResults)
        self.assertNotIn("tc1", self.chatWidget._awaitingToolResults)

    def test_multiple_write_tools_at_end_all_confirmed(self):
        """Multiple WRITE tools at the end of history should all show confirmations."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append({
                "type": "append",
                "role": resp.role.name.lower(),
                "description": resp.description or "",
            })

        def _insertToolConfirmation(**kwargs):
            calls.append({
                "type": "confirm",
                "tool": kwargs.get("toolName"),
                "id": kwargs.get("toolCallId"),
            })

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

        # Multiple WRITE tools at the end without results
        messages = [
            {"role": "user", "content": "do multiple things"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc1", "type": "function", "function": {
                        "name": "git_add", "arguments": '{"files": ["test.txt"]}'}},
                    {"id": "tc2", "type": "function", "function": {
                        "name": "git_commit", "arguments": '{"message": "test"}'}},
                ],
            },
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Both confirmations should be inserted
        confirm_calls = [c for c in calls if c["type"] == "confirm"]
        self.assertEqual(2, len(confirm_calls))
        confirm_ids = [c["id"] for c in confirm_calls]
        self.assertIn("tc1", confirm_ids)
        self.assertIn("tc2", confirm_ids)

        # No cancelled entries
        cancelled_calls = [
            c for c in calls
            if c["type"] == "append" and c["role"] == "tool" and "cancelled" in c["description"].lower()
        ]
        self.assertEqual(0, len(cancelled_calls))

        # Both should be awaiting confirmation
        self.assertEqual(2, len(self.chatWidget._awaitingToolResults))
        self.assertIn("tc1", self.chatWidget._awaitingToolResults)
        self.assertIn("tc2", self.chatWidget._awaitingToolResults)
