# -*- coding: utf-8 -*-

import unittest
from unittest.mock import MagicMock, patch

from qgitc.aichatwidget import AiChatWidget
from qgitc.applicationbase import ApplicationBase
from tests.base import TestBase


class TestActiveRequestModelId(TestBase):

    def doCreateRepo(self):
        pass  # No repo needed

    def _makeWidget(self) -> AiChatWidget:
        widget = AiChatWidget(parent=None, embedded=False, hideHistoryPanel=True)
        # Process any pending timers (e.g. _onDelayInit)
        self.processEvents()
        return widget

    # ------------------------------------------------------------------
    # Test 1: _saveChatHistoryFromLoop uses the snapshot, not model.modelId
    # ------------------------------------------------------------------
    def test_saveChatHistory_uses_activeRequestModelId(self):
        widget = self._makeWidget()

        # Arrange: fake agent loop with messages
        fakeLoop = MagicMock()
        fakeLoop.messages.return_value = [{"role": "user", "content": "hi"}]
        widget._agentLoop = fakeLoop

        # Arrange: fake history
        fakeHistory = MagicMock()
        fakeHistory.historyId = "hist-1"
        widget._historyPanel = MagicMock()
        widget._historyPanel.currentHistory.return_value = fakeHistory

        # Arrange: fake model with modelId = "model-B" (would be wrong if used)
        fakeModel = MagicMock()
        fakeModel.modelId = "model-B"
        fakeModel.name = "model-B"
        widget._contextPanel = MagicMock()
        widget._contextPanel.cbBots = MagicMock()
        widget._contextPanel.cbBots.currentData.return_value = fakeModel

        # Arrange: snapshot was captured at submit time
        widget._activeRequestModelId = "model-A"

        # Arrange: fake store
        fakeStore = MagicMock()
        fakeStore.updateFromMessages.return_value = fakeHistory
        with patch.object(widget, 'currentChatModel', return_value=fakeModel), \
             patch.object(
                 ApplicationBase.instance(),
                 'aiChatHistoryStore',
                 return_value=fakeStore,
             ):
            widget._saveChatHistoryFromLoop()

        _, kwargs = fakeStore.updateFromMessages.call_args
        self.assertEqual(kwargs.get("modelId"), "model-A")
        self.assertNotEqual(kwargs.get("modelId"), "model-B")

    # ------------------------------------------------------------------
    # Test 2: _onAgentFinished clears _activeRequestModelId after saving
    # ------------------------------------------------------------------
    def test_onAgentFinished_clears_activeRequestModelId(self):
        widget = self._makeWidget()
        widget._activeRequestModelId = "model-A"

        with patch.object(widget, '_saveChatHistoryFromLoop'), \
             patch.object(widget, '_updateStatus'), \
             patch.object(widget._chatBot, 'collapseLatestReasoningBlock'):
            widget._onAgentFinished()

        self.assertIsNone(widget._activeRequestModelId)

    # ------------------------------------------------------------------
    # Test 3: _resetAgentLoop clears _activeRequestModelId (stale snapshot)
    # ------------------------------------------------------------------
    def test_resetAgentLoop_clears_activeRequestModelId(self):
        widget = self._makeWidget()
        widget._activeRequestModelId = "model-A"

        # No live agent loop — _resetAgentLoop should still clear the snapshot
        widget._resetAgentLoop()

        self.assertIsNone(widget._activeRequestModelId)


if __name__ == "__main__":
    unittest.main()
