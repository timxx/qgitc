# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QTest

from qgitc.agenttools import ToolType
from qgitc.aichatwindow import AiChatWidget
from qgitc.llm import AiChatMessage, AiModelBase
from qgitc.windowtype import WindowType
from tests.base import TestBase


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
        # Mock insertToolConfirmation to capture what it's called with
        insertedParams = {}

        def _captureInsertToolConfirmation(**kwargs):
            insertedParams.update(kwargs)

        self.chatWidget.messages.appendResponse = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_captureInsertToolConfirmation)

        # Simulate tool machine emitting userConfirmationNeeded
        toolCallId = "call_123"
        toolName = "apply_patch"
        params = {
            "file_path": "test.py",
            "patch": "some patch",
            "explanation": "Fix the bug in the test file"
        }
        toolDesc = "Apply a patch to a file"
        toolType = ToolType.WRITE

        # Call the handler directly (simulating the signal connection)
        self.chatWidget._onToolConfirmationNeeded(
            toolCallId, toolName, params, toolDesc, toolType)

        # Verify insertToolConfirmation was called
        self.chatWidget.messages.insertToolConfirmation.assert_called_once()

        # Verify that explanation was used, not the tool description
        self.assertEqual(insertedParams.get("toolDesc"),
                         "Fix the bug in the test file")
        self.assertNotEqual(insertedParams.get("toolDesc"), toolDesc)

    def test_uses_tool_description_when_no_explanation(self):
        """When params don't contain 'explanation', tool description should be used."""
        insertedParams = {}

        def _captureInsertToolConfirmation(**kwargs):
            insertedParams.update(kwargs)

        self.chatWidget.messages.appendResponse = MagicMock()
        self.chatWidget.messages.insertToolConfirmation = MagicMock(
            side_effect=_captureInsertToolConfirmation)

        toolCallId = "call_456"
        toolName = "git_checkout"
        params = {
            "branch": "main"
        }
        toolDesc = "Switch to a different branch"
        toolType = ToolType.WRITE

        self.chatWidget._onToolConfirmationNeeded(
            toolCallId, toolName, params, toolDesc, toolType)

        self.chatWidget.messages.insertToolConfirmation.assert_called_once()

        # Verify that tool description was used since no explanation exists
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

        toolCallId = "call_789"
        toolName = "run_command"
        params = {
            "command": "ls -la",
            "explanation": "   "  # whitespace only
        }
        toolDesc = "Run a shell command"
        toolType = ToolType.DANGEROUS

        self.chatWidget._onToolConfirmationNeeded(
            toolCallId, toolName, params, toolDesc, toolType)

        self.chatWidget.messages.insertToolConfirmation.assert_called_once()

        # Verify that tool description was used since explanation is empty
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

        toolCallId = "call_abc"
        toolName = "read_file"
        params = {
            "file_path": "test.py",
            "explanation": "  Read the test file  \n"
        }
        toolDesc = "Read contents of a file"
        toolType = ToolType.READ_ONLY

        self.chatWidget._onToolConfirmationNeeded(
            toolCallId, toolName, params, toolDesc, toolType)

        self.chatWidget.messages.insertToolConfirmation.assert_called_once()

        # Verify explanation was used and whitespace was stripped
        self.assertEqual(insertedParams.get("toolDesc"),
                         "Read the test file")
