# -*- coding: utf-8 -*-
from PySide6.QtCore import QPoint
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from qgitc.agenttools import ToolType
from qgitc.aichatbot import AiChatbot
from qgitc.aitoolconfirmation import ButtonType
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

    def testGetConfirmDataAtPosition_WithScrolling(self):
        """Test that _getConfirmDataAtPosition works correctly when document is scrolled"""
        # Add a lot of initial content to enable scrolling
        for i in range(30):
            response = AiResponse(
                role=AiRole.Assistant, message=f"Line {i}\n" * 5)
            response.is_delta = False
            self.chatbot.appendResponse(response)

        # Insert a tool confirmation at the end
        toolName = "test_tool"
        params = {"param1": "value1"}
        toolDesc = "Test tool description"
        toolType = ToolType.READ_ONLY
        toolCallId = "test_call_123"

        pos = self.chatbot.insertToolConfirmation(
            toolName, params, toolDesc, toolType, toolCallId)

        # Ensure the chatbot is visible and sized
        self.chatbot.resize(400, 300)
        QTest.qWait(100)  # Wait for layout

        # Scroll to the top (making contentOffset non-zero when we later look at the bottom)
        cursor = self.chatbot.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.chatbot.setTextCursor(cursor)
        self.chatbot.ensureCursorVisible()
        QTest.qWait(50)

        # Now scroll to the bottom where the confirmation is
        cursor.movePosition(QTextCursor.End)
        self.chatbot.setTextCursor(cursor)
        self.chatbot.ensureCursorVisible()
        QTest.qWait(50)

        # Find the confirmation block
        doc = self.chatbot.document()
        confirmBlock = doc.findBlock(pos)
        self.assertTrue(confirmBlock.isValid())

        # Get the block's bounding rect in viewport coordinates
        blockGeometry = self.chatbot.blockBoundingGeometry(confirmBlock)
        blockRect = blockGeometry.translated(self.chatbot.contentOffset())

        # Create a point that should be within the confirmation object
        # (middle of the block vertically, left side horizontally)
        testPoint = QPoint(
            int(blockRect.left() + 50),
            int(blockRect.top() + blockRect.height() / 2)
        )

        # Verify the point is within viewport bounds
        viewportRect = self.chatbot.viewport().rect()
        self.assertTrue(viewportRect.contains(testPoint),
                        f"Test point {testPoint} not in viewport {viewportRect}")

        # Test _getConfirmDataAtPosition - should find the confirmation
        confirmData, button = self.chatbot._getConfirmDataAtPosition(
            testPoint)

        # Verify we found the confirmation data
        self.assertIsNotNone(
            confirmData, "Failed to find confirmation data at position")
        self.assertEqual(confirmData.tool_name, toolName)
        self.assertEqual(confirmData.params, params)
        self.assertEqual(confirmData.tool_desc, toolDesc)
        self.assertEqual(confirmData.tool_type, toolType)
        self.assertEqual(confirmData.tool_call_id, toolCallId)

        # Test that hovering over the buttons works
        # Get button rectangles
        cursor.setPosition(pos)
        charFormat = cursor.charFormat()
        objSize = self.chatbot._toolConfirmInterface.intrinsicSize(
            doc, pos, charFormat)

        lineLayout = confirmBlock.layout()
        line = lineLayout.lineForTextPosition(0)
        self.assertTrue(line.isValid())

        lineRect = line.rect()
        objRect = blockRect.adjusted(
            lineRect.x(),
            lineRect.y(),
            lineRect.x() - blockRect.width() + objSize.width(),
            lineRect.y() - blockRect.height() + objSize.height()
        )

        approveRect, rejectRect = self.chatbot._toolConfirmInterface.getButtonRects(
            objRect)

        # Test clicking on approve button
        approvePoint = QPoint(
            int(approveRect.center().x()),
            int(approveRect.center().y())
        )

        confirmData2, button2 = self.chatbot._getConfirmDataAtPosition(
            approvePoint)
        self.assertIsNotNone(confirmData2)
        self.assertEqual(button2, ButtonType.APPROVE)

        # Test clicking on reject button
        rejectPoint = QPoint(
            int(rejectRect.center().x()),
            int(rejectRect.center().y())
        )

        confirmData3, button3 = self.chatbot._getConfirmDataAtPosition(
            rejectPoint)
        self.assertIsNotNone(confirmData3)
        self.assertEqual(button3, ButtonType.REJECT)

    def testGetConfirmDataAtPosition_OutsideObject(self):
        """Test that _getConfirmDataAtPosition returns None for points outside the confirmation"""
        # Add some content
        response = AiResponse(role=AiRole.Assistant, message="Test message")
        response.is_delta = False
        self.chatbot.appendResponse(response)

        # Insert a tool confirmation
        pos = self.chatbot.insertToolConfirmation(
            "test_tool", {"param": "value"}, "Test tool", ToolType.READ_ONLY)

        QTest.qWait(50)

        # Test a point far outside the confirmation area
        outsidePoint = QPoint(10, 5)
        confirmData, button = self.chatbot._getConfirmDataAtPosition(
            outsidePoint)

        # Should return None since point is outside
        self.assertIsNone(confirmData)
        self.assertEqual(button, ButtonType.NONE)
