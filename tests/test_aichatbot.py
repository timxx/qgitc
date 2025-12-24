# -*- coding: utf-8 -*-
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from qgitc.aichatbot import AiChatbot
from qgitc.llm import AiResponse, AiRole
from tests.base import TestBase


class TestAiChatbot(TestBase):
    def setUp(self):
        super().setUp()
        self.chatbot = AiChatbot()
        self.chatbot.show()
        QTest.qWaitForWindowExposed(self.chatbot)

    def tearDown(self):
        self.chatbot.close()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def testAppendResponse_SelectionAtEnd_Preserved(self):
        """Test that selection at document end IS preserved (prevents expansion)"""
        # Add initial content
        response1 = AiResponse(role=AiRole.Assistant, message="First message")
        response1.is_delta = False
        self.chatbot.appendResponse(response1)

        # Select to the end of document
        cursor = self.chatbot.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.NextCharacter,
                            QTextCursor.MoveAnchor, 5)
        cursor.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        self.chatbot.setTextCursor(cursor)

        selectionStart = cursor.selectionStart()
        selectionEnd = cursor.selectionEnd()
        selectedText = cursor.selectedText()

        # Verify we ARE at the document end
        docLength = self.chatbot.document().characterCount() - 1
        self.assertEqual(selectionEnd, docLength)

        # Append new content
        response2 = AiResponse(role=AiRole.User, message="Second message")
        response2.is_delta = False
        self.chatbot.appendResponse(response2)

        # Verify selection is preserved (not expanded to include new text)
        newCursor = self.chatbot.textCursor()
        self.assertTrue(newCursor.hasSelection())
        self.assertEqual(selectionStart, newCursor.selectionStart())
        self.assertEqual(selectionEnd, newCursor.selectionEnd())
        self.assertEqual(selectedText, newCursor.selectedText())

    def testAppendResponse_DeltaMessages(self):
        """Test appending delta messages (streaming responses)"""
        # First delta
        response1 = AiResponse(role=AiRole.Assistant, message="Hello ")
        response1.is_delta = True
        response1.first_delta = True
        self.chatbot.appendResponse(response1)

        cursor = self.chatbot.textCursor()
        cursor.movePosition(QTextCursor.End)
        endPos1 = cursor.position()

        # Subsequent deltas
        response2 = AiResponse(role=AiRole.Assistant, message="World")
        response2.is_delta = True
        response2.first_delta = False
        self.chatbot.appendResponse(response2)

        # Verify content is appended
        cursor = self.chatbot.textCursor()
        cursor.movePosition(QTextCursor.End)
        endPos2 = cursor.position()
        self.assertGreater(endPos2, endPos1)

        # Verify text content
        text = self.chatbot.toPlainText()
        self.assertIn("Hello World", text)

    def testAppendResponse_NoSelectionNoCursorChange(self):
        """Test that when there's no selection and cursor is not at end, cursor stays in place"""
        # Add initial content
        response1 = AiResponse(role=AiRole.Assistant, message="First message")
        response1.is_delta = False
        self.chatbot.appendResponse(response1)

        # Position cursor in the middle (no selection)
        cursor = self.chatbot.textCursor()
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.NextCharacter,
                            QTextCursor.MoveAnchor, 5)
        self.chatbot.setTextCursor(cursor)
        cursorPos = cursor.position()
        self.assertFalse(cursor.hasSelection())

        # Append new content
        response2 = AiResponse(role=AiRole.User, message="Second message")
        response2.is_delta = False
        self.chatbot.appendResponse(response2)

        # Cursor should stay at the same position since there was no selection
        # and it wasn't at the end
        actualCursor = self.chatbot.textCursor()
        self.assertEqual(cursorPos, actualCursor.position())
        self.assertFalse(actualCursor.hasSelection())
