# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy

from qgitc.aichatwindow import AiChatWidget
from qgitc.application import Application
from tests.base import TestBase


class TestAiChat(TestBase):
    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(Application.AiAssistant)
        self.chatWidget: AiChatWidget = self.window.centralWidget()
        self.window.show()

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def testBots(self):
        self.assertEqual(2, self.chatWidget.cbBots.count())
        self.assertTrue(self.chatWidget.cbBots.itemData(0).isLocal())
        self.assertFalse(self.chatWidget.cbBots.itemData(1).isLocal())

    def testLocalLLM(self):
        self.chatWidget.cbBots.setCurrentIndex(0)
        model = self.chatWidget.currentChatModel()
        self.assertTrue(model.isLocal())

        chatbot = self.chatWidget.messages
        # blockCount will never be 0
        self.assertEqual(1, chatbot.blockCount())

        self.chatWidget.usrInput.edit.setPlainText("Hello")

        spy = QSignalSpy(model.serviceUnavailable)
        QTest.mouseClick(self.chatWidget.btnSend, Qt.LeftButton)
        self.assertEqual(2, chatbot.blockCount())

        self.assertFalse(self.chatWidget.btnSend.isEnabled())
        self.assertFalse(self.chatWidget.btnClear.isEnabled())

        while spy.count() == 0:
            self.processEvents()

        self.assertEqual(4, chatbot.blockCount())

        self.assertTrue(self.chatWidget.btnClear.isEnabled())
        QTest.mouseClick(self.chatWidget.btnClear, Qt.LeftButton)
        self.processEvents()

        self.assertEqual(1, chatbot.blockCount())

        self.wait(100)
