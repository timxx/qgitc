# -*- coding: utf-8 -*-

import typing

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyleOptionToolButton, QStylePainter, QToolButton


class ColoredIconToolButton(QToolButton):

    @typing.overload
    def __init__(self, icon: QIcon, iconSize: QSize, parent=None): ...

    @typing.overload
    def __init__(self, parent=None): ...

    def __init__(self, *args):
        if len(args) <= 1:
            super().__init__(args[0] if len(args) == 1 else None)
            self._icon = QIcon()
        elif len(args) == 2 or len(args) == 3:
            super().__init__(args[2] if len(args) == 3 else None)
            self._icon = args[0]
            self.setIconSize(args[1])
        else:
            raise TypeError("Invalid arguments")

        self.setToolButtonStyle(Qt.ToolButtonIconOnly)

    def setIcon(self, icon):
        self._icon = icon
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

        if self._icon.isNull():
            return

        pixmap = self._makePixmap()
        rect = QRect(QPoint(0, 0), opt.iconSize)

        style = self.toolButtonStyle()
        if style == Qt.ToolButtonIconOnly:
            rect.moveCenter(self.rect().center())
        elif style == Qt.ToolButtonTextBesideIcon:
            rect.moveTop(self.rect().top() + (self.height() - opt.iconSize.height()) / 2)
        else:
            assert ("Unsupported tool button style")
        painter.drawPixmap(rect, pixmap)

        if style == Qt.ToolButtonTextBesideIcon:
            opt.rect.setLeft(opt.iconSize.width())
            painter.drawControl(QStyle.CE_ToolButtonLabel, opt)

    def _makePixmap(self):
        pixmap = self._icon.pixmap(self.iconSize(), self.devicePixelRatio())

        p = QPainter(pixmap)
        p.setPen(Qt.NoPen)

        brush = self.palette().windowText()
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(pixmap.rect(), brush)
        p.end()

        return pixmap

    def sizeHint(self):
        size = self.iconSize() + QSize(2, 2)
        if self.toolButtonStyle() == Qt.ToolButtonTextBesideIcon:
            fm = self.fontMetrics()
            textSize = fm.size(Qt.TextShowMnemonic, self.text())
            textSize.setWidth(textSize.width() + fm.horizontalAdvance(' ') * 2)
            size.setWidth(size.width() + 4 + textSize.width())

        return size
