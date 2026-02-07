# -*- coding: utf-8 -*-

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from qgitc.applicationbase import ApplicationBase
from qgitc.drawutils import blend


class PopupWidget(QWidget):

    def __init__(self, radius: int = 6, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self._radius = radius
        self._contentWidget = None

        # Needed on Windows so the corners can be truly transparent.
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

    def setContentWidget(self, widget: QWidget):
        if self._contentWidget is widget:
            return

        if self._contentWidget is not None:
            self.layout().removeWidget(self._contentWidget)
            self._contentWidget.setParent(None)

        self._contentWidget = widget
        self.layout().addWidget(widget)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        palette = self.palette()
        base = palette.base().color()
        window = palette.window().color()

        # Slightly offset the popup background from the app background so it doesn't "disappear"
        # on dark themes, and keep it a touch translucent to visually blend with what's behind.
        app = ApplicationBase.instance()
        if app.isDarkTheme():
            bg = blend(base, QColor(255, 255, 255), 0.06)
            border = blend(bg, QColor(255, 255, 255), 0.22)
        else:
            bg = blend(base, QColor(0, 0, 0), 0.03)
            border = blend(bg, QColor(0, 0, 0), 0.20)

        # If the palette base/window are identical, nudge border a bit more.
        if base == window:
            if app.isDarkTheme():
                border = blend(border, QColor(255, 255, 255), 0.15)
            else:
                border = blend(border, QColor(0, 0, 0), 0.15)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(border, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, self._radius, self._radius)
