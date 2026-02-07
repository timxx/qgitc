# -*- coding: utf-8 -*-

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from qgitc.applicationbase import ApplicationBase


def blend(a: QColor, b: QColor, t: float, alpha = 255) -> QColor:
    t = max(0.0, min(1.0, t))
    alpha = max(0, min(255, int(alpha)))

    return QColor(
        round(a.red() * (1.0 - t) + b.red() * t),
        round(a.green() * (1.0 - t) + b.green() * t),
        round(a.blue() * (1.0 - t) + b.blue() * t),
        alpha,
    )


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
                blended = blend(fg, bg, t, fg.alpha())
                adjusted = QBrush(brush)
                adjusted.setColor(blended)
                brush = adjusted

    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pixmap.rect(), brush)
    p.end()

    return pixmap


def drawRoundedRect(
        painter: QPainter, rect: QRectF, radius: float,
        borderColor: QColor, borderWidth: float = 1.0,
        borderStyle: Qt.BrushStyle = Qt.SolidPattern):
    painter.save()

    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(borderColor, borderStyle))

    outerPath = toRoundedPath(rect, radius)
    innerRect = rect.adjusted(borderWidth, borderWidth, -borderWidth, -borderWidth)
    innerPath = toRoundedPath(innerRect, max(0, radius - borderWidth))

    painter.drawPath(outerPath.subtracted(innerPath))

    painter.restore()


def toRoundedPath(rect: QRectF, radius: float):
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path
