# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent
from PySide6.QtGui import (
    QTextCursor,
    QTextCharFormat,
    QFont,
    QTextDocument
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

    def appendResponse(self, response: AiResponse):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        if not response.is_delta or response.first_delta:
            if self.blockCount() > 0:
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
        cursor.insertBlock()

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
