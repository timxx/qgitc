# -*- coding: utf-8 -*-
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest

from qgitc.aichatwindow import AiChatWidget
from qgitc.llm import AiModelBase
from qgitc.windowtype import WindowType
from tests.base import TestBase
from tests.mocklocalllm import MockLocalLLM


class TestAiChat(TestBase):
    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(WindowType.AiAssistant)
        self.chatWidget: AiChatWidget = self.window.centralWidget()
        self.window.show()

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def testBots(self):
        self.assertEqual(2, self.chatWidget.cbBots.count())

    def testLocalLLM(self):
        for i in range(self.chatWidget.cbBots.count()):
            model: AiModelBase = self.chatWidget.cbBots.itemData(i)
            if model.isLocal():
                self.chatWidget.cbBots.setCurrentIndex(i)
                break
        model = self.chatWidget.currentChatModel()
        self.assertTrue(model.isLocal())

        chatbot = self.chatWidget.messages
        # blockCount will never be 0
        self.assertEqual(1, chatbot.blockCount())

        self.chatWidget.usrInput.edit.setPlainText("Hello")

        with MockLocalLLM(False) as mock:
            spy = QSignalSpy(model.serviceUnavailable)
            QTest.mouseClick(self.chatWidget.btnSend, Qt.LeftButton)
            self.assertEqual(2, chatbot.blockCount())

            self.assertFalse(self.chatWidget.btnSend.isEnabled())
            self.assertFalse(self.chatWidget.btnClear.isEnabled())

            self.wait(10000, lambda: spy.count() == 0)
            self.wait(50)

            self.assertEqual(4, chatbot.blockCount())

            self.assertTrue(self.chatWidget.btnClear.isEnabled())
            QTest.mouseClick(self.chatWidget.btnClear, Qt.LeftButton)
            self.processEvents()

            self.assertEqual(1, chatbot.blockCount())

            self.wait(100)

        with MockLocalLLM(True) as mock:
            spy = QSignalSpy(model.responseAvailable)
            QTest.mouseClick(self.chatWidget.btnSend, Qt.LeftButton)
            self.assertEqual(2, chatbot.blockCount())

            self.wait(10000, lambda: model.isRunning())
            self.wait(50)

            self.assertEqual(4, chatbot.blockCount())
            self.assertEqual("This is a mock response",
                             chatbot.document().lastBlock().text())


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
