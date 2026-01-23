# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QTest

from qgitc.agenttoolexecutor import AgentToolResult
from qgitc.agenttools import AgentToolRegistry
from qgitc.aichatwindow import AiChatWidget
from qgitc.llm import AiChatMode, AiModelBase, AiResponse, AiRole
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestAgentMode(TestBase):
    def setUp(self):
        super().setUp()

        # Avoid instantiating real LLM models (which may trigger network/model discovery)
        # during AI window/widget creation.
        self._mockChatModel = MagicMock(spec=AiModelBase)
        self._mockChatModel.name = "Test AI Model"
        self._mockChatModel.modelId = "test-model"
        self._mockChatModel.history = []
        self._mockChatModel.isLocal.return_value = True
        self._mockChatModel.isRunning.return_value = False
        self._mockChatModel.queryAsync = MagicMock()

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

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def _assistant_tool_call_response(self, tool_name: str, arguments: str):
        resp = AiResponse(role=AiRole.Assistant, message="")
        resp.tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": tool_name, "arguments": arguments},
            }
        ]
        return resp

    def test_agent_autorun_readonly_tool_triggers_followup(self):
        # Ensure we are in Agent mode (not strictly required for tool-call handling,
        # but matches real usage).
        self.chatWidget._contextPanel.setMode(AiChatMode.Agent)

        model = self.chatWidget.currentChatModel()

        # Intercept tool execution and follow-up request.
        self.chatWidget._agentExecutor.executeAsync = MagicMock(
            return_value=True)
        model.queryAsync = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock()

        resp = self._assistant_tool_call_response("git_status", "{}")
        self.chatWidget._doMessageReady(model, resp)

        # wait for singleShot
        self.wait(50)

        # Tool should auto-run without showing confirmation.
        self.chatWidget._agentExecutor.executeAsync.assert_called_once()
        self.chatWidget.messages.insertToolConfirmation.assert_not_called()
        self.assertEqual(self.chatWidget._pendingAgentTool, "git_status")

        # Simulate tool finished.
        self.chatWidget._onAgentToolFinished(
            AgentToolResult("git_status", True,
                            "## main\nworking tree clean (no changes).")
        )

        # Auto-run batch should continue automatically via a continuation request.
        self.assertTrue(model.queryAsync.called)
        args, _ = model.queryAsync.call_args
        params = args[0]
        self.assertTrue(getattr(params, "continue_only", False))
        self.assertEqual(getattr(params, "chat_mode", None), AiChatMode.Agent)

    def test_agent_mixed_tools_requires_confirmation_no_autocontinue(self):
        self.chatWidget._contextPanel.setMode(AiChatMode.Agent)

        model = self.chatWidget.currentChatModel()

        self.chatWidget._agentExecutor.executeAsync = MagicMock(
            return_value=True)
        self.chatWidget._continueAgentConversation = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock()

        resp = AiResponse(role=AiRole.Assistant, message="")
        resp.tool_calls = [
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "git_checkout", "arguments": '{"branch":"main"}'},
            },
        ]

        self.chatWidget._doMessageReady(model, resp)

        self.wait(50)

        # git_checkout requires confirmation UI.
        self.chatWidget._agentExecutor.executeAsync.assert_not_called()
        self.chatWidget.messages.insertToolConfirmation.assert_called_once()

        # Because confirmations exist, auto batch should NOT auto-continue.
        self.chatWidget._continueAgentConversation.assert_not_called()

    def test_agent_mixed_confirm_and_autorun_waits_for_all_tool_results(self):
        """Regression: if assistant requests 2 tools, only continue after both results.

        Scenario:
        - tool #1 requires confirmation (WRITE)
        - tool #2 is READ_ONLY (auto-run)
        When the READ_ONLY tool finishes first, we must NOT continue yet.
        """
        self.chatWidget._contextPanel.setMode(AiChatMode.Agent)
        model = self.chatWidget.currentChatModel()

        self.chatWidget._agentExecutor.executeAsync = MagicMock(
            return_value=True)
        self.chatWidget._continueAgentConversation = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock()

        resp = AiResponse(role=AiRole.Assistant, message="")
        resp.tool_calls = [
            {
                "id": "call_confirm",
                "type": "function",
                "function": {"name": "git_checkout", "arguments": '{"branch":"main"}'},
            },
            {
                "id": "call_auto",
                "type": "function",
                "function": {"name": "git_status", "arguments": "{}"},
            },
        ]

        self.chatWidget._doMessageReady(model, resp)
        self.wait(50)

        # READ_ONLY tool should auto-run; WRITE tool should require confirmation.
        self.chatWidget._agentExecutor.executeAsync.assert_called_once_with(
            "git_status", {})
        self.chatWidget.messages.insertToolConfirmation.assert_called_once()

        # Finish the READ_ONLY tool first: must NOT continue yet.
        self.chatWidget._onAgentToolFinished(
            AgentToolResult("git_status", True, "clean")
        )
        self.chatWidget._continueAgentConversation.assert_not_called()

        # Now approve and finish the confirmed tool: continuation should happen.
        self.chatWidget._onToolApproved(
            "git_checkout", {"branch": "main"}, "call_confirm")
        self.chatWidget._onAgentToolFinished(
            AgentToolResult("git_checkout", True, "ok")
        )
        self.assertTrue(self.chatWidget._continueAgentConversation.called)

    def test_agent_tools_include_current_branch(self):
        # Sanity check the registry includes the dedicated current-branch tool,
        # so the LLM can fetch it without listing all branches.

        tools = AgentToolRegistry.openai_tools()
        names = [t.get("function", {}).get("name") for t in tools]
        self.assertIn("git_current_branch", names)
