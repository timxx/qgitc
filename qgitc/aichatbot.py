# -*- coding: utf-8 -*-

from typing import Dict, Optional, Tuple

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QFont,
    QMouseEvent,
    QPainter,
    QPolygonF,
    QTextBlock,
    QTextBlockUserData,
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


class AiChatHeaderData(QTextBlockUserData):

    def __init__(self, role: AiRole, collapsed=False, descPos=-1):
        super().__init__()
        self.role = role
        self.collapsed = collapsed
        self.descPos = descPos


class AiChatBotHighlighter(MarkdownHighlighter):

    def __init__(self, document: QTextDocument):
        super().__init__(document)

    def highlightBlock(self, text: str):
        data = self.currentBlockUserData()
        if isinstance(data, AiChatHeaderData):
            self._setTitleFormat(text, data)
            return

        super().highlightBlock(text)

    def _setTitleFormat(self, text: str, data: AiChatHeaderData):
        charFormat = QTextCharFormat()
        charFormat.setFontWeight(QFont.Bold)
        schema = ApplicationBase.instance().colorSchema()
        if data.role == AiRole.User:
            charFormat.setForeground(schema.UserBlockFg)
        elif data.role == AiRole.Assistant:
            charFormat.setForeground(schema.AssistantBlockFg)
        elif data.role == AiRole.System:
            charFormat.setForeground(schema.SystemBlockFg)
        elif data.role == AiRole.Tool:
            charFormat.setForeground(schema.ToolBlockFg)

        self.initUtf16IndexMapper(text)
        if data.descPos != -1:
            titleLength = data.descPos - 1
            self.highlightInlineRules(text)
            self.setFormatPy(0, titleLength, charFormat)
        else:
            self.setFormatPy(0, len(text), charFormat)


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

        self._hoveredHeaderPos: Optional[int] = None

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

    def appendResponse(self, response: AiResponse, collapsed=False):
        cursor = self.textCursor()
        selectionStart = cursor.selectionStart()
        selectionEnd = cursor.selectionEnd()
        docLength = self.document().characterCount() - 1
        cursor.movePosition(QTextCursor.End)

        headerBlock = None
        if not response.is_delta or response.first_delta:
            headerBlock = self._insertHeaderBlock(
                cursor, response.role, collapsed, response.description)
            cursor.insertBlock()

        cursor.insertText(response.message)

        # If collapsed, hide all blocks that belong to this header
        if collapsed and headerBlock:
            self._applyCollapsedState(headerBlock)

        # If this is a delta continuation, keep the current group visibility consistent.
        if response.is_delta and not response.first_delta:
            activeHeader = self._findHeaderBlock(cursor.block())
            if activeHeader is not None:
                headerData = self._headerData(activeHeader)
                if headerData and headerData.collapsed:
                    self._setBlockVisible(cursor.block(), False)

        if selectionStart != selectionEnd and selectionEnd == docLength:
            newCursor = self.textCursor()
            newCursor.setPosition(selectionStart)
            newCursor.setPosition(selectionEnd, QTextCursor.KeepAnchor)
            self.setTextCursor(newCursor)

    def appendServiceUnavailable(self, errorMsg: str = None):
        cursor = self.textCursor()
        selectionStart = cursor.selectionStart()
        selectionEnd = cursor.selectionEnd()
        docLength = self.document().characterCount() - 1
        cursor.movePosition(QTextCursor.End)

        self._insertHeaderBlock(cursor, AiRole.System)

        cursor.insertBlock()
        cursor.insertText(self.tr("Service Unavailable")
                          if errorMsg is None else errorMsg)

        if selectionStart != selectionEnd and selectionEnd == docLength:
            newCursor = self.textCursor()
            newCursor.setPosition(selectionStart)
            newCursor.setPosition(selectionEnd, QTextCursor.KeepAnchor)
            self.setTextCursor(newCursor)

    def _insertHeaderBlock(
            self,
            cursor: QTextCursor,
            role: AiRole,
            collapsed: bool = False,
            description: str = None):
        if self.blockCount() > 1:
            cursor.insertBlock()
        title = self._roleString(role)
        descPos = -1
        if description:
            descPos = len(title) + 1
            title += " " + description
        cursor.insertText(title)
        block = cursor.block()
        block.setUserData(AiChatHeaderData(role, collapsed, descPos))
        return block

    def clear(self):
        self._highlighter.clearDirtyBlocks()
        self._confirmations.clear()
        self._hoveredConfirmation = None
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
        if role == AiRole.Tool:
            return self.tr("Tool:")

        return self.tr("System:")

    def paintEvent(self, event):
        if self.document().isEmpty():
            return super().paintEvent(event)

        block = self.firstVisibleBlock()

        painter = QPainter(self.viewport())
        viewportRect = self.viewport().rect()
        offset = QPointF(self.contentOffset())
        blockAreaRect = QRectF()

        currRole: Optional[AiRole] = None
        curClipTop = False

        while block.isValid():
            r = self.blockBoundingRect(block).translated(offset)
            offset.setY(offset.y() + r.height())

            blockRole = self._headerRole(block)
            if blockRole is not None:
                painter.setBrush(self._aiBlockBgColor(blockRole))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(
                    r, self.cornerRadius, self.cornerRadius)
                painter.setBrush(Qt.NoBrush)

                # Draw expand/collapse toggle aligned to the right side of the header line.
                self._drawHeaderToggle(painter, block)

            if currRole is None and blockRole is None:
                currRole = self._findHeaderRole(block)
                curClipTop = True
                blockAreaRect = r
            elif blockRole is not None and blockRole != currRole:
                self._drawAiBlock(painter, currRole,
                                  blockAreaRect, curClipTop)
                currRole = blockRole
                curClipTop = False
                blockAreaRect = r
            elif currRole is not None:
                blockAreaRect.setHeight(blockAreaRect.height() + r.height())

            if offset.y() > viewportRect.height():
                break

            block = block.next()

        if currRole is not None:
            self._drawAiBlock(painter, currRole,
                              blockAreaRect, curClipTop)

        painter.end()
        super().paintEvent(event)

    def _drawHeaderToggle(self, painter: QPainter, headerBlock: QTextBlock):
        if not headerBlock.isValid() or not headerBlock.isVisible():
            return

        toggleRect = self._toggleRectForHeader(headerBlock)
        if toggleRect is None:
            return

        headerData = self._headerData(headerBlock)
        collapsed = headerData.collapsed if headerData else False
        role = headerData.role if headerData else None
        schema = ApplicationBase.instance().colorSchema()
        if role == AiRole.User:
            painter.setPen(schema.UserBlockFg)
        elif role == AiRole.Assistant:
            painter.setPen(schema.AssistantBlockFg)
        elif role == AiRole.System:
            painter.setPen(schema.SystemBlockFg)
        elif role == AiRole.Tool:
            painter.setPen(schema.ToolBlockFg)

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

        oldHint = painter.renderHints()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(painter.pen().color())
        painter.drawPolygon(pts)
        painter.setBrush(Qt.NoBrush)
        painter.setRenderHints(oldHint)

    def _headerRole(self, block: QTextBlock) -> Optional[AiRole]:
        if not block.isValid():
            return None
        data = block.userData()
        if isinstance(data, AiChatHeaderData):
            return data.role
        return None

    def _findHeaderRole(self, block: QTextBlock) -> Optional[AiRole]:
        prevBlock = QTextBlock(block).previous()
        while prevBlock.isValid():
            role = self._headerRole(prevBlock)
            if role is not None:
                return role
            prevBlock = prevBlock.previous()
        return None

    def _drawAiBlock(
            self,
            painter: QPainter,
            role: Optional[AiRole],
            blockAreaRect: QRectF,
            clipTop: bool):
        if role is None:
            return

        schema = ApplicationBase.instance().colorSchema()
        if role == AiRole.User:
            painter.setPen(schema.UserBlockBorder)
        elif role == AiRole.Assistant:
            painter.setPen(schema.AssistantBlockBorder)
        elif role == AiRole.System:
            painter.setPen(schema.SystemBlockBorder)
        elif role == AiRole.Tool:
            painter.setPen(schema.ToolBlockBorder)

        if clipTop:
            # make the top out of viewport
            blockAreaRect.setTop(blockAreaRect.top() - self.cornerRadius)

        blockAreaRect.adjust(1, 1, -1, -1)
        painter.drawRoundedRect(
            blockAreaRect,
            self.cornerRadius,
            self.cornerRadius)

    def _aiBlockBgColor(self, role: Optional[AiRole]):
        schema = ApplicationBase.instance().colorSchema()
        if role == AiRole.User:
            return schema.UserBlockBg
        elif role == AiRole.Assistant:
            return schema.AssistantBlockBg
        elif role == AiRole.System:
            return schema.SystemBlockBg
        elif role == AiRole.Tool:
            return schema.ToolBlockBg
        return schema.SystemBlockBg

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
        selectionStart = cursor.selectionStart()
        selectionEnd = cursor.selectionEnd()
        doc = self.document()
        docLength = doc.characterCount() - 1
        cursor.movePosition(QTextCursor.End)
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

        # doc.markContentsDirty(0, doc.characterCount())
        # doc.adjustSize()
        # self.updateGeometry()
        # self.viewport().update()
        # Fix vertical scrollbar range not updating correctly
        # The above calls don't seem to help (even with delay)
        # setDocument internal will relayoutDocument/adjustScrollbars
        self.setDocument(doc)

        if selectionStart != selectionEnd and selectionEnd == docLength:
            newCursor = self.textCursor()
            newCursor.setPosition(selectionStart)
            newCursor.setPosition(selectionEnd, QTextCursor.KeepAnchor)
            self.setTextCursor(newCursor)

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
        if not block.isValid() or not block.isVisible() or self._headerRole(block) is None:
            return None, False

        toggleRect = self._toggleRectForHeader(block)
        if toggleRect is None:
            return None, False

        return block.position(), toggleRect.contains(pos)

    def _toggleCollapsed(self, headerPos: int):
        headerBlock = self.document().findBlock(headerPos)
        if not headerBlock.isValid() or self._headerRole(headerBlock) is None:
            return

        headerData = self._headerData(headerBlock)
        headerData.collapsed = not headerData.collapsed
        self._applyCollapsedState(headerBlock)

    def _applyCollapsedState(self, headerBlock: QTextBlock):
        headerData = self._headerData(headerBlock)
        collapsed = headerData.collapsed if headerData else False
        block = headerBlock.next()
        while block.isValid() and self._headerRole(block) is None:
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
        if self._headerRole(block) is not None:
            return block

        prev = QTextBlock(block).previous()
        while prev.isValid():
            if self._headerRole(prev) is not None:
                return prev
            prev = prev.previous()
        return None

    def _headerData(self, headerBlock: Optional[QTextBlock]) -> Optional[AiChatHeaderData]:
        if headerBlock is None or not headerBlock.isValid():
            return None
        data = headerBlock.userData()
        if isinstance(data, AiChatHeaderData):
            return data
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

    def setHighlighterEnabled(self, enabled: bool):
        """Enable or disable the syntax highlighter."""
        if enabled:
            if self._highlighter is None:
                self._highlighter = AiChatBotHighlighter(self.document())
        elif self._highlighter is not None:
            self._highlighter.setDocument(None)
            self._highlighter = None
