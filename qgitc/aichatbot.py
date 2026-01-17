# -*- coding: utf-8 -*-

from typing import Dict

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QFont,
    QMouseEvent,
    QPainter,
    QTextBlock,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit

from qgitc.agenttools import ToolType
from qgitc.aitoolconfirmation import (
    TOOL_CONFIRMATION_OBJECT_TYPE,
    ButtonType,
    ConfirmationStatus,
    ToolConfirmationData,
    ToolConfirmationInterface,
)
from qgitc.applicationbase import ApplicationBase
from qgitc.llm import AiResponse, AiRole
from qgitc.markdownhighlighter import HighlighterState, MarkdownHighlighter


class AiChatBotState:

    UserBlock = 150
    AssistantBlock = 151
    SystemBlock = 152


class AiChatBotHighlighter(MarkdownHighlighter):

    def __init__(self, document: QTextDocument):
        super().__init__(document)

    def highlightBlock(self, text: str):
        state = self.currentBlockState()
        if state == AiChatBotState.UserBlock:
            self._setTitleFormat(len(text), AiRole.User)
            return
        if state == AiChatBotState.AssistantBlock:
            self._setTitleFormat(len(text), AiRole.Assistant)
            return
        if state == AiChatBotState.SystemBlock:
            self._setTitleFormat(len(text), AiRole.System)
            return

        super().highlightBlock(text)

        if self.currentBlockState() == HighlighterState.NoState:
            if self.previousBlockState() == AiChatBotState.SystemBlock:
                charFormat = QTextCharFormat()
                charFormat.setForeground(
                    ApplicationBase.instance().colorSchema().ErrorText)
                self.setFormat(0, len(text), charFormat)

    def _setTitleFormat(self, length: int, role: AiRole):
        charFormat = QTextCharFormat()
        charFormat.setFontWeight(QFont.Bold)
        if role == AiRole.User:
            charFormat.setForeground(
                ApplicationBase.instance().colorSchema().UserBlockFg)
        elif role == AiRole.Assistant:
            charFormat.setForeground(
                ApplicationBase.instance().colorSchema().AssistantBlockFg)
        elif role == AiRole.System:
            charFormat.setForeground(
                ApplicationBase.instance().colorSchema().SystemBlockFg)
        self.setFormat(0, length, charFormat)

    @staticmethod
    def roleToBlockState(role: AiRole):
        if role == AiRole.User:
            return AiChatBotState.UserBlock
        elif role == AiRole.Assistant:
            return AiChatBotState.AssistantBlock
        elif role == AiRole.System:
            return AiChatBotState.SystemBlock

        return HighlighterState.NoState


