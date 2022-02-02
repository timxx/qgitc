# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QToolButton
from PySide6.QtGui import (QPainter, QIcon, QPen)
from PySide6.QtCore import (QRect, QPoint, Qt)


class ToggleIconButton(QToolButton):

    def __init__(self, icon, iconSize, parent=None):
        super().__init__(parent)
        self._iconSize = iconSize
        self.setIcon(icon)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.isChecked():
            oldPen = painter.pen()
            painter.setPen(QPen(Qt.black, 1))
            rc = self.rect().adjusted(1, 1, -1, -1)
            painter.drawRect(rc)
            painter.setPen(oldPen)

        state = QIcon.Disabled
        if self.isEnabled():
            state = QIcon.Active if self.isDown() else QIcon.Normal
        pixmap = self.icon().pixmap(self._iconSize, self.devicePixelRatio(), state, QIcon.Off)
        pixmapRect = QRect(QPoint(0, 0), self._iconSize)
        pixmapRect.moveCenter(self.rect().center())
        painter.drawPixmap(pixmapRect, pixmap)
