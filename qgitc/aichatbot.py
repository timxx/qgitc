# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QFont,
    QPainter,
    QTextBlock,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import QPlainTextEdit

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = AiChatBotHighlighter(self.document())
        self.setReadOnly(True)

    def appendResponse(self, response: AiResponse):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        if not response.is_delta or response.first_delta:
            self._insertRoleBlock(cursor, response.role)
            cursor.insertBlock()
        cursor.insertText(response.message)

    def appendServiceUnavailable(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        self._insertRoleBlock(cursor, AiRole.System)

        cursor.insertBlock()
        cursor.insertText(self.tr("Service Unavailable"))

    def _insertRoleBlock(self, cursor: QTextCursor, role: AiRole):
        if self.blockCount() > 1:
            cursor.insertBlock()
        cursor.insertText(self._roleString(role))
        cursor.block().setUserState(AiChatBotHighlighter.roleToBlockState(role))

    def clear(self):
        self._highlighter.clearDirtyBlocks()
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
