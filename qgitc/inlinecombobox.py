# -*- coding: utf-8 -*-

from typing import List, Tuple

from PySide6.QtCore import QElapsedTimer, QEvent, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QListWidget,
    QMenu,
    QWidget,
    QWidgetAction,
)

from qgitc.applicationbase import ApplicationBase


class InlineComboBox(QWidget):
    """
    A custom inline combobox that:
    - Sizes based on current item text (not longest)
    - Can shrink to show only arrow when squeezed
    - Shows elided text when space is tight
    - Popup adjusts to longest item (clamped to screen)
    - Custom border: transparent → visible on hover/focus
    """

    currentIndexChanged = Signal(int)
    popupClosed = Signal()  # Emitted when popup is closed after selection

    ArrowWidth = 8
    Spacing = 4
    # Extra padding to avoid text eliding even when enough space
    ExtraPadding = 2

    def __init__(self, parent=None):
        super().__init__(parent)

        # List of (text, userData) tuples
        self._items: List[Tuple[str, object]] = []
        self._currentIndex = -1
        self._isHovered = False
        self._popupVisible = False
        self._popup = None
        self._popupTimer = QElapsedTimer()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setContentsMargins(4, 4, 4, 4)
        self.setCursor(Qt.PointingHandCursor)

    def addItem(self, text: str, userData=None):
        """Add an item to the combobox"""
        self._items.append((text, userData))
        if self._currentIndex == -1:
            self.setCurrentIndex(0)
        self.updateGeometry()

    def clear(self):
        """Clear all items"""
        self._items.clear()
        self._currentIndex = -1
        self.update()
        self.updateGeometry()

    def count(self):
        """Return number of items"""
        return len(self._items)

    def currentIndex(self):
        """Return current selected index"""
        return self._currentIndex

    def setCurrentIndex(self, index: int):
        """Set current selected index"""
        if 0 <= index < len(self._items):
            if self._currentIndex != index:
                self._currentIndex = index
                self.update()
                self.currentIndexChanged.emit(index)
                self.updateGeometry()

    def currentText(self):
        """Return current item text"""
        if 0 <= self._currentIndex < len(self._items):
            return self._items[self._currentIndex][0]
        return ""

    def currentData(self):
        """Return current item user data"""
        if 0 <= self._currentIndex < len(self._items):
            return self._items[self._currentIndex][1]
        return None

    def itemText(self, index: int):
        """Return text at index"""
        if 0 <= index < len(self._items):
            return self._items[index][0]
        return ""

    def itemData(self, index: int):
        """Return user data at index"""
        if 0 <= index < len(self._items):
            return self._items[index][1]
        return None

    def setCurrentText(self, text: str):
        """Set current item by text"""
        for i, (itemText, _) in enumerate(self._items):
            if itemText == text:
                self.setCurrentIndex(i)
                return

    def findData(self, userData):
        """Find index by user data. Returns -1 if not found."""
        for i, (_, data) in enumerate(self._items):
            if data is userData:
                return i
        return -1

    def sizeHint(self):
        """Return preferred size based on current text"""
        fm = self.fontMetrics()
        textWidth = fm.horizontalAdvance(self.currentText())
        margins = self.contentsMargins()

        width = margins.left() + textWidth + self.ExtraPadding + \
            self.Spacing + self.ArrowWidth + margins.right()
        height = fm.height() + margins.top() + margins.bottom()

        return QSize(width, height)

    def minimumSizeHint(self):
        """Return minimum size: just arrow and padding"""
        fm = QFontMetrics(self.font())
        margins = self.contentsMargins()

        width = margins.left() + self.Spacing + self.ArrowWidth + margins.right()
        height = fm.height() + margins.top() + margins.bottom()

        return QSize(width, height)

    def enterEvent(self, event):
        """Track hover state"""
        self._isHovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Track hover state"""
        self._isHovered = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event):
        """Repaint on focus"""
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        """Repaint on focus loss"""
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event):
        """Custom paint for border, text, and arrow"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect())
        borderRect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 4

        palette = self.palette()
        if not self.isEnabled():
            pass
        elif self.hasFocus():
            pen = QPen(palette.highlight().color())
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(borderRect, radius, radius)
        elif self._isHovered:
            app = ApplicationBase.instance()
            if app.isDarkTheme():
                pen = Qt.NoPen
            else:
                outline = palette.window().color().darker(140)
                pen = QPen(outline)
                pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(palette.button().color())
            painter.drawRoundedRect(borderRect, radius, radius)

        # Calculate text and arrow areas
        margins = self.contentsMargins()

        # Draw elided text
        text = self.currentText()
        if text:
            textRect = rect.adjusted(
                margins.left(),
                margins.top(),
                -(self.ArrowWidth + self.Spacing + margins.right()),
                -margins.bottom()
            )

            fm = self.fontMetrics()
            elidedText = fm.elidedText(text, Qt.ElideRight, textRect.width())

            painter.setPen(palette.text().color())
            painter.drawText(textRect, Qt.AlignLeft |
                             Qt.AlignVCenter, elidedText)

        # Draw arrow
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(QPen(palette.text().color(), 1))
        chevronSize = self.ArrowWidth // 2
        arrowX = rect.right() - margins.right() - self.ArrowWidth
        arrowY = rect.top() + (rect.height() - chevronSize) / 2 + 1
        painter.drawLine(arrowX, arrowY, arrowX +
                         chevronSize, arrowY + chevronSize)
        painter.drawLine(arrowX + chevronSize, arrowY +
                         chevronSize, arrowX + 2 * chevronSize, arrowY)

    def mousePressEvent(self, event: QMouseEvent):
        """Show popup on click"""
        if event.button() == Qt.LeftButton:
            # Avoid immediate re-show on popup close
            # WA_NoMouseReplay is useless here
            if not self._popupTimer.isValid() or \
                    self._popupTimer.elapsed() > 100:
                self._showPopup()
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard navigation"""
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Down):
            self._showPopup()
        elif event.key() == Qt.Key_Up:
            # Navigate up
            if self._currentIndex > 0:
                self.setCurrentIndex(self._currentIndex - 1)
        else:
            super().keyPressEvent(event)

    def eventFilter(self, watched, event: QEvent):
        """Handle events from the popup list widget"""
        if self._popupVisible and isinstance(watched, QListWidget):
            if event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Return:
                    # Select current item and close popup
                    currentRow = watched.currentRow()
                    if currentRow >= 0:
                        self.setCurrentIndex(currentRow)
                    if self._popup:
                        self._popup.close()
                    self.popupClosed.emit()
                    return True
        return super().eventFilter(watched, event)

    def _showPopup(self):
        """Show the popup list"""
        if self._popupVisible or len(self._items) == 0:
            return

        self._popup = QMenu(self)
        self._popup.setAttribute(Qt.WA_DeleteOnClose)

        # List widget
        listWidget = QListWidget(self._popup)
        listWidget.setFrameShape(QFrame.StyledPanel)

        # Add items
        for text, _ in self._items:
            listWidget.addItem(text)

        # Select current item
        if self._currentIndex >= 0:
            listWidget.setCurrentRow(self._currentIndex)

        # Connect signals
        listWidget.itemClicked.connect(self._onPopupItemClicked)
        # Install event filter to handle Enter key
        listWidget.installEventFilter(self)

        action = QWidgetAction(self._popup)
        action.setDefaultWidget(listWidget)
        self._popup.addAction(action)

        # Calculate popup width (longest item, clamped to screen)
        fm = QFontMetrics(self.font())
        maxWidth = max(fm.horizontalAdvance(text)
                       for text, _ in self._items) if self._items else 100
        maxWidth += 40  # scrollbar + margins

        # Clamp to screen
        screen = QApplication.screenAt(self.mapToGlobal(self.rect().center()))
        if screen:
            screenGeometry = screen.availableGeometry()
            maxWidth = min(maxWidth, screenGeometry.width() - 40)

        # At least as wide as the widget
        maxWidth = max(maxWidth, self.width())

        # Calculate exact height needed for items (up to max of 10 visible rows)
        viewportHeight = 0
        for i in range(min(10, listWidget.count())):
            viewportHeight += listWidget.sizeHintForRow(i)

        frameWidth = listWidget.frameWidth() * 2
        popupHeight = viewportHeight + frameWidth
        listWidget.setFixedSize(maxWidth, popupHeight)

        # Position below widget (or above if not enough space)
        globalPos = self.mapToGlobal(QPoint(0, self.height()))

        if screen:
            screenGeometry = screen.availableGeometry()
            if globalPos.y() + popupHeight > screenGeometry.bottom():
                # Show above
                globalPos = self.mapToGlobal(QPoint(0, -popupHeight))

        self._popupVisible = True
        self._popup.destroyed.connect(self._onPopupClosed)
        self.update()  # Redraw border
        self._popup.popup(globalPos)
        listWidget.setFocus()
        self._popupTimer.invalidate()

    def _onPopupItemClicked(self, item):
        """Handle item selection in popup"""
        listWidget = self.sender()
        index = listWidget.row(item)
        self.setCurrentIndex(index)
        if self._popup:
            self._popup.close()
        self._popupTimer.invalidate()
        # Emit signal after popup closes so parent can restore focus
        self.popupClosed.emit()

    def _onPopupClosed(self):
        """Handle popup closed"""
        self._popupVisible = False
        self._popup = None
        self.update()  # Redraw border
        self._popupTimer.restart()
