# -*- coding: utf-8 -*-

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyleOptionToolButton

from qgitc.coloredicontoolbutton import ColoredIconToolButton
from qgitc.drawutils import makeColoredIconPixmap


class AiContextToolButton(ColoredIconToolButton):
    """Context chip button with split click behavior.

    - Clicking the icon area toggles selection (emits toggleRequested).
    - Clicking the text area emits activated.

    Hover highlight is only shown when hovering the icon area.
    Border is always drawn (dotted when unselected, solid when selected).
    """

    toggleRequested = Signal(str)
    activated = Signal(str)

    def __init__(
        self,
        contextId: str,
        label: str,
        addIcon: QIcon,
        removeIcon: QIcon,
        iconSize: QSize,
        parent=None,
    ):
        super().__init__(addIcon, iconSize, parent)

        self._contextId = contextId
        self._label = label
        self._addIcon = addIcon
        self._removeIcon = removeIcon
        self._selected = False

        self._hoverOnIcon = False

        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    def contextId(self) -> str:
        return self._contextId

    def setLabel(self, label: str):
        if self._label == label:
            return
        self._label = label
        self.updateGeometry()
        self.update()

    def label(self) -> str:
        return self._label

    def setSelected(self, selected: bool):
        if self._selected == selected:
            return
        self._selected = selected
        super().setIcon(self._removeIcon if selected else self._addIcon)
        self.update()

    def isSelected(self) -> bool:
        return self._selected

    def _iconClickRect(self) -> QRect:
        # A slightly larger hit area around the icon.
        w = self.iconSize().width() + 4 + 4
        return QRect(0, 0, w, self.height())

    def _textRect(self) -> QRect:
        r = self.rect()
        iconPart = self._iconClickRect()
        return r.adjusted(iconPart.width(), 0, 0, 0)

    def mouseMoveEvent(self, event: QMouseEvent):
        onIcon = self._iconClickRect().contains(event.position().toPoint())
        if onIcon != self._hoverOnIcon:
            self._hoverOnIcon = onIcon
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hoverOnIcon:
            self._hoverOnIcon = False
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            if self._iconClickRect().contains(pos):
                self.toggleRequested.emit(self._contextId)
                event.accept()
                return
            if self._textRect().contains(pos):
                self.activated.emit(self._contextId)
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)

        # Draw border (always)
        penStyle = Qt.SolidLine if self._selected else Qt.DotLine
        baseColor = QColor(self.palette().windowText().color())
        baseColor.setAlpha(100)

        painter.setPen(QPen(baseColor, 1, penStyle))
        borderRect = self.rect().adjusted(1, 1, -1, -1)
        painter.drawRoundedRect(borderRect, 4, 4)

        # Draw hover only for icon part.
        if (opt.state & QStyle.State_Enabled) and (opt.state & QStyle.State_MouseOver) and self._hoverOnIcon:
            hoverOpt = QStyleOptionToolButton(opt)
            hoverOpt.rect = self._iconClickRect()
            self.style().drawPrimitive(QStyle.PE_PanelButtonTool, hoverOpt, painter, self)

        # Draw icon
        iconRect = QRect(0, 0, self.iconSize().width(),
                         self.iconSize().height())
        iconRect.moveLeft(4)
        iconRect.moveTop((self.height() - iconRect.height()) // 2)
        pixmap = makeColoredIconPixmap(self, self._icon, self.iconSize())
        painter.drawPixmap(iconRect, pixmap)

        # Draw text
        textRect = self._textRect().adjusted(2, 0, -2, 0)
        painter.setPen(self.palette().windowText().color())
        elided = self.fontMetrics().elidedText(
            self._label, Qt.ElideRight, max(0, textRect.width()))
        painter.drawText(textRect, Qt.AlignVCenter | Qt.AlignLeft, elided)

        painter.end()

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        textW = fm.horizontalAdvance(self._label) + fm.horizontalAdvance("  ")
        w = 4 + self.iconSize().width() + 4 + textW + 4
        h = max(self.iconSize().height() + 6, fm.height() + 6)
        return QSize(w, h)
