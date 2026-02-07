# -*- coding: utf-8 -*-

import typing

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFontMetrics, QMouseEvent, QPalette
from PySide6.QtWidgets import QStyle, QStyleOptionToolButton, QStylePainter, QWidget


class ElidedLabel(QWidget):
    """A custom label can shrink text with ellipsis when not enough space"""

    clicked = Signal()

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
        self._clickable = False
        self._hovered = False

        # Only used for clickable labels.
        self._padX = 6
        self._padY = 2

    def _elidedDisplayText(self) -> str:
        if not self._fullText:
            return ""
        fm = QFontMetrics(self.font())
        availWidth = self.width()
        if self._clickable:
            availWidth = max(0, availWidth - (self._padX * 2))
        return fm.elidedText(self._fullText, Qt.ElideRight, availWidth)

    def _textHitRect(self) -> QRect:
        """Return the local rect covering the (elided) drawn text plus padding."""
        text = self._elidedDisplayText()
        if not text:
            return QRect()

        fm = self.fontMetrics()
        textWidth = fm.horizontalAdvance(text)
        textHeight = fm.height()

        padX = self._padX if self._clickable else 0
        padY = self._padY if self._clickable else 0

        h = min(self.height(), textHeight + padY * 2)
        y = (self.height() - h) // 2
        w = min(self.width(), textWidth + padX * 2)
        return QRect(0, y, w, h)

    def _updateHoverFromPos(self, pos: QPoint):
        if not self._clickable:
            return

        hit = self._textHitRect().contains(pos)
        if hit != self._hovered:
            self._hovered = hit
            self.update()

        if hit:
            if self.cursor().shape() != Qt.PointingHandCursor:
                self.setCursor(Qt.PointingHandCursor)
        else:
            self.unsetCursor()

    def setClickable(self, clickable: bool):
        self._clickable = clickable
        self.setMouseTracking(clickable)

        self._hovered = False
        # Cursor/hover are updated dynamically based on whether the mouse is
        # over the text hit rect.
        self._updateHoverFromPos(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def setText(self, text: str):
        """Set the full text and trigger repaint"""
        self._fullText = text
        self.updateGeometry()
        self.update()

    def setTextColor(self, color: QColor):
        """Set the text color"""
        self._textColor = color
        self.update()

    def paintEvent(self, event):
        """Draw the elided text"""
        if not self._fullText:
            return

        painter = QStylePainter(self)

        if self._clickable:
            hitRect = self._textHitRect()

        if self._hovered and self.isEnabled() and hitRect.isValid():
            opt = QStyleOptionToolButton()
            opt.initFrom(self)
            opt.rect = hitRect
            opt.state |= QStyle.State_Raised
            opt.state |= QStyle.State_MouseOver
            painter.drawPrimitive(QStyle.PE_PanelButtonTool, opt)

        if self._textColor is None:
            painter.setPen(self.palette().color(QPalette.WindowText))
        else:
            painter.setPen(self._textColor)

        elidedText = self._elidedDisplayText()

        # Draw text vertically centered. For clickable/hover-enabled labels, keep
        # text aligned within the padded hit rect.
        if self._clickable and hitRect.isValid():
            textRect = hitRect.adjusted(self._padX, 0, -self._padX, 0)
        else:
            textRect = self.rect()
        painter.drawText(textRect, Qt.AlignLeft | Qt.AlignVCenter, elidedText)

    def mousePressEvent(self, event: QMouseEvent):
        if (
            self._clickable
            and event.button() == Qt.LeftButton
            and self._textHitRect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self._updateHoverFromPos(event.position().toPoint())
        super().mouseMoveEvent(event)

    def enterEvent(self, event: QEvent):
        self._updateHoverFromPos(self.mapFromGlobal(QCursor.pos()))
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent):
        if self._clickable:
            self._hovered = False
            self.update()
        super().leaveEvent(event)

    def sizeHint(self):
        """Preferred size for the full text"""
        if not self._fullText:
            return self.minimumSizeHint()

        fm = QFontMetrics(self.font())
        textWidth = fm.horizontalAdvance(self._fullText) + 1
        return QSize(textWidth, fm.height())
