# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QTest

from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.tool_registration import register_builtin_tools
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
        self._mockChatModel.models.return_value = [
            ("test-model", "Test Model")]
        self._mockChatModel.supportsToolCalls.return_value = True
        self._mockChatModel.modelKey = "GithubCopilot"

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

    def test_agent_loop_created_on_request(self):
        """Test that _ensureAgentLoop creates an AgentLoop."""
        self.assertIsNone(self.chatWidget._agentLoop)
        loop = self.chatWidget._ensureAgentLoop()
        self.assertIsNotNone(loop)
        self.assertIsNotNone(self.chatWidget._toolRegistry)

    def test_agent_loop_reset(self):
        """Test that _resetAgentLoop clears the loop."""
        self.chatWidget._ensureAgentLoop()
        self.assertIsNotNone(self.chatWidget._agentLoop)
        self.chatWidget._resetAgentLoop()
        self.assertIsNone(self.chatWidget._agentLoop)
        self.assertIsNone(self.chatWidget._toolRegistry)

    def test_tool_registry_includes_builtin_tools(self):
        """Registry built by the widget should include builtin tools."""
        registry = self.chatWidget._buildToolRegistry()
        # git_status is a builtin tool
        tool = registry.get("git_status")
        self.assertIsNotNone(tool)

    def test_agent_tools_include_current_branch(self):
        # Sanity check the registry includes the dedicated current-branch tool,
        # so the LLM can fetch it without listing all branches.
        registry = ToolRegistry()
        register_builtin_tools(registry)
        names = [t.name for t in registry.list_tools()]
        self.assertIn("git_current_branch", names)
