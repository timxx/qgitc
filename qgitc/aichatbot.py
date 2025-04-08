# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QTextBrowser

from .llm import AiResponse


class AiChatbot(QTextBrowser):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rawText = ""

    def appendResponse(self, response: AiResponse):
        if not response.is_delta or response.first_delta:
            self._appendRoleText(response.role, False)

        if response.message:
            self._rawText += response.message

        self.setMarkdown(self._rawText)

    def appendServiceUnavailable(self):
        self._appendRoleText(self.tr("System"))
        self._rawText += "\n"
        self._appendColoredText(
            self.tr("Service Unavailable"), qApp.colorSchema().ErrorText.name())
        self._rawText += "\n"

        self.setMarkdown(self._rawText)

    def clear(self):
        self._rawText = ""
        super().clear()

    def _appendRoleText(self, role: str, applyNow=True):
        if self._rawText and self._rawText[-1] != "\n":
            self._rawText += "\n"

        self._rawText += "\n"
        color = qApp.palette().windowText().color().name()
        self._rawText += '<span style="color:{}"><b>'.format(
            color) + role + ":</b></span>"
        self._rawText += "\n\n"
        if applyNow:
            self.setMarkdown(self._rawText)

    def _appendColoredText(self, text: str, color: str):
        self._rawText += '<span style="color:{}">'.format(
            color) + text + "</span>"
        self.setMarkdown(self._rawText)
