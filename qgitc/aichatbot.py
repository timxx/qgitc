# -*- coding: utf-8 -*-

from typing import Dict, Optional, Tuple

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QFont,
    QMouseEvent,
    QPainter,
    QPolygonF,
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

    toggleMarginRight = 8
    toggleMarginTop = 2
    toggleMinSize = 10
    toggleMaxSize = 14

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

        # Track which AI blocks are collapsed
        # header_block_position -> collapsed
        self._collapsedBlocks: Dict[int, bool] = {}
        self._hoveredHeaderPos: Optional[int] = None

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

    def appendResponse(self, response: AiResponse, collapsed: bool = False):
        cursor = self.textCursor()
        selectionStart = cursor.selectionStart()
        selectionEnd = cursor.selectionEnd()
        docLength = self.document().characterCount() - 1
        cursor.movePosition(QTextCursor.End)

        headerBlock: Optional[QTextBlock] = None

        if not response.is_delta or response.first_delta:
            headerBlock = self._insertRoleBlock(cursor, response.role)
            cursor.insertBlock()
            self._collapsedBlocks[headerBlock.position()] = collapsed
            if collapsed:
                # Hide the first body block immediately (streaming will append into it).
                self._setBlockVisible(cursor.block(), False)
        cursor.insertText(response.message)

        # If this is a delta continuation, keep the current group visibility consistent.
        if response.is_delta and not response.first_delta:
            activeHeader = self._findHeaderBlock(cursor.block())
            if activeHeader is not None:
                isCollapsed = self._collapsedBlocks.get(
                    activeHeader.position(), False)
                if isCollapsed:
                    self._setBlockVisible(cursor.block(), False)

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
        block = cursor.block()
        block.setUserState(AiChatBotHighlighter.roleToBlockState(role))
        return block

    def clear(self):
        self._highlighter.clearDirtyBlocks()
        self._confirmations.clear()
        self._hoveredConfirmation = None
        self._collapsedBlocks.clear()
        self._hoveredHeaderPos = None
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
            if self._isHeaderBlock(blockType):
                painter.setBrush(self._aiBlockBgColor(blockType))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(
                    r, self.cornerRadius, self.cornerRadius)
                painter.setBrush(Qt.NoBrush)

                # Draw expand/collapse toggle aligned to the right side of the header line.
                self._drawHeaderToggle(painter, block)

            if currBlockType is None and not self._isHeaderBlock(blockType):
                currBlockType = self._findHeaderBlock(block)
                curClipTop = True
                blockAreaRect = r
            elif self._isHeaderBlock(blockType) and blockType != currBlockType:
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

    def _drawHeaderToggle(self, painter: QPainter, headerBlock: QTextBlock):
        if not headerBlock.isValid() or not headerBlock.isVisible():
            return

        toggleRect = self._toggleRectForHeader(headerBlock)
        if toggleRect is None:
            return

        collapsed = self._collapsedBlocks.get(headerBlock.position(), False)
        blockType = headerBlock.userState()
        if blockType == AiChatBotState.UserBlock:
            painter.setPen(
                ApplicationBase.instance().colorSchema().UserBlockFg)
        elif blockType == AiChatBotState.AssistantBlock:
            painter.setPen(
                ApplicationBase.instance().colorSchema().AssistantBlockFg)
        else:
            painter.setPen(
                ApplicationBase.instance().colorSchema().SystemBlockFg)

        # Triangle icon
        cx = toggleRect.center().x()
        cy = toggleRect.center().y()
        s = toggleRect.width() / 2.0

        if collapsed:
            # Pointing right
            pts = QPolygonF([
                QPointF(cx - s * 0.4, cy - s * 0.6),
                QPointF(cx - s * 0.4, cy + s * 0.6),
                QPointF(cx + s * 0.6, cy),
            ])
        else:
            # Pointing down
            pts = QPolygonF([
                QPointF(cx - s * 0.6, cy - s * 0.4),
                QPointF(cx + s * 0.6, cy - s * 0.4),
                QPointF(cx, cy + s * 0.6),
            ])

        painter.setBrush(painter.pen().color())
        painter.drawPolygon(pts)
        painter.setBrush(Qt.NoBrush)

    @staticmethod
    def _isHeaderBlock(state):
        return state in [
            AiChatBotState.UserBlock,
            AiChatBotState.AssistantBlock,
            AiChatBotState.SystemBlock]

    def _findHeaderBlock(self, block: QTextBlock):
        prevBlock = QTextBlock(block).previous()
        while prevBlock.isValid():
            prevState = prevBlock.userState()
            if self._isHeaderBlock(prevState):
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

        hoveredHeaderPos, overToggle = self._getHeaderToggleAtPosition(
            mousePos)

        # Find which confirmation (if any) the mouse is over by checking rectangles
        hoveredButton = ButtonType.NONE

        # Update hover state
        needsUpdate = False
        hoveredConfirmData, hoveredButton = self._getConfirmDataAtPosition(
            mousePos)
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

        # Toggle hover takes precedence for cursor
        if overToggle and hoveredHeaderPos is not None:
            cursorShape = Qt.PointingHandCursor

        if self._hoveredHeaderPos != hoveredHeaderPos:
            self._hoveredHeaderPos = hoveredHeaderPos
            needsUpdate = True

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

        headerPos, overToggle = self._getHeaderToggleAtPosition(event.pos())
        if overToggle and headerPos is not None:
            self._toggleCollapsed(headerPos)
            event.accept()
            return

        confirmData, clickedButton = self._getConfirmDataAtPosition(
            event.pos())
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

    def _toggleRectForHeader(self, headerBlock: QTextBlock) -> Optional[QRectF]:
        layout = headerBlock.layout()
        line = layout.lineForTextPosition(0)
        if not line.isValid():
            return None

        viewportRect = self.viewport().rect()
        lineRect = line.rect()

        # blockBoundingGeometry is in document coordinates; translate to viewport.
        br = self.blockBoundingGeometry(
            headerBlock).translated(self.contentOffset())

        size = int(min(self.toggleMaxSize, max(
            self.toggleMinSize, lineRect.height() * 0.75)))
        x = viewportRect.right() - self.toggleMarginRight - size
        y = br.y() + lineRect.y() + (lineRect.height() - size) / 2.0
        y = max(y, br.y() + self.toggleMarginTop)

        return QRectF(x, y, size, size)

    def _getHeaderToggleAtPosition(self, pos: QPoint) -> Tuple[Optional[int], bool]:
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        if not block.isValid() or not block.isVisible() or not self._isHeaderBlock(block.userState()):
            return None, False

        toggleRect = self._toggleRectForHeader(block)
        if toggleRect is None:
            return None, False

        return block.position(), toggleRect.contains(pos)

    def _toggleCollapsed(self, headerPos: int):
        headerBlock = self.document().findBlock(headerPos)
        if not headerBlock.isValid() or not self._isHeaderBlock(headerBlock.userState()):
            return

        newState = not self._collapsedBlocks.get(headerPos, False)
        self._collapsedBlocks[headerPos] = newState
        self._applyCollapsedState(headerBlock)

    def _applyCollapsedState(self, headerBlock: QTextBlock):
        collapsed = self._collapsedBlocks.get(headerBlock.position(), False)
        block = headerBlock.next()
        while block.isValid() and not self._isHeaderBlock(block.userState()):
            self._setBlockVisible(block, not collapsed)
            block = block.next()

        # Force relayout and repaint.
        self.document().markContentsDirty(0, self.document().characterCount())
        self.viewport().update()

    def _setBlockVisible(self, block: QTextBlock, visible: bool):
        if not block.isValid():
            return

        block.setVisible(visible)

    def _findHeaderBlock(self, block: QTextBlock) -> Optional[QTextBlock]:
        if not block.isValid():
            return None
        if self._isHeaderBlock(block.userState()):
            return block

        prev = QTextBlock(block).previous()
        while prev.isValid():
            if self._isHeaderBlock(prev.userState()):
                return prev
            prev = prev.previous()
        return None

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
