# -*- coding: utf-8 -*-

import typing

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import QPushButton


class ColoredIconButton(QPushButton):

    @typing.overload
    def __init__(self, parent=None): ...

    @typing.overload
    def __init__(self, text: str, parent=None): ...

    @typing.overload
    def __init__(self, icon: QIcon, text: str, parent=None): ...

    def __init__(self, *args):
        super().__init__(*args)
        self._originalIcon = None

        if len(args) >= 2 and isinstance(args[0], QIcon):
            self.setIcon(args[0])

    def setIcon(self, icon):
        self._originalIcon = icon
        icon = QIcon(self._makePixmap())
        return super().setIcon(icon)

    def _makePixmap(self):
        pixmap = self.icon().pixmap(self.iconSize(), self.devicePixelRatio())

        p = QPainter(pixmap)
        p.setPen(Qt.NoPen)

        brush = self.palette().buttonText()
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(pixmap.rect(), brush)
        p.end()

        return pixmap

    def event(self, evt):
        if evt.type() == QEvent.PaletteChange:
            self.setIcon(self._originalIcon)
        return super().event(evt)
