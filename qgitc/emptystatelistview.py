# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QListView


class EmptyStateListView(QListView):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._emptyStateText: str = None

    def setEmptyStateText(self, text: str):
        """Set the empty state text for the view
        Shows the empty state text when there are no items in the view.
        """
        self._emptyStateText = text

    def paintEvent(self, event):
        if self.model().rowCount() == 0 and self._emptyStateText:
            self._drawStateText()
        else:
            super().paintEvent(event)

    def _drawStateText(self):
        painter = QPainter(self.viewport())
        font = self.font()
        font.setItalic(True)
        painter.setFont(font)
        painter.setPen(self.palette().color(
            QPalette.Disabled, QPalette.Text))
        painter.drawText(
            self.viewport().rect(),
            Qt.AlignLeft,
            self._emptyStateText)
