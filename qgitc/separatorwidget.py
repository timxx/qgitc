# -*- coding: utf-8 -*-

from PySide6.QtCore import QSize
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget


class SeparatorWidget(QWidget):
    """A vertical separator widget instead of QFrame for better appearance"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def sizeHint(self):
        return QSize(16, 16)

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(self.palette().windowText().color().darker(200))
        pen.setWidth(1)
        painter.setPen(pen)
        x = self.width() // 2
        painter.drawLine(x, 0, x, self.height())
