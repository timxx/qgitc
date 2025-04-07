# -*- coding: utf-8 -*-

from PySide6.QtGui import QTextCursor, QTextBlockFormat, QTextCharFormat, QFont
from PySide6.QtWidgets import QTextBrowser

from .llm import AiResponse


class AiChatbot(QTextBrowser):

    def __init__(self, parent=None):
        super().__init__(parent)

    def appendResponse(self, response: AiResponse):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        format = QTextBlockFormat()
        roleFormat = QTextCharFormat()
        roleFormat.setFontWeight(QFont.Bold)
        if self.document().blockCount() == 1:
            cursor.setBlockCharFormat(roleFormat)
        elif not response.is_delta or response.first_delta:
            cursor.insertBlock(format, roleFormat)
        if not response.is_delta or response.first_delta:
            cursor.insertText(response.role + ":")

        if response.role != "user" and response.role != "system":
            format.setBackground(qApp.colorSchema().AiResponseBg)
            format.setForeground(qApp.colorSchema().AiResponseFg)

        if not response.is_delta or response.first_delta:
            cursor.insertBlock(format, QTextCharFormat())
        cursor.insertText(response.message)

        if not response.is_delta:
            cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
            cursor.insertText("")

    def appendServiceUnavailable(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        format = QTextBlockFormat()
        roleFormat = QTextCharFormat()
        roleFormat.setFontWeight(QFont.Bold)
        cursor.insertBlock(format, roleFormat)
        cursor.insertText("System:")

        errorFormat = QTextCharFormat()
        errorFormat.setForeground(qApp.colorSchema().ErrorText)
        cursor.insertBlock(QTextBlockFormat(), errorFormat)
        cursor.insertText(self.tr("Service Unavailable"))
        cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())

    def clear(self):
        super().clear()
