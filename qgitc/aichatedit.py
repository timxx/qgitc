# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QSizePolicy, QWidget


class AiChatEdit(QWidget):
    """Multi-line text input with auto-expanding height"""
    MaxLines = 5
    enterPressed = Signal()
    textChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

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
        self.edit.document().setDocumentMargin(4)

        self._lineHeight = self.edit.document().firstBlock().layout().boundingRect().height()

        self.edit.textChanged.connect(self.textChanged)
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
            if event.key() in [Qt.Key_Enter, Qt.Key_Return]:
                if event.modifiers() == Qt.NoModifier:
                    self.enterPressed.emit()
                    return True
                elif event.modifiers() == Qt.ShiftModifier:
                    return False
        return super().eventFilter(watched, event)
