# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QTest

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

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_onToolRejected_calls_denyTool(self):
        """_onToolRejected should call denyTool on the agent loop."""
        # Create an agent loop
        loop = self.chatWidget._ensureAgentLoop()
        loop.denyTool = MagicMock()

        self.chatWidget.messages.setToolConfirmationStatus = MagicMock()

        self.chatWidget._onToolRejected("git_status", "call_123")

        loop.denyTool.assert_called_once_with("call_123")
        self.chatWidget.messages.setToolConfirmationStatus.assert_called_once_with(
            "call_123", ConfirmationStatus.REJECTED)

    def test_onToolApproved_calls_approveTool(self):
        """_onToolApproved should call approveTool on the agent loop."""
        loop = self.chatWidget._ensureAgentLoop()
        loop.approveTool = MagicMock()

        self.chatWidget._onToolApproved("git_status", {}, "call_456")

        loop.approveTool.assert_called_once_with("call_456")

    def test_new_chat_resets_agent_loop(self):
        """Creating a new conversation should reset the agent loop."""
        # Create an agent loop
        self.chatWidget._ensureAgentLoop()
        self.assertIsNotNone(self.chatWidget._agentLoop)

        # Create new chat
        self.chatWidget.onNewChatRequested()
        self.processEvents()

        # Agent loop should be reset
        self.assertIsNone(self.chatWidget._agentLoop)
        self.assertIsNone(self.chatWidget._toolRegistry)

    def test_onToolRejected_without_loop_does_nothing(self):
        """_onToolRejected should not crash when agent loop is None."""
        self.assertIsNone(self.chatWidget._agentLoop)
        # Should not raise
        self.chatWidget._onToolRejected("git_status", "call_abc")

    def test_onToolApproved_without_loop_does_nothing(self):
        """_onToolApproved should not crash when agent loop is None."""
        self.assertIsNone(self.chatWidget._agentLoop)
        # Should not raise
        self.chatWidget._onToolApproved("git_status", {}, "call_xyz")