class AiChatbot(QPlainTextEdit):
    cornerRadius = 5

    # Signals for tool confirmation interaction
    toolConfirmationApproved = Signal(str, dict)  # tool_name, params
    toolConfirmationRejected = Signal(str)  # tool_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = AiChatBotHighlighter(self.document())
        self.setReadOnly(True)

        # Register text object interface for tool confirmations
        self._toolConfirmInterface = ToolConfirmationInterface(self)
        self.document().documentLayout().registerHandler(
            TOOL_CONFIRMATION_OBJECT_TYPE, self._toolConfirmInterface
        )

        # Track confirmation data by position for interaction
        # position -> ToolConfirmationData
        self._confirmations: Dict[int, ToolConfirmationData] = {}
        # Track which confirmation is hovered
        self._hoveredConfirmation: ToolConfirmationData = None

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

    def appendResponse(self, response: AiResponse):
        cursor = self.textCursor()
        selectionStart = cursor.selectionStart()
        selectionEnd = cursor.selectionEnd()
        docLength = self.document().characterCount() - 1
        cursor.movePosition(QTextCursor.End)

        if not response.is_delta or response.first_delta:
            self._insertRoleBlock(cursor, response.role)
            cursor.insertBlock()
        cursor.insertText(response.message)

        if selectionStart != selectionEnd and selectionEnd == docLength:
            newCursor = self.textCursor()
            newCursor.setPosition(selectionStart)
            newCursor.setPosition(selectionEnd, QTextCursor.KeepAnchor)
            self.setTextCursor(newCursor)

    def appendServiceUnavailable(self):
        cursor = self.textCursor()
        selectionStart = cursor.selectionStart()
        selectionEnd = cursor.selectionEnd()
        docLength = self.document().characterCount() - 1
        cursor.movePosition(QTextCursor.End)

        self._insertRoleBlock(cursor, AiRole.System)

        cursor.insertBlock()
        cursor.insertText(self.tr("Service Unavailable"))

        if selectionStart != selectionEnd and selectionEnd == docLength:
            newCursor = self.textCursor()
            newCursor.setPosition(selectionStart)
            newCursor.setPosition(selectionEnd, QTextCursor.KeepAnchor)
            self.setTextCursor(newCursor)

    def _insertRoleBlock(self, cursor: QTextCursor, role: AiRole):
        if self.blockCount() > 1:
            cursor.insertBlock()
        cursor.insertText(self._roleString(role))
        cursor.block().setUserState(AiChatBotHighlighter.roleToBlockState(role))

    def clear(self):
        self._highlighter.clearDirtyBlocks()
        self._confirmations.clear()
        self._hoveredConfirmation = None
        super().clear()

    def event(self, event):
        if event.type() == QEvent.PaletteChange:
            self._highlighter.initTextFormats()
            self._highlighter.rehighlight()

        return super().event(event)

    def _roleString(self, role: AiRole):
        if role == AiRole.User:
            return self.tr("User:")
        if role == AiRole.Assistant:
            return self.tr("Assistant:")

        return self.tr("System:")

    def paintEvent(self, event):
        if self.document().isEmpty():
            return super().paintEvent(event)

        block = self.firstVisibleBlock()

        painter = QPainter(self.viewport())
        viewportRect = self.viewport().rect()
        offset = QPointF(self.contentOffset())
        blockAreaRect = QRectF()

        currBlockType = None
        curClipTop = False

        while block.isValid():
            r = self.blockBoundingRect(block).translated(offset)
            offset.setY(offset.y() + r.height())

            blockType = block.userState()
            if self._isAiBlock(blockType):
                painter.setBrush(self._aiBlockBgColor(blockType))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(
                    r, self.cornerRadius, self.cornerRadius)
                painter.setBrush(Qt.NoBrush)

            if currBlockType is None and not self._isAiBlock(blockType):
                currBlockType = self._findAiBlockType(block)
                curClipTop = True
                blockAreaRect = r
            elif self._isAiBlock(blockType) and blockType != currBlockType:
                self._drawAiBlock(painter, currBlockType,
                                  blockAreaRect, curClipTop)
                currBlockType = blockType
                curClipTop = False
                blockAreaRect = r
            elif currBlockType is not None:
                blockAreaRect.setHeight(blockAreaRect.height() + r.height())

            if offset.y() > viewportRect.height():
                break

            block = block.next()

        if currBlockType is not None:
            self._drawAiBlock(painter, currBlockType,
                              blockAreaRect, curClipTop)

        painter.end()
        super().paintEvent(event)

    @staticmethod
    def _isAiBlock(state):
        return state in [
            AiChatBotState.UserBlock,
            AiChatBotState.AssistantBlock,
            AiChatBotState.SystemBlock]

    def _findAiBlockType(self, block: QTextBlock):
        prevBlock = QTextBlock(block).previous()
        while prevBlock.isValid():
            prevState = prevBlock.userState()
            if self._isAiBlock(prevState):
                return prevState
            prevBlock = prevBlock.previous()

        return None

    def _drawAiBlock(
            self,
            painter: QPainter,
            blockType: AiChatBotState,
            blockAreaRect: QRectF,
            clipTop: bool):
        if blockType is None:
            return

        if blockType == AiChatBotState.UserBlock:
            painter.setPen(
                ApplicationBase.instance().colorSchema().UserBlockBorder)
        elif blockType == AiChatBotState.AssistantBlock:
            painter.setPen(ApplicationBase.instance(
            ).colorSchema().AssistantBlockBorder)
        elif blockType == AiChatBotState.SystemBlock:
            painter.setPen(ApplicationBase.instance(
            ).colorSchema().SystemBlockBorder)

        if clipTop:
            # make the top out of viewport
            blockAreaRect.setTop(blockAreaRect.top() - self.cornerRadius)

        blockAreaRect.adjust(1, 1, -1, -1)
        painter.drawRoundedRect(
            blockAreaRect,
            self.cornerRadius,
            self.cornerRadius)

    def _aiBlockBgColor(self, blockType):
        if blockType == AiChatBotState.UserBlock:
            return ApplicationBase.instance().colorSchema().UserBlockBg
        elif blockType == AiChatBotState.AssistantBlock:
            return ApplicationBase.instance().colorSchema().AssistantBlockBg
        return ApplicationBase.instance().colorSchema().SystemBlockBg

    def insertToolConfirmation(self, toolName: str, params: dict,
                               toolDesc: str = None, toolType: int = ToolType.READ_ONLY):
        """
        Insert a tool confirmation card using QTextObjectInterface.
        
        Args:
            toolName: Name of the tool to execute
            params: Parameters for the tool
            toolDesc: Human-readable description
            toolType: ToolType constant (READ_ONLY, WRITE, DANGEROUS)
            
        Returns:
            Position where the confirmation was inserted
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        # Insert a new block for the confirmation
        if self.document().characterCount() > 1:
            cursor.insertBlock()

        # Create confirmation data
        confirmData = ToolConfirmationData(
            toolName, params, toolDesc, toolType)

        # Create custom character format with our data
        charFormat = QTextCharFormat()
        charFormat.setObjectType(TOOL_CONFIRMATION_OBJECT_TYPE)
        charFormat.setProperty(QTextFormat.UserProperty, confirmData)

        # Get position before inserting
        position = cursor.position()

        # Insert the object replacement character with custom format
        cursor.insertText("\ufffc", charFormat)

        # Store confirmation data for interaction handling
        self._confirmations[position] = confirmData

        # Insert a newline after for proper spacing
        cursor.insertText("\n")

        return position

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for hover effects"""
        mousePos = event.pos()

        # Find which confirmation (if any) the mouse is over by checking rectangles
        hoveredButton = ButtonType.NONE

        # Update hover state
        needsUpdate = False
        hoveredConfirmData, hoveredButton = self._getConfirmDataAtPosition(mousePos)
        if hoveredConfirmData != self._hoveredConfirmation:
            # Clear previous hover
            if self._hoveredConfirmation:
                self._hoveredConfirmation.hovered = False
                self._hoveredConfirmation.hovered_button = ButtonType.NONE
                needsUpdate = True

            # Set new hover
            self._hoveredConfirmation = hoveredConfirmData
            if hoveredConfirmData:
                hoveredConfirmData.hovered = True
                needsUpdate = True

        # Update button hover state
        cursorShape = Qt.IBeamCursor
        if hoveredConfirmData:
            if hoveredConfirmData.hovered_button != hoveredButton:
                hoveredConfirmData.hovered_button = hoveredButton
                needsUpdate = True

            # Set cursor based on button hover
            if hoveredButton in (ButtonType.APPROVE, ButtonType.REJECT):
                cursorShape = Qt.PointingHandCursor

        self.viewport().setCursor(cursorShape)
        if needsUpdate:
            self.viewport().update()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse clicks for tool confirmation interaction"""
        if event.button() != Qt.LeftButton:
            return super().mouseReleaseEvent(event)

        confirmData, clickedButton = self._getConfirmDataAtPosition(event.pos())
        if clickedButton != ButtonType.NONE:
            if clickedButton == ButtonType.APPROVE:
                confirmData.status = ConfirmationStatus.APPROVED
                self.toolConfirmationApproved.emit(
                    confirmData.tool_name, confirmData.params)
            elif clickedButton == ButtonType.REJECT:
                confirmData.status = ConfirmationStatus.REJECTED
                self.toolConfirmationRejected.emit(
                    confirmData.tool_name)

            cursor = self.cursorForPosition(event.pos())
            pos = cursor.block().position()
            self.document().markContentsDirty(pos, 1)
            self.viewport().update()

        super().mouseReleaseEvent(event)

    def _getConfirmDataAtPosition(self, pos: QPoint):
        # get the block at the mouse position
        button = ButtonType.NONE

        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        if not block.isValid() or block.length() != 2 or not block.isVisible():
            return None, button

        confirmData = self._confirmations.get(block.position())
        if not confirmData:
            return None, button

        layout = block.layout()
        br = self.blockBoundingGeometry(block)
        line = layout.lineForTextPosition(0)
        if not line.isValid():
            return None, button

        cursor.setPosition(block.position())
        charFormat = cursor.charFormat()
        objSize = self._toolConfirmInterface.intrinsicSize(
            self.document(), pos, charFormat)
        lineRect = line.rect()
        objRect = QRectF(
            br.x() + lineRect.x(),
            br.y() + lineRect.y(),
            objSize.width(),
            objSize.height()
        )

        # Check if mouse is within this confirmation's rectangle
        if not objRect.contains(pos):
            return None, button

        if confirmData.status == ConfirmationStatus.PENDING:
            approveRect, rejectRect = self._toolConfirmInterface.getButtonRects(
                objRect)
            if approveRect.contains(pos):
                button = ButtonType.APPROVE
            elif rejectRect.contains(pos):
                button = ButtonType.REJECT

        return confirmData, button
