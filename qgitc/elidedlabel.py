# -*- coding: utf-8 -*-

import typing

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import QWidget


class ElidedLabel(QWidget):
    """A custom label can shrink text with ellipsis when not enough space"""

    @typing.overload
    def __init__(self, parent=None): ...

    @typing.overload
    def __init__(self, text: str, parent=None): ...

    def __init__(self, *args):
        if len(args) == 0:
            parent = None
            text = ""
        elif len(args) == 1:
            if isinstance(args[0], str):
                text = args[0]
                parent = None
            else:
                parent = args[0]
                text = ""
        elif len(args) == 2:
            text = args[0]
            parent = args[1]
        else:
            raise TypeError("Invalid arguments")

        super().__init__(parent)
        self.setText(text)
        self._textColor = None

    def setText(self, text: str):
        """Set the full text and trigger repaint"""
        self._fullText = text
        self.updateGeometry()

    def setTextColor(self, color: QColor):
        """Set the text color"""
        self._textColor = color
        self.update()

    def paintEvent(self, event):
        """Draw the elided text"""
        if not self._fullText:
            return

        painter = QPainter(self)
        if self._textColor is None:
            painter.setPen(self.palette().color(QPalette.WindowText))
        else:
            painter.setPen(self._textColor)

        fm = painter.fontMetrics()
        elidedText = fm.elidedText(self._fullText, Qt.ElideRight, self.width())

        # Draw text vertically centered
        textRect = self.rect()
        painter.drawText(textRect, Qt.AlignLeft | Qt.AlignVCenter, elidedText)

    def sizeHint(self):
        """Preferred size for the full text"""
        if not self._fullText:
            return self.minimumSizeHint()

        fm = QFontMetrics(self.font())
        textWidth = fm.horizontalAdvance(self._fullText) + 1
        return QSize(textWidth, fm.height())
