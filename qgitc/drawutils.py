# -*- coding: utf-8 -*-

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter
from PySide6.QtWidgets import QWidget

from qgitc.applicationbase import ApplicationBase


def makeColoredIconPixmap(widget: QWidget, icon: QIcon, iconSize: QSize, brush: QBrush = None):
    pixmap = icon.pixmap(iconSize, widget.devicePixelRatio())

    p = QPainter(pixmap)
    p.setPen(Qt.NoPen)

    if brush is None:
        palette = widget.palette()
        brush = palette.windowText()
        app = ApplicationBase.instance()
        if not app.isDarkTheme():
            # On light theme the palette text color is often pure black, which can look too heavy
            # for toolbar/button icons. Instead of QColor.lighter/darker (which tends to be subtle
            # for near-black), blend toward the widget background.
            bg = palette.color(widget.backgroundRole())
            if not bg.isValid() or bg.alpha() == 0:
                bg = palette.window().color()

            fg = brush.color()
            # Only adjust when the foreground is a near-black, low-saturation color.
            if fg.isValid() and fg.alpha() > 0 and fg.value() < 80 and fg.saturation() < 50:
                t = 0.25  # 0 → original fg, 1 → background
                blended = QColor(
                    round(fg.red() * (1.0 - t) + bg.red() * t),
                    round(fg.green() * (1.0 - t) + bg.green() * t),
                    round(fg.blue() * (1.0 - t) + bg.blue() * t),
                    fg.alpha(),
                )

                adjusted = QBrush(brush)
                adjusted.setColor(blended)
                brush = adjusted

    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pixmap.rect(), brush)
    p.end()

    return pixmap
