# -*- coding: utf-8 -*-

from typing import Optional

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QSizePolicy, QWidget

from qgitc.agent.slash_commands import CommandRegistry, SlashCommand
from qgitc.slash_command_popup import SlashCommandPopup


class AiChatEdit(QWidget):
    """Multi-line text input with auto-expanding height"""
    MaxLines = 5
    enterPressed = Signal()
    textChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._commandRegistry = None  # type: Optional[CommandRegistry]
        self._slashCommandPopup = None  # type: Optional[SlashCommandPopup]

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.edit = QPlainTextEdit(self)
        layout.addWidget(self.edit)

        font = self.font()
        font.setPointSize(9)
        self.setFont(font)

        self.setFocusProxy(self.edit)

        self.edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        doc = self.edit.document()
        doc.setDocumentMargin(4)

        block = doc.firstBlock()
        layout = block.layout()
        self._lineHeight = layout.boundingRect().height()

        self.edit.textChanged.connect(self._onEditorTextChanged)
        self.edit.document().documentLayout().documentSizeChanged.connect(
            self._onDocumentSizeChanged)

        self._adjustHeight()
        self.edit.installEventFilter(self)

    def toPlainText(self):
        return self.edit.toPlainText()

    def clear(self):
        self.edit.clear()

    def setPlaceholderText(self, text):
        self.edit.setPlaceholderText(text)

    def textCursor(self):
        return self.edit.textCursor()

    def setCommandRegistry(self, registry: CommandRegistry):
        self._commandRegistry = registry

    def _onEditorTextChanged(self):
        self.textChanged.emit()
        self._updateSlashCommandPopup()

    def _ensureSlashCommandPopup(self) -> SlashCommandPopup:
        if self._slashCommandPopup is None:
            self._slashCommandPopup = SlashCommandPopup(self)
            self._slashCommandPopup.setKeyTarget(self.edit)
            self._slashCommandPopup.commandSelected.connect(
                self._onSlashCommandSelected)
        return self._slashCommandPopup

    @staticmethod
    def _fuzzyMatch(name: str, query: str) -> bool:
        if not query:
            return True
        idx = 0
        lower_name = name.lower()
        lower_query = query.lower()
        for ch in lower_name:
            if idx < len(lower_query) and ch == lower_query[idx]:
                idx += 1
        return idx == len(lower_query)

    def _updateSlashCommandPopup(self):
        if self._commandRegistry is None:
            return

        text = self.toPlainText()
        stripped = text.strip()
        if not stripped.startswith("/"):
            if self._slashCommandPopup is not None:
                self._slashCommandPopup.hide()
            return

        after_slash = stripped[1:]
        if " " in after_slash:
            if self._slashCommandPopup is not None:
                self._slashCommandPopup.hide()
            return

        query = after_slash
        commands = [
            cmd for cmd in self._commandRegistry.listCommands()
            if self._fuzzyMatch(cmd.name, query)
        ]

        popup = self._ensureSlashCommandPopup()
        if not commands:
            popup.hide()
            return

        popup.setCommands(commands)
        cursor_rect = self.edit.cursorRect()
        pos = self.edit.mapToGlobal(cursor_rect.bottomLeft())
        popup.showAt(pos)
        self.edit.setFocus()

    def _onSlashCommandSelected(self, command: SlashCommand):
        self.edit.setPlainText("/{} ".format(command.name))
        cursor = self.edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.edit.setTextCursor(cursor)
        if self._slashCommandPopup is not None:
            self._slashCommandPopup.hide()

    def _onDocumentSizeChanged(self, newSize):
        self._adjustHeight()

    def _adjustHeight(self):
        lineCount = self.edit.document().lineCount()
        margin = self.edit.document().documentMargin()
        # see `QLineEdit::sizeHint()`
        verticalMargin = 2 * 1
        if lineCount < AiChatEdit.MaxLines:
            height = lineCount * self._lineHeight
            self.edit.setMinimumHeight(height)
            self.setFixedHeight(height + margin * 2 + verticalMargin)
        else:
            maxHeight = AiChatEdit.MaxLines * self._lineHeight
            self.edit.setMinimumHeight(maxHeight + margin * 2)
            self.setFixedHeight(maxHeight + margin * 2 + verticalMargin)

    def eventFilter(self, watched, event: QEvent):
        if watched == self.edit and event.type() == QEvent.KeyPress:
            if self._slashCommandPopup is not None and self._slashCommandPopup.isVisible():
                if event.key() == Qt.Key_Escape:
                    self._slashCommandPopup.hide()
                    return True
                if event.key() == Qt.Key_Down:
                    self._slashCommandPopup.selectNext()
                    return True
                if event.key() == Qt.Key_Up:
                    self._slashCommandPopup.selectPrevious()
                    return True
                if event.key() == Qt.Key_Tab:
                    self._slashCommandPopup.activateCurrent()
                    return True

            if event.key() in [Qt.Key_Enter, Qt.Key_Return]:
                if event.modifiers() == Qt.NoModifier:
                    self.enterPressed.emit()
                    return True
                elif event.modifiers() == Qt.ShiftModifier:
                    return False
        return super().eventFilter(watched, event)
