# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QBrush, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QLabel

from qgitc.applicationbase import ApplicationBase
from qgitc.drawutils import makeColoredIconPixmap


class ColoredIconLabel(QLabel):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon: QIcon = None
        self._size: QSize = QSize(16, 16)
        self._pixmap: QPixmap = None
        self._colorSchema: str = None

    def setIcon(self, icon: QIcon, colorSchema: str = None, size: QSize = QSize(16, 16)):
        self._icon = icon
        self._size = size
        self._colorSchema = colorSchema
        self._pixmap = self._makePixmap()

    def paintEvent(self, event):
        if self._pixmap is None:
            return

        rect = QRect(QPoint(0, 0), self._size)
        rect.moveCenter(self.rect().center())
        painter = QPainter(self)
        painter.drawPixmap(rect, self._pixmap)

    def _makePixmap(self):
        if not self._icon or self._icon.isNull():
            return None

        brush = None
        if self._colorSchema:
            brush = QBrush(
                getattr(ApplicationBase.instance().colorSchema(), self._colorSchema))

        return makeColoredIconPixmap(self, self._icon, self._size, brush)

    def sizeHint(self):
        return self._size

    def event(self, evt):
        if evt.type() == QEvent.PaletteChange:
            self._pixmap = self._makePixmap()
        return super().event(evt)
