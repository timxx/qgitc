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

        def _clear():
            self._mockChatModel.history.clear()

        def _addHistory(role, message, **kwargs):
            self._mockChatModel.history.append(
                AiChatMessage(role, message, **kwargs))

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

    def test_restore_interleaves_run_and_confirmation_multiple_write_calls(self):
        """Restored UI should show run(tool1)->confirm, run(tool2)->confirm, ..."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            # Record role and description to distinguish tool run previews.
            calls.append(
                ("append", resp.role.name.lower(), resp.description or ""))

        def _insertToolConfirmation(**kwargs):
            calls.append(("confirm", kwargs.get(
                "toolName"), kwargs.get("toolCallId")))

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

        # Persisted history contains assistant tool_calls + tool results (with tool_call_id).
        # UI-only tool run previews are no longer stored in model history.
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
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # We should see an interleaving pattern: append(tool run), confirm, append, confirm, ...
        # Filter down to only appends of tool run previews and confirm insertions.
        simplified = []
        for c in calls:
            if c[0] == "append" and c[1] == "tool" and "run `" in c[2]:
                simplified.append(("run", c[2]))
            elif c[0] == "confirm":
                simplified.append(("confirm", c[1], c[2]))

        self.assertGreaterEqual(len(simplified), 6)
        self.assertEqual("run", simplified[0][0])
        self.assertEqual("confirm", simplified[1][0])
        self.assertEqual("run", simplified[2][0])
        self.assertEqual("confirm", simplified[3][0])
        self.assertEqual("run", simplified[4][0])
        self.assertEqual("confirm", simplified[5][0])

        # Confirmations should preserve tool_call_id order.
        confirm_ids = [x[2] for x in simplified if x[0] == "confirm"]
        self.assertEqual(["c1", "c2", "c3"], confirm_ids[:3])

    def test_restore_confirmation_after_write_before_read_run(self):
        """If history has write-run, read-run, then tool_calls, confirmation must follow write-run."""
        calls = []

        def _appendResponse(resp, collapsed=False):
            calls.append(
                ("append", resp.role.name.lower(), resp.description or ""))

        def _insertToolConfirmation(**kwargs):
            calls.append(("confirm", kwargs.get(
                "toolName"), kwargs.get("toolCallId")))

        self.chatWidget.messages.appendResponse = MagicMock(
            side_effect=_appendResponse)
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_insertToolConfirmation)

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
        ]

        self.chatWidget._loadMessagesFromHistory(messages, addToChatBot=True)

        # Extract indices of events.
        run_checkout_idx = None
        run_status_idx = None
        confirm_checkout_idx = None
        for idx, c in enumerate(calls):
            if c[0] == "append" and c[1] == "tool" and "run `git_checkout`" in c[2]:
                run_checkout_idx = idx
            if c[0] == "append" and c[1] == "tool" and "run `git_status`" in c[2]:
                run_status_idx = idx
            if c[0] == "confirm" and c[2] == "w1":
                confirm_checkout_idx = idx

        self.assertIsNotNone(run_checkout_idx)
        self.assertIsNotNone(run_status_idx)
        self.assertIsNotNone(confirm_checkout_idx)

        # Confirmation should come after the write-run and before the read-run.
        self.assertLess(run_checkout_idx, confirm_checkout_idx)
        self.assertLess(confirm_checkout_idx, run_status_idx)
