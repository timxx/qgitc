# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget


class FlowLayout(QLayout):
    """A simple wrapping layout (like words in a paragraph).

    Based on the canonical Qt Flow Layout example, adapted for PySide6.
    """

    def __init__(self, parent: QWidget = None, margin: int = 0, spacing: int = 4):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def __del__(self):
        item = self.takeAt(0)
        while item is not None:
            item = self.takeAt(0)

    def addItem(self, item: QLayoutItem):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._doLayout(QRect(0, 0, width, 0), testOnly=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._doLayout(rect, testOnly=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())

        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def _doLayout(self, rect: QRect, testOnly: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)

        x = effective.x()
        y = effective.y()
        lineHeight = 0

        spacing = self.spacing()
        if spacing < 0:
            spacing = 4

        for item in self._items:
            hint = item.sizeHint()
            nextX = x + hint.width() + spacing

            if lineHeight > 0 and nextX - spacing > effective.right():
                x = effective.x()
                y += lineHeight + spacing
                nextX = x + hint.width() + spacing
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = nextX
            lineHeight = max(lineHeight, hint.height())

        return (y + lineHeight - effective.y()) + bottom

    def invalidate(self):
        super().invalidate()
        for item in self._items:
            w = item.widget()
            if w is not None:
                w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
