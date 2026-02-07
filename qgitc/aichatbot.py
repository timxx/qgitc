# -*- coding: utf-8 -*-

import re
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPolygonF,
    QTextBlock,
    QTextBlockUserData,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QTextOption,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit

from qgitc.agenttools import ToolType
from qgitc.aitoolconfirmation import (
    TOOL_CONFIRMATION_OBJECT_TYPE,
    ButtonType,
    ConfirmationStatus,
    ToolConfirmationData,
    ToolConfirmationInterface,
)
from qgitc.applicationbase import ApplicationBase
from qgitc.drawutils import drawRoundedRect
from qgitc.findconstants import FindFlags
from qgitc.findpanel import FindPanel
from qgitc.llm import AiResponse, AiRole
from qgitc.markdownhighlighter import MarkdownHighlighter


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
    # tool_name, params, tool_call_id
    toolConfirmationApproved = Signal(str, dict, str)
    toolConfirmationRejected = Signal(str, str)  # tool_name, tool_call_id

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

        # Find panel state
        self._findPanel: Optional[FindPanel] = None
        self._findMatches: List[Tuple[int, int]] = []
        self._findCurrentIndex: int = -1

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

        self.setWordWrapMode(QTextOption.WrapAnywhere)

    def keyPressEvent(self, event: QKeyEvent):
        # Ctrl+F (Find)
        if event.matches(QKeySequence.Find):
            self.executeFind()
            event.accept()
            return

        # When find panel is visible, support Esc + FindNext/Previous.
        if self._findPanel and self._findPanel.isVisible():
            if event.key() == Qt.Key_Escape:
                self._findPanel.hideAnimate()
                event.accept()
                return
            if event.matches(QKeySequence.FindNext):
                self._findNext()
                event.accept()
                return
            if event.matches(QKeySequence.FindPrevious):
                self._findPrevious()
                event.accept()
                return

        super().keyPressEvent(event)

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

        # Keep find results updated while panel is open, without moving the viewport.
        if self._findPanel and self._findPanel.isVisible() and self._findPanel.text:
            self._refreshFindResults(preserveSelection=True)

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
        title, descPos = self._headerString(role, description)
        cursor.insertText(title)
        block = cursor.block()
        block.setUserData(AiChatHeaderData(role, collapsed, descPos))
        return block

    def clear(self):
        self._highlighter.clearDirtyBlocks()
        self._confirmations.clear()
        self._hoveredConfirmation = None
        self._hoveredHeaderPos = None

        self._clearFindState()
        super().clear()

    def executeFind(self):
        if not self._findPanel:
            self._findPanel = FindPanel(self.viewport(), self)
            self._findPanel.findRequested.connect(self._onFindRequested)
            self._findPanel.nextRequested.connect(self._findNext)
            self._findPanel.previousRequested.connect(self._findPrevious)
            self._findPanel.afterHidden.connect(self._onFindHidden)

        # Prime with current selection if any (first line only).
        text = self.textCursor().selectedText()
        if text:
            # QTextCursor.selectedText uses U+2029 for line breaks.
            text = text.replace("\u2029", "\n").lstrip("\n")
            idx = text.find("\n")
            if idx != -1:
                text = text[:idx]
            self._findPanel.setText(text)

        self._findPanel.showAnimate()

    def _onFindHidden(self):
        self._clearFindState()
        self.viewport().update()

    def _clearFindState(self):
        self._findMatches = []
        self._findCurrentIndex = -1
        # Clear highlights
        self.setExtraSelections([])

    def _onFindRequested(self, text: str, flags: int):
        self._findMatches = self._computeFindMatches(text, flags)

        if not self._findMatches:
            self._findCurrentIndex = -1
            self._applyFindHighlights([], -1)
            if self._findPanel:
                self._findPanel.updateStatus(0, 0)
            return

        cur = self.textCursor()
        selStart, selEnd = cur.selectionStart(), cur.selectionEnd()
        idx = -1

        if cur.hasSelection():
            # 1) Exact match (keeps index stable when toggling flags)
            for i, (s, e) in enumerate(self._findMatches):
                if s == selStart and e == selEnd:
                    idx = i
                    break

            # 2) Same start (keeps incremental typing anchored)
            if idx == -1:
                for i, (s, _) in enumerate(self._findMatches):
                    if s == selStart:
                        idx = i
                        break

            # 3) Contains selection start (handles cases where selection was shorter/longer)
            if idx == -1:
                for i, (s, e) in enumerate(self._findMatches):
                    if s <= selStart < e:
                        idx = i
                        break

            # 4) Fallback: next match after the current selection end
            if idx == -1:
                pos = selEnd
                idx = 0
                for i, (s, _) in enumerate(self._findMatches):
                    if s >= pos:
                        idx = i
                        break
        else:
            # No selection: pick the next match at/after the caret.
            pos = cur.position()
            idx = 0
            for i, (s, _) in enumerate(self._findMatches):
                if s >= pos:
                    idx = i
                    break
        self._findCurrentIndex = idx
        self._selectFindMatch(self._findCurrentIndex)

    def _refreshFindResults(self, preserveSelection: bool = True):
        if not self._findPanel or not self._findPanel.isVisible():
            return
        if not self._findPanel.text:
            self._clearFindState()
            self._findPanel.updateStatus(0, 0)
            return

        matches = self._computeFindMatches(
            self._findPanel.text, self._findPanel.flags)
        self._findMatches = matches

        if not matches:
            self._findCurrentIndex = -1
            self._applyFindHighlights([], -1)
            self._findPanel.updateStatus(0, 0)
            return

        idx = self._findCurrentIndex
        if preserveSelection:
            cur = self.textCursor()
            selStart, selEnd = cur.selectionStart(), cur.selectionEnd()
            for i, (s, e) in enumerate(matches):
                if s == selStart and e == selEnd:
                    idx = i
                    break

        if idx < 0:
            idx = 0
        if idx >= len(matches):
            idx = len(matches) - 1

        self._findCurrentIndex = idx
        self._applyFindHighlights(matches, idx)
        self._findPanel.updateStatus(idx, len(matches))

    def _findNext(self):
        if not self._findMatches:
            return
        if self._findCurrentIndex < 0:
            self._findCurrentIndex = 0
        else:
            self._findCurrentIndex = (
                self._findCurrentIndex + 1) % len(self._findMatches)
        self._selectFindMatch(self._findCurrentIndex)

    def _findPrevious(self):
        if not self._findMatches:
            return
        if self._findCurrentIndex < 0:
            self._findCurrentIndex = len(self._findMatches) - 1
        else:
            self._findCurrentIndex = (
                self._findCurrentIndex - 1) % len(self._findMatches)
        self._selectFindMatch(self._findCurrentIndex)

    def _selectFindMatch(self, index: int):
        if not self._findMatches or index < 0 or index >= len(self._findMatches):
            return

        start, end = self._findMatches[index]
        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)
        self.centerCursor()

        self._applyFindHighlights(self._findMatches, index)
        if self._findPanel:
            self._findPanel.updateStatus(index, len(self._findMatches))

    def _applyFindHighlights(self, matches: List[Tuple[int, int]], currentIndex: int):
        if not matches:
            self.setExtraSelections([])
            return

        schema = ApplicationBase.instance().colorSchema()
        baseBg = QColor(schema.FindResult)
        baseBg.setAlpha(90)
        curBg = QColor(schema.FindResult)
        curBg.setAlpha(170)

        selections: List[QTextEdit.ExtraSelection] = []

        # Safety cap: don't highlight an extreme number of matches.
        maxHighlights = 2000
        doc = self.document()

        for i, (s, e) in enumerate(matches[:maxHighlights]):
            sel = QTextEdit.ExtraSelection()
            sel.cursor = QTextCursor(doc)
            sel.cursor.setPosition(s)
            sel.cursor.setPosition(e, QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(curBg if i == currentIndex else baseBg)
            sel.format = fmt
            selections.append(sel)

        self.setExtraSelections(selections)

    def _computeFindMatches(self, text: str, flags: int) -> List[Tuple[int, int]]:
        if not text:
            return []

        plain = self.document().toPlainText()

        if flags & FindFlags.UseRegExp:
            pattern = text
            if flags & FindFlags.WholeWords:
                pattern = rf"\b(?:{pattern})\b"

            reFlags = re.MULTILINE
            if not (flags & FindFlags.CaseSenitively):
                reFlags |= re.IGNORECASE

            try:
                rx = re.compile(pattern, reFlags)
            except re.error:
                return []

            matches: List[Tuple[int, int]] = []
            for m in rx.finditer(plain):
                if m.start() == m.end():
                    continue
                matches.append((m.start(), m.end()))
            return matches

        qtFlags = QTextDocument.FindFlags()
        if flags & FindFlags.CaseSenitively:
            qtFlags |= QTextDocument.FindCaseSensitively
        if flags & FindFlags.WholeWords:
            qtFlags |= QTextDocument.FindWholeWords

        matches: List[Tuple[int, int]] = []
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.Start)
        while True:
            cursor = self.document().find(text, cursor, qtFlags)
            if cursor.isNull():
                break
            matches.append((cursor.selectionStart(), cursor.selectionEnd()))
        return matches

    def event(self, event):
        if event.type() == QEvent.PaletteChange:
            self._highlighter.initTextFormats()
            self._highlighter.rehighlight()

        return super().event(event)

    def _headerString(self, role: AiRole, description: str = None):
        if role == AiRole.User:
            template = self.tr("User: {0}")
        elif role == AiRole.Assistant:
            template = self.tr("Assistant: {0}")
        elif role == AiRole.Tool:
            template = self.tr("Tool: {0}")
        else:
            template = self.tr("System: {0}")

        if not description:
            return template.format(""), -1

        descPos = len(template.format("")) + 1
        return template.format(description), descPos

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
            borderColor = schema.UserBlockBorder
        elif role == AiRole.Assistant:
            borderColor = schema.AssistantBlockBorder
        elif role == AiRole.System:
            borderColor = schema.SystemBlockBorder
        elif role == AiRole.Tool:
            borderColor = schema.ToolBlockBorder

        if clipTop:
            # make the top out of viewport
            blockAreaRect.setTop(blockAreaRect.top() - self.cornerRadius)

        drawRoundedRect(painter, blockAreaRect, self.cornerRadius, borderColor)

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
                               toolDesc: str = None, toolType: int = ToolType.READ_ONLY,
                               toolCallId: str = None):
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
            toolName, params, toolDesc, toolType, tool_call_id=toolCallId)

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
        # setDocument still not always work, so do a resize trick
        size = self.size()
        self.resize(size.width() + 1, size.height())
        self.resize(size)
        self.setDocument(doc)

        if selectionStart != selectionEnd and selectionEnd == docLength:
            newCursor = self.textCursor()
            newCursor.setPosition(selectionStart)
            newCursor.setPosition(selectionEnd, QTextCursor.KeepAnchor)
            self.setTextCursor(newCursor)

        return position

    def setToolConfirmationStatus(self, toolCallId: str, status: ConfirmationStatus) -> bool:
        """Update confirmation card status by OpenAI tool_call_id.

        Returns True if at least one confirmation was updated.
        """
        if not toolCallId:
            return False

        updated = False
        for pos, confirmData in self._confirmations.items():
            if confirmData and confirmData.tool_call_id == toolCallId:
                confirmData.status = status
                updated = True
                # Repaint that block.
                self.document().markContentsDirty(pos, 1)

        if updated:
            self.viewport().update()
        return updated

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for hover effects"""
        mousePos = event.position().toPoint()

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
                self._hoveredConfirmation.hovered_button = ButtonType.NONE
                needsUpdate = True

            # Set new hover
            self._hoveredConfirmation = hoveredConfirmData

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

        pos = event.position().toPoint()
        headerPos, overToggle = self._getHeaderToggleAtPosition(pos)
        if overToggle and headerPos is not None:
            self._toggleCollapsed(headerPos)
            event.accept()
            return

        confirmData, clickedButton = self._getConfirmDataAtPosition(pos)
        if clickedButton != ButtonType.NONE:
            if clickedButton == ButtonType.APPROVE:
                confirmData.status = ConfirmationStatus.APPROVED
                self.toolConfirmationApproved.emit(
                    confirmData.tool_name, confirmData.params, confirmData.tool_call_id)
            elif clickedButton == ButtonType.REJECT:
                confirmData.status = ConfirmationStatus.REJECTED
                self.toolConfirmationRejected.emit(
                    confirmData.tool_name, confirmData.tool_call_id)

            cursor = self.cursorForPosition(pos)
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
        br = self.blockBoundingGeometry(block).translated(self.contentOffset())
        line = layout.lineForTextPosition(0)
        if not line.isValid():
            return None, button

        cursor.setPosition(block.position())
        charFormat = cursor.charFormat()
        objSize = self._toolConfirmInterface.intrinsicSize(
            self.document(), block.position(), charFormat)
        lineRect = line.rect()
        objRect = QRectF(
            br.x() + lineRect.x(),
            br.y() + lineRect.y(),
            objSize.width(),
            objSize.height()
        )

        # Check if mouse is within this confirmation's rectangle
        if not objRect.contains(QPointF(pos)):
            return None, button

        if confirmData.status == ConfirmationStatus.PENDING:
            approveRect, rejectRect = self._toolConfirmInterface.getButtonRects(
                objRect)
            if approveRect.contains(QPointF(pos)):
                button = ButtonType.APPROVE
            elif rejectRect.contains(QPointF(pos)):
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

    def collapseLatestReasoningBlock(self):
        """Collapse the most recent assistant reasoning block (🧠 ...)."""

        doc = self.document()
        block = doc.lastBlock()
        while block.isValid():
            headerData = self._headerData(block)
            if headerData and headerData.role == AiRole.Assistant and headerData.descPos != -1:
                if not headerData.collapsed:
                    headerData.collapsed = True
                    self._applyCollapsedState(block)
                return
            block = block.previous()
