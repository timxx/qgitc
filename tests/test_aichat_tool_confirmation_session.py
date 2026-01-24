# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QTest

from qgitc.agenttools import ToolType
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

        def _clear():
            self._mockChatModel.history.clear()

        def _addHistory(role, message, description=None, toolCalls=None):
            self._mockChatModel.history.append(
                AiChatMessage(
                    role, message, description=description, toolCalls=toolCalls)
            )

        self._mockChatModel.clear.side_effect = _clear
        self._mockChatModel.addHistory.side_effect = _addHistory

        self._modelFactoryPatcher = patch(
            'qgitc.llmprovider.AiModelFactory.models')
        mock_factory_models = self._modelFactoryPatcher.start()
        self.addCleanup(self._modelFactoryPatcher.stop)
        mock_factory_models.return_value = [lambda parent: self._mockChatModel]

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

    def test_restore_pending_confirmations_and_autorun_queue(self):
        """Restores pending tool confirmations + READ_ONLY auto queue from history."""
        # One READ_ONLY tool (auto-run) + one WRITE tool (needs confirmation)
        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_auto",
                        "type": "function",
                        "function": {"name": "git_status", "arguments": "{}"},
                    },
                    {
                        "id": "call_confirm",
                        "type": "function",
                        "function": {"name": "git_checkout", "arguments": '{"branch":"main"}'},
                    },
                ],
            },
        ]

        # Spy on confirmation insertion.
        self.chatWidget.messages.insertToolConfirmation = MagicMock()

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Pending tool_call_ids are tracked.
        self.assertIn("call_auto", self.chatWidget._awaitingToolResults)
        self.assertIn("call_confirm", self.chatWidget._awaitingToolResults)

        # READ_ONLY tool should be queued for auto-run.
        self.assertTrue(self.chatWidget._autoToolQueue)
        queued = self.chatWidget._autoToolQueue[0]
        self.assertEqual("git_status", queued[0])
        self.assertEqual("call_auto", queued[3])

        # Metadata is restored for both ids.
        self.assertEqual(
            ToolType.READ_ONLY,
            self.chatWidget._toolCallMeta["call_auto"]["tool_type"],
        )
        self.assertEqual(
            "git_checkout",
            self.chatWidget._toolCallMeta["call_confirm"]["tool_name"],
        )

        # Confirmation UI should be restored for the WRITE tool.
        self.chatWidget.messages.insertToolConfirmation.assert_called()
        called_ids = [
            kwargs.get("toolCallId")
            for _, kwargs in self.chatWidget.messages.insertToolConfirmation.call_args_list
        ]
        self.assertIn("call_confirm", called_ids)

        # Auto-run resume is scheduled (we patched the method, so it should be callable).
        self.wait(50)
        self.assertTrue(self.chatWidget._startNextAutoToolIfIdle.called)

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

        self.assertFalse(self.chatWidget._awaitingToolResults)
        self.assertFalse(self.chatWidget._autoToolQueue)
        self.assertFalse(self.chatWidget._autoToolGroups)

    def test_auto_cancel_and_reject_pending_on_new_user_message(self):
        """New user prompt while pending tools exist cancels READ_ONLY and rejects WRITE."""
        model = self.chatWidget.currentChatModel()
        model.clear()

        self.chatWidget._awaitingToolResults = {"call_ro", "call_w"}
        self.chatWidget._toolCallMeta = {
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
        self.chatWidget._autoToolQueue = [("git_status", {}, 1, "call_ro")]
        self.chatWidget._autoToolGroups = {
            1: {"remaining": 1, "outputs": [], "auto_continue": True}}

        self.chatWidget.messages.setToolConfirmationStatus = MagicMock()

        ok = self.chatWidget._autoRejectPendingConfirmationsForNewUserMessage()
        self.assertTrue(ok)

        # Everything is resolved so a new user prompt can be sent.
        self.assertFalse(self.chatWidget._awaitingToolResults)
        self.assertFalse(self.chatWidget._autoToolQueue)
        self.assertFalse(self.chatWidget._autoToolGroups)

        # READ_ONLY gets cancelled/ignored.
        self.assertIn("call_ro", self.chatWidget._ignoredToolCallIds)

        # Tool meta cleared as results are synthesized.
        self.assertNotIn("call_ro", self.chatWidget._toolCallMeta)
        self.assertNotIn("call_w", self.chatWidget._toolCallMeta)

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
