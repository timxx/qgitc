# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QToolButton
from PySide6.QtGui import (QPainter, QIcon, QPen, QPalette)
from PySide6.QtCore import (QRect, QPoint, Qt)


class ToggleIconButton(QToolButton):

    def __init__(self, icon, iconSize, parent=None):
        super().__init__(parent)
        self._iconSize = iconSize
        self.setIcon(icon)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._isColoredIcon = True

    def setColoredIcon(self, isColoredIcon):
        self._isColoredIcon = isColoredIcon
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        palette = self.palette()

        if self.isChecked():
            oldPen = painter.pen()
            painter.setPen(QPen(palette.windowText().color(), 1))
            rc = self.rect().adjusted(1, 1, -1, -1)
            painter.drawRect(rc)
            painter.setPen(oldPen)

        state = QIcon.Disabled
        if self.isEnabled():
            state = QIcon.Active if self.isDown() else QIcon.Normal
        pixmap = self.icon().pixmap(self._iconSize, self.devicePixelRatio(), state, QIcon.Off)
        pixmapRect = QRect(QPoint(0, 0), self._iconSize)
        pixmapRect.moveCenter(self.rect().center())

        if self._isColoredIcon and qApp.isDarkTheme():
            p = QPainter(pixmap)
            p.setPen(Qt.NoPen)
            group = QPalette.Disabled
            if self.isEnabled():
                group = QPalette.Active if self.isDown() else QPalette.Normal

            brush = palette.brush(group, QPalette.WindowText)
            p.setCompositionMode(QPainter.CompositionMode_SourceIn)
            p.fillRect(pixmap.rect(), brush)
            p.end()

        painter.drawPixmap(pixmapRect, pixmap)
