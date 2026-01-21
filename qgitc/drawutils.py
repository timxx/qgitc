# -*- coding: utf-8 -*-

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QIcon, QPainter
from PySide6.QtWidgets import QWidget


def makeColoredIconPixmap(widget: QWidget, icon: QIcon, iconSize: QSize, brush: QBrush = None):
    pixmap = icon.pixmap(iconSize, widget.devicePixelRatio())

    p = QPainter(pixmap)
    p.setPen(Qt.NoPen)

    if brush is None:
        brush = widget.palette().windowText()
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pixmap.rect(), brush)
    p.end()

    return pixmap
