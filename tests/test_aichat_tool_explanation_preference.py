# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QTest

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agenttools import ToolType
from qgitc.aichatwindow import AiChatWidget
from qgitc.llm import AiChatMessage, AiModelBase
from qgitc.windowtype import WindowType
from tests.base import TestBase


class _MockTool(Tool):
    """A mock tool for testing permission confirmations."""

    def __init__(self, name, description, read_only=False, destructive=False):
        self.name = name
        self.description = description
        self._read_only = read_only
        self._destructive = destructive

    def is_read_only(self):
        return self._read_only

    def is_destructive(self):
        return self._destructive

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def input_schema(self):
        return {"type": "object", "properties": {}}


class TestAiChatToolExplanationPreference(TestBase):
    """Test that tool confirmation UI prefers explanation over tool description."""

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

    def test_prefers_explanation_over_tool_description(self):
        """When params contain 'explanation', it should be used instead of tool description."""
        insertedParams = {}

        def _captureInsertToolConfirmation(**kwargs):
            insertedParams.update(kwargs)

        self.chatWidget.messages.appendResponse = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_captureInsertToolConfirmation)

        # Build tool registry so _makeUiToolCallResponse can find tools
        self.chatWidget._ensureAgentLoop()

        tool = _MockTool("apply_patch", "Apply a patch to a file")
        inputData = {
            "file_path": "test.py",
            "patch": "some patch",
            "explanation": "Fix the bug in the test file"
        }

        self.chatWidget._onAgentPermissionRequired(
            "call_123", tool, inputData)

        self.chatWidget.messages.insertToolConfirmation.assert_called_once()
        self.assertEqual(insertedParams.get("toolDesc"),
                         "Fix the bug in the test file")

    def test_uses_tool_description_when_no_explanation(self):
        """When params don't contain 'explanation', tool description should be used."""
        insertedParams = {}

        def _captureInsertToolConfirmation(**kwargs):
            insertedParams.update(kwargs)

        self.chatWidget.messages.appendResponse = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_captureInsertToolConfirmation)

        self.chatWidget._ensureAgentLoop()

        tool = _MockTool("git_checkout", "Switch to a different branch")
        inputData = {"branch": "main"}

        self.chatWidget._onAgentPermissionRequired(
            "call_456", tool, inputData)

        self.chatWidget.messages.insertToolConfirmation.assert_called_once()
        self.assertEqual(insertedParams.get("toolDesc"),
                         "Switch to a different branch")

    def test_uses_tool_description_when_explanation_empty(self):
        """When explanation is empty or whitespace, tool description should be used."""
        insertedParams = {}

        def _captureInsertToolConfirmation(**kwargs):
            insertedParams.update(kwargs)

        self.chatWidget.messages.appendResponse = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_captureInsertToolConfirmation)

        self.chatWidget._ensureAgentLoop()

        tool = _MockTool("run_command", "Run a shell command", destructive=True)
        inputData = {
            "command": "ls -la",
            "explanation": "   "  # whitespace only
        }

        self.chatWidget._onAgentPermissionRequired(
            "call_789", tool, inputData)

        self.chatWidget.messages.insertToolConfirmation.assert_called_once()
        self.assertEqual(insertedParams.get("toolDesc"),
                         "Run a shell command")

    def test_explanation_strips_whitespace(self):
        """Explanation should be stripped of leading/trailing whitespace."""
        insertedParams = {}

        def _captureInsertToolConfirmation(**kwargs):
            insertedParams.update(kwargs)

        self.chatWidget.messages.appendResponse = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_captureInsertToolConfirmation)

        self.chatWidget._ensureAgentLoop()

        tool = _MockTool("read_file", "Read contents of a file", read_only=True)
        inputData = {
            "file_path": "test.py",
            "explanation": "  Read the test file  \n"
        }

        self.chatWidget._onAgentPermissionRequired(
            "call_abc", tool, inputData)

        self.chatWidget.messages.insertToolConfirmation.assert_called_once()
        self.assertEqual(insertedParams.get("toolDesc"),
                         "Read the test file")
