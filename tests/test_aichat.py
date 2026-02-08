# -*- coding: utf-8 -*-
from unittest.mock import patch

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtTest import QSignalSpy, QTest

from qgitc.aichathistory import AiChatHistory
from qgitc.aichatwindow import AiChatWidget
from qgitc.llm import AiChatMode, AiModelBase
from qgitc.windowtype import WindowType
from tests.base import TestBase
from tests.mocklocalllm import MockLocalLLM


class TestAiChat(TestBase):
    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(WindowType.AiAssistant)
        self.chatWidget: AiChatWidget = self.window.centralWidget()
        self.chatWidget.contextPanel.cbMode.setCurrentIndex(1)
        self.assertTrue(
            self.chatWidget.contextPanel.currentMode() == AiChatMode.Chat)
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)
        # wait for creating new conversation
        self.wait(
            200, lambda: self.chatWidget._historyPanel.currentHistory() is None)

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def testBots(self):
        self.assertEqual(3, self.chatWidget._contextPanel.cbBots.count())

    def testLocalLLM(self):
        self.assertIsNotNone(self.chatWidget._historyPanel.currentHistory())

        for i in range(self.chatWidget._contextPanel.cbBots.count()):
            model: AiModelBase = self.chatWidget._contextPanel.cbBots.itemData(
                i)
            if model.isLocal():
                self.chatWidget._contextPanel.cbBots.setCurrentIndex(i)
                break
        model = self.chatWidget.currentChatModel()
        self.assertTrue(model.isLocal())

        chatbot = self.chatWidget.messages
        initialBlockCount = chatbot.blockCount()
        self.assertGreaterEqual(initialBlockCount, 1)

        self.chatWidget._contextPanel.edit.edit.setPlainText("Hello")

        with MockLocalLLM(False) as mock:
            spy = QSignalSpy(model.serviceUnavailable)
            QTest.mouseClick(
                self.chatWidget._contextPanel.btnSend, Qt.LeftButton)
            self.assertGreater(chatbot.blockCount(), initialBlockCount)

            self.assertFalse(self.chatWidget._contextPanel.btnSend.isVisible())

            self.wait(10000, lambda: spy.count() == 0)
            self.wait(50)

            self.assertGreater(chatbot.blockCount(), initialBlockCount)

            self.wait(100)
            self.chatWidget._clearCurrentChat()
            self.processEvents()

            self.assertGreaterEqual(chatbot.blockCount(), 1)

            self.wait(100)

        self.chatWidget._clearCurrentChat()

        self.chatWidget._contextPanel.edit.edit.setPlainText("Hello")
        with MockLocalLLM(True) as mock:
            spy = QSignalSpy(model.responseAvailable)
            QTest.mouseClick(
                self.chatWidget._contextPanel.btnSend, Qt.LeftButton)
            self.assertGreater(chatbot.blockCount(), initialBlockCount)

            self.wait(10000, lambda: model.isRunning())
            self.wait(50)

            self.assertGreater(chatbot.blockCount(), initialBlockCount)
            self.assertEqual("This is a mock response",
                             chatbot.document().lastBlock().text())

    def test_sendButtonState(self):
        self.assertFalse(self.chatWidget._contextPanel.btnSend.isEnabled())
        self.chatWidget._contextPanel.edit.edit.setPlainText("hello")
        self.assertTrue(self.chatWidget._contextPanel.btnSend.isEnabled())
        curChat = self.chatWidget._historyPanel.currentHistory()
        self.assertIsNotNone(curChat)

        spy = QSignalSpy(self.chatWidget._historyPanel.historySelectionChanged)
        self.chatWidget._historyPanel._searchEdit.setText("should not match")
        self.assertEqual(1, spy.count())

        self.assertFalse(self.chatWidget._contextPanel.btnSend.isEnabled())
        self.assertIsNone(self.chatWidget._historyPanel.currentHistory())

    def test_setCurrentHistory_clears_previous_selection(self):
        panel = self.chatWidget._historyPanel

        panel.insertHistoryAtTop(AiChatHistory(title="Second"), select=False)
        self.processEvents()

        idx0 = panel._filterModel.index(0, 0)
        idx1 = panel._filterModel.index(1, 0)
        self.assertTrue(idx0.isValid())
        self.assertTrue(idx1.isValid())

        hist0 = panel._filterModel.data(idx0, Qt.UserRole)
        hist1 = panel._filterModel.data(idx1, Qt.UserRole)
        self.assertIsNotNone(hist0)
        self.assertIsNotNone(hist1)

        selModel = panel._historyList.selectionModel()
        # Select two items (mimics ExtendedSelection Ctrl+click).
        selModel.setCurrentIndex(
            idx0, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Current)
        selModel.select(idx1, QItemSelectionModel.Select)
        self.processEvents()
        self.assertEqual(len(selModel.selectedIndexes()), 2)

        # Now switch history programmatically; old selections should be cleared.
        panel.setCurrentHistory(hist1.historyId)
        self.processEvents()

        selected = selModel.selectedIndexes()
        self.assertEqual(1, len(selected))
        self.assertEqual(idx1.row(), selected[0].row())
        self.assertEqual(hist1.historyId, panel.currentHistory().historyId)


class TestAiChatFetchModels(TestBase):

    def doCreateRepo(self):
        pass

    @patch("qgitc.models.githubcopilot.GithubCopilot.updateToken")
    def testGitHubCopilot(self, mock_update_token):
        window = self.app.getWindow(WindowType.AiAssistant)
        window.show()
        QTest.qWaitForWindowExposed(window)
        self.wait(50)
        self.assertFalse(mock_update_token.called)
        window.close()
