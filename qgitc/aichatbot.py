# -*- coding: utf-8 -*-

from PySide6.QtCore import (
    QEvent,
    QPointF,
    QRectF,
    Qt
)
from PySide6.QtGui import (
    QTextCursor,
    QTextCharFormat,
    QFont,
    QTextDocument,
    QPainter,
    QPainterPath,
    QTextBlock
)
from PySide6.QtWidgets import QPlainTextEdit
from .markdownhighlighter import HighlighterState, MarkdownHighlighter
from .llm import AiResponse, AiRole


class AiChatBotState:

    UserBlock = 150
    AssistantBlock = 151
    SystemBlock = 152


class AiChatBotHighlighter(MarkdownHighlighter):

    def __init__(self, document: QTextDocument):
        super().__init__(document)

    def highlightBlock(self, text: str):
        super().highlightBlock(text)

        if self.currentBlockState() == HighlighterState.NoState:
            if self.previousBlockState() == AiChatBotState.SystemBlock:
                charFormat = QTextCharFormat()
                charFormat.setForeground(qApp.colorSchema().ErrorText)
                self.setFormat(0, len(text), charFormat)

            elif text == self.tr("User:"):
                self.setCurrentBlockState(AiChatBotState.UserBlock)
                self._setTitleFormat(len(text))
            elif text == self.tr("Assistant:"):
                self.setCurrentBlockState(AiChatBotState.AssistantBlock)
                self._setTitleFormat(len(text))
            elif text == self.tr("System:"):
                self.setCurrentBlockState(AiChatBotState.SystemBlock)
                self._setTitleFormat(len(text))

    def _setTitleFormat(self, length: int):
        charFormat = QTextCharFormat()
        charFormat.setFontWeight(QFont.Bold)
        self.setFormat(0, length, charFormat)


class AiChatbot(QPlainTextEdit):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = AiChatBotHighlighter(self.document())
        self.setReadOnly(True)

    def appendResponse(self, response: AiResponse):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        if not response.is_delta or response.first_delta:
            if self.blockCount() > 1:
                cursor.insertBlock()
            cursor.insertText(self._roleString(response.role))
            cursor.insertBlock()
        cursor.insertText(response.message)

    def appendServiceUnavailable(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        cursor.insertBlock()
        cursor.insertText(self._roleString(AiRole.System))

        cursor.insertBlock()
        cursor.insertText(self.tr("Service Unavailable"))

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

    def _drawAiBlock(self, painter: QPainter, blockType: AiChatBotState, blockAreaRect: QRectF, clipTop: bool):
        if blockType is None:
            return

        if blockType == AiChatBotState.UserBlock:
            painter.setPen(qApp.colorSchema().UserBlockBorder)
        elif blockType == AiChatBotState.AssistantBlock:
            painter.setPen(qApp.colorSchema().AssistantBlockBorder)
        elif blockType == AiChatBotState.SystemBlock:
            painter.setPen(qApp.colorSchema().SystemBlockBorder)

        cornerRadius = 5
        if clipTop:
            # make the top out of viewport
            blockAreaRect.setTop(blockAreaRect.top() - cornerRadius)

        # to avoid border overlap
        blockAreaRect.setHeight(blockAreaRect.height() - 2)
        painter.drawRoundedRect(blockAreaRect, cornerRadius, cornerRadius)
