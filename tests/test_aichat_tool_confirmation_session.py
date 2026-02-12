# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QSignalSpy, QTest

from qgitc.agentmachine import ToolRequest
from qgitc.agenttools import AgentToolRegistry, ToolType
from qgitc.aichatwidget import SKIP_TOOL
from qgitc.aichatwindow import AiChatWidget
from qgitc.aitoolconfirmation import ConfirmationStatus
from qgitc.llm import AiChatMessage, AiModelBase, AiResponse, AiRole
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestAiChatToolConfirmationSession(TestBase):
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

        # Prevent any background auto-run from actually starting tools.
        self.chatWidget._startNextAutoToolIfIdle = MagicMock()

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_restore_does_not_mark_pending_when_results_exist(self):
        """If tool results exist immediately after tool_calls, nothing is pending."""
        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_status",
                        "type": "function",
                        "function": {"name": "git_status", "arguments": "{}"},
                    },
                ],
            },
            {
                "role": "tool",
                "content": "clean",
                "tool_calls": {"tool_call_id": "call_status"},
            },
            {"role": "assistant", "content": "done"},
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=False)

        self.assertFalse(self.chatWidget._toolMachine._awaitingToolResults)
        self.assertFalse(self.chatWidget._toolMachine._toolQueue)
        self.assertFalse(self.chatWidget._toolMachine._autoToolGroups)

    def test_auto_cancel_and_reject_pending_on_new_user_message(self):
        """New user prompt while pending tools exist cancels READ_ONLY and rejects WRITE."""
        model = self.chatWidget.currentChatModel()
        model.clear()

        toolCalls = {
            "call_ro": {
                "tool_name": "git_status",
                "params": {},
                "tool_type": ToolType.READ_ONLY,
                "tool_desc": "status",
            },
            "call_w": {
                "tool_name": "git_checkout",
                "params": {"branch": "main"},
                "tool_type": ToolType.WRITE,
                "tool_desc": "checkout",
            },
        }

        self.chatWidget._toolMachine._awaitingToolResults = {
            "call_ro": AgentToolRegistry.tool_by_name("git_status"),
            "call_w": AgentToolRegistry.tool_by_name("git_checkout")
        }

        self.chatWidget._toolMachine._toolQueue = [
            ToolRequest(toolName="git_status", params={},
                        toolType=ToolType.READ_ONLY, toolCallId="call_ro",
                        groupId=1,
                        source="auto",
                        description="status"),
        ]
        self.chatWidget._toolMachine._autoToolGroups = {
            1: {"remaining": 1, "outputs": [], "auto_continue": True}}

        self.chatWidget.messages.setToolConfirmationStatus = MagicMock()

        self.chatWidget._toolMachine.rejectPendingResults()

        # Everything is resolved so a new user prompt can be sent.
        self.assertFalse(self.chatWidget._toolMachine._awaitingToolResults)
        self.assertFalse(self.chatWidget._toolMachine._toolQueue)
        self.assertFalse(self.chatWidget._toolMachine._autoToolGroups)

        # READ_ONLY gets cancelled/ignored.
        self.assertIn(
            "call_ro", self.chatWidget._toolMachine._ignoredToolCallIds)

        # Tool meta cleared as results are synthesized.
        self.assertNotIn(
            "call_ro", self.chatWidget._toolMachine._awaitingToolResults)
        self.assertNotIn(
            "call_w", self.chatWidget._toolMachine._awaitingToolResults)

        # Confirmation card status is flipped for the WRITE tool.
        self.chatWidget.messages.setToolConfirmationStatus.assert_called_with(
            "call_w", ConfirmationStatus.REJECTED
        )

        # Tool results are recorded with matching tool_call_id.
        tool_msgs = [m for m in model.history if m.role == AiRole.Tool]
        tcids = []
        for m in tool_msgs:
            if isinstance(m.toolCalls, dict) and m.toolCalls.get("tool_call_id"):
                tcids.append(m.toolCalls.get("tool_call_id"))

        self.assertIn("call_ro", tcids)
        self.assertIn("call_w", tcids)

    def test_clear_model_resets_tool_machine_pending_results(self):
        """Switching chat session clears pending tool results to prevent false cancellations.
        
        Regression test: When current chat session has pending tool confirmations
        and user switches to a new chat, clearModel() calls reset() on the tool
        machine to prevent false toolExecutionCancelled signals.
        """
        # Setup: Process tool calls with one requiring confirmation
        toolCalls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "git_status", "arguments": "{}"},
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "git_checkout", "arguments": '{"branch": "main"}'},
            },
        ]

        spyConfirmation = QSignalSpy(
            self.chatWidget._toolMachine.userConfirmationNeeded)
        spyFinished = QSignalSpy(self.chatWidget._agentExecutor.toolFinished)

        response = AiResponse(
            role=AiRole.Assistant,
            tool_calls=toolCalls,
        )
        model = self.chatWidget.currentChatModel()
        self.chatWidget._doMessageReady(model, response)
        self.wait(1000, lambda: spyFinished.count() == 0)
        self.processEvents()

        self.assertEqual(spyConfirmation.count(), 1)

        # Verify we have pending tool confirmations
        self.assertTrue(self.chatWidget._toolMachine.hasPendingResults())
        self.assertEqual(self.chatWidget._toolMachine.getAwaitingCount(), 1)

        self.assertEqual(len(self.chatWidget._toolMachine._inProgress) +
                         len(self.chatWidget._toolMachine._toolQueue), 0)

        # Register a signal spy to ensure no cancellation signals are emitted during reset
        cancelled_signals = []
        self.chatWidget._toolMachine.toolExecutionCancelled.connect(
            lambda *args: cancelled_signals.append(args)
        )

        # User creates a new chat session - this calls clearModel()
        self.chatWidget.onNewChatRequested()
        self.processEvents()

        # Verify tool machine is completely cleared
        self.assertFalse(self.chatWidget._toolMachine.hasPendingResults())
        self.assertEqual(self.chatWidget._toolMachine.getAwaitingCount(), 0)
        self.assertTrue(self.chatWidget._toolMachine.readyToContinue())
        self.assertEqual(len(self.chatWidget._toolMachine._toolQueue), 0)
        self.assertEqual(len(self.chatWidget._toolMachine._inProgress), 0)
        self.assertEqual(len(self.chatWidget._toolMachine._autoToolGroups), 0)

        # No false cancellation signals should be emitted during reset
        self.assertEqual(len(cancelled_signals), 0)

    def test_onToolRejected_adds_tool_response_to_model_history(self):
        """
        Test that _onToolRejected adds a tool response message to the chat model.

        When a user rejects a tool execution:
        1. A Tool role message with SKIP_TOOL content is added to model history
        2. A corresponding AiResponse is processed via _doMessageReady
        3. The tool machine is told to reject the tool execution

        This ensures the model state includes the rejection decision,
        which is required by OpenAI-style chat APIs.
        """
        from qgitc.aichatwidget import SKIP_TOOL

        toolName = "git_status"
        toolCallId = "call_123"

        # Get the current chat model
        model = self.chatWidget.currentChatModel()
        self.assertIsNotNone(model)

        # Initial state: no tool rejection in history
        self.assertEqual(len(model.history), 0)

        # Mock the tool machine to track rejection calls
        mockToolMachine = MagicMock()
        self.chatWidget._toolMachine = mockToolMachine

        # Mock _doMessageReady to track calls
        originalDoMessageReady = self.chatWidget._doMessageReady
        mockDoMessageReady = MagicMock(side_effect=originalDoMessageReady)
        self.chatWidget._doMessageReady = mockDoMessageReady

        # Call the method under test
        self.chatWidget._onToolRejected(toolName, toolCallId)

        # Verify: addHistory was called with the skipped tool message
        self.assertEqual(len(model.history), 1)
        historyEntry = model.history[0]
        self.assertEqual(historyEntry.role, AiRole.Tool)
        self.assertEqual(historyEntry.message, SKIP_TOOL)
        self.assertIn("✗ `git_status` skipped", historyEntry.description)
        self.assertEqual(historyEntry.toolCalls.get(
            "tool_call_id"), toolCallId)

    def test_onToolRejected_calls_doMessageReady_with_response(self):
        """
        Test that _onToolRejected calls _doMessageReady with appropriate AiResponse.

        The response should have:
        - Role: AiRole.Tool
        - Message: SKIP_TOOL constant
        - Description: formatted with tool name and "skipped" indicator
        """
        toolName = "git_checkout"
        toolCallId = "call_456"

        model = self.chatWidget.currentChatModel()
        self.assertIsNotNone(model)

        # Mock _doMessageReady to capture the call
        mockDoMessageReady = MagicMock()
        self.chatWidget._doMessageReady = mockDoMessageReady

        # Call the method under test
        self.chatWidget._onToolRejected(toolName, toolCallId)

        # Verify: _doMessageReady was called once
        mockDoMessageReady.assert_called_once()

        # Extract the arguments
        callArgs = mockDoMessageReady.call_args
        callModel = callArgs[0][0]  # First positional arg: model
        callResponse = callArgs[0][1]  # Second positional arg: response

        # Verify the model passed
        self.assertEqual(callModel, model)

        # Verify the response
        self.assertIsInstance(callResponse, AiResponse)
        self.assertEqual(callResponse.role, AiRole.Tool)
        self.assertEqual(callResponse.message, SKIP_TOOL)
        self.assertIn("✗ `git_checkout` skipped", callResponse.description)

    def test_onToolRejected_calls_tool_machine_reject(self):
        """
        Test that _onToolRejected delegates to tool machine for rejection.

        After ensuring the model state is updated, the tool machine
        must be notified to handle cleanup and state transitions.
        """
        toolName = "git_commit"
        toolCallId = "call_789"

        model = self.chatWidget.currentChatModel()

        # Mock the tool machine
        mockToolMachine = MagicMock()
        self.chatWidget._toolMachine = mockToolMachine

        # Call the method under test
        self.chatWidget._onToolRejected(toolName, toolCallId)

        # Verify: rejectToolExecution was called with correct arguments
        mockToolMachine.rejectToolExecution.assert_called_once_with(
            toolName, toolCallId)

    def test_onToolRejected_description_format(self):
        """
        Test that the skipped tool description follows the expected format.

        The description should be translatable and include:
        - A checkmark (✗) to indicate rejection
        - The tool name in backticks
        - The word "skipped"
        """
        toolName = "test_tool_name"
        toolCallId = "call_test"

        model = self.chatWidget.currentChatModel()

        # Call the method under test
        self.chatWidget._onToolRejected(toolName, toolCallId)

        # Verify: check the description format
        self.assertEqual(len(model.history), 1)
        description = model.history[0].description

        # Should contain the tool name
        self.assertIn(toolName, description)
        # Should indicate it was skipped
        self.assertIn("skipped", description.lower())
        # Should have the rejection marker
        self.assertIn("✗", description)

    def test_onToolRejected_preserves_tool_call_id(self):
        """
        Test that the tool_call_id is properly preserved in the message.

        This is required for OpenAI-style APIs where each tool_call_id
        must have a corresponding tool response message.
        """
        toolName = "some_tool"
        toolCallId = "call_specific_id_12345"

        model = self.chatWidget.currentChatModel()

        # Call the method under test
        self.chatWidget._onToolRejected(toolName, toolCallId)

        # Verify: tool_call_id is in the message metadata
        self.assertEqual(len(model.history), 1)
        toolCalls = model.history[0].toolCalls
        self.assertIsNotNone(toolCalls)
        self.assertEqual(toolCalls.get("tool_call_id"), toolCallId)

    def test_onToolRejected_multiple_rejections(self):
        """
        Test that multiple tool rejections are handled correctly.

        Sequential rejections should each add their own message to the history.
        """
        toolName_a = "tool_a"
        toolCallId_a = "call_a"
        toolName_b = "tool_b"
        toolCallId_b = "call_b"

        model = self.chatWidget.currentChatModel()

        # First rejection
        self.chatWidget._onToolRejected(toolName_a, toolCallId_a)
        self.assertEqual(len(model.history), 1)
        self.assertIn("tool_a", model.history[0].description)

        # Second rejection
        self.chatWidget._onToolRejected(toolName_b, toolCallId_b)
        self.assertEqual(len(model.history), 2)
        self.assertIn("tool_b", model.history[1].description)

        # Verify each has the correct tool_call_id
        self.assertEqual(model.history[0].toolCalls.get(
            "tool_call_id"), toolCallId_a)
        self.assertEqual(model.history[1].toolCalls.get(
            "tool_call_id"), toolCallId_b)
