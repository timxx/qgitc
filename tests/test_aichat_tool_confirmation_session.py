# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QTest

from qgitc.agentmachine import ToolRequest
from qgitc.agenttools import AgentToolRegistry, ToolType
from qgitc.aichatwindow import AiChatWidget
from qgitc.aitoolconfirmation import ConfirmationStatus
from qgitc.llm import AiChatMessage, AiModelBase, AiRole
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
        self.assertIn("call_ro", self.chatWidget._toolMachine._ignoredToolCallIds)

        # Tool meta cleared as results are synthesized.
        self.assertNotIn("call_ro", self.chatWidget._toolMachine._awaitingToolResults)
        self.assertNotIn("call_w", self.chatWidget._toolMachine._awaitingToolResults)

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
