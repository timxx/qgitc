# -*- coding: utf-8 -*-

import typing
from PySide6.QtWidgets import (
    QToolButton, QStylePainter, QStyleOptionToolButton, QStyle)
from PySide6.QtGui import (QPainter, QIcon, QPen)
from PySide6.QtCore import (Qt, QSize, QRect, QPoint)


class ColoredIconToolButton(QToolButton):

    @typing.overload
    def __init__(self, icon: QIcon, iconSize: QSize, parent=None): ...

    @typing.overload
    def __init__(self, parent=None): ...

    def __init__(self, *args):
        if len(args) <= 1:
            super().__init__(args[0] if len(args) == 1 else None)
            self._icon = QIcon()
            self._iconSize = QSize()
        elif len(args) == 2 or len(args) == 3:
            super().__init__(args[2] if len(args) == 3 else None)
            self._icon = args[0]
            self._iconSize = args[1]
        else:
            raise TypeError("Invalid arguments")

        self.setToolButtonStyle(Qt.ToolButtonIconOnly)

    def setIcon(self, icon):
        self._icon = icon
        self.update()

    def setIconSize(self, size):
        self._iconSize = size
        self.update()

    def paintEvent(self, event):
        painter = QStylePainter(self)

        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)

        if (opt.state & QStyle.State_MouseOver) and (opt.state & QStyle.State_Enabled):
            painter.drawPrimitive(QStyle.PE_PanelButtonTool, opt)

        if opt.state & QStyle.State_On:
            oldPen = painter.pen()
            painter.setPen(QPen(self.palette().windowText().color()))
            rc = self.rect().adjusted(1, 1, -1, -1)
            painter.drawRect(rc)
            painter.setPen(oldPen)

        pixmap = self._makePixmap()
        rect = QRect(QPoint(0, 0), self._iconSize)
        rect.moveCenter(self.rect().center())
        painter.drawPixmap(rect, pixmap)

    def _makePixmap(self):
        pixmap = self._icon.pixmap(self._iconSize, self.devicePixelRatio())

        p = QPainter(pixmap)
        p.setPen(Qt.NoPen)

        brush = self.palette().windowText()
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(pixmap.rect(), brush)
        p.end()

        return pixmap
