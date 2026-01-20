# -*- coding: utf-8 -*-

import typing

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyleOptionToolButton, QStylePainter, QToolButton


class ColoredIconToolButton(QToolButton):

    @typing.overload
    def __init__(self, icon: QIcon, iconSize: QSize, parent=None): ...

    @typing.overload
    def __init__(self, parent=None): ...

    def __init__(self, *args):
        if len(args) <= 1:
            super().__init__(args[0] if len(args) == 1 else None)
            self._icon = QIcon()
        elif len(args) == 2 or len(args) == 3:
            super().__init__(args[2] if len(args) == 3 else None)
            self._icon = args[0]
            self.setIconSize(args[1])
        else:
            raise TypeError("Invalid arguments")

        self.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.setMouseTracking(True)
        self._hoverOnArrow = False
        self._hoverOnButton = False

    def setIcon(self, icon):
        self._icon = icon
        self.update()

    def paintEvent(self, event):
        painter = QStylePainter(self)

        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        hasMenu = opt.features & QStyleOptionToolButton.Menu
        buttonRect = self.rect()

        # Calculate menu button indicator width
        menuButtonIndicatorWidth = 0
        if hasMenu:
            menuButtonIndicatorWidth = self.style().pixelMetric(
                QStyle.PM_MenuButtonIndicator, opt, self)

        # Draw split hover states if enabled and has menu
        if (opt.state & QStyle.State_MouseOver) and (opt.state & QStyle.State_Enabled):
            painter.drawPrimitive(QStyle.PE_PanelButtonTool, opt)
            if self._hoverOnButton:
                buttonPartRect = buttonRect.adjusted(
                    0, 0, -menuButtonIndicatorWidth, 0)
                opt.rect = buttonPartRect
                painter.drawPrimitive(QStyle.PE_PanelButtonTool, opt)
                opt.rect = buttonRect
            elif self._hoverOnArrow:
                arrowPartRect = QRect(buttonRect.right() - menuButtonIndicatorWidth,
                                        buttonRect.top(),
                                        menuButtonIndicatorWidth,
                                        buttonRect.height())
                opt.rect = arrowPartRect
                painter.drawPrimitive(QStyle.PE_PanelButtonTool, opt)
                opt.rect = buttonRect

        if opt.state & QStyle.State_On:
            oldPen = painter.pen()
            painter.setPen(QPen(self.palette().windowText().color()))
            rc = self.rect().adjusted(1, 1, -1, -1)
            painter.drawRect(rc)
            painter.setPen(oldPen)

        if self._icon.isNull():
            return

        pixmap = self._makePixmap()
        rect = QRect(QPoint(0, 0), opt.iconSize)

        style = self.toolButtonStyle()
        if style == Qt.ToolButtonIconOnly:
            # Adjust icon position if menu indicator is present
            if hasMenu:
                # Shift icon to the left to make room for menu indicator
                availableWidth = buttonRect.width() - menuButtonIndicatorWidth
                rect.moveLeft((availableWidth - opt.iconSize.width()) // 2)
                rect.moveTop(
                    (buttonRect.height() - opt.iconSize.height()) // 2)
            else:
                rect.moveCenter(buttonRect.center())
        elif style == Qt.ToolButtonTextBesideIcon:
            rect.moveTop(buttonRect.top() +
                         (self.height() - opt.iconSize.height()) / 2)
        else:
            assert ("Unsupported tool button style")
        painter.drawPixmap(rect, pixmap)

        # Draw menu arrow if present
        if hasMenu:
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setPen(QPen(self.palette().windowText().color(), 1))

            arrowHeight = min(buttonRect.height() // 3, 6)
            chevronSize = arrowHeight
            arrowWidth = chevronSize * 2

            arrowX = buttonRect.right() - menuButtonIndicatorWidth // 2 - chevronSize
            arrowY = buttonRect.top() + (buttonRect.height() - chevronSize) / 2 + 1

            painter.drawLine(arrowX, arrowY, arrowX +
                             chevronSize, arrowY + chevronSize)
            painter.drawLine(arrowX + chevronSize, arrowY + chevronSize,
                             arrowX + arrowWidth, arrowY)

        if style == Qt.ToolButtonTextBesideIcon:
            opt.rect.setLeft(opt.iconSize.width())
            painter.drawControl(QStyle.CE_ToolButtonLabel, opt)

    def mouseMoveEvent(self, event):
        """Track which part of the button is hovered"""
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        hasMenu = opt.features & QStyleOptionToolButton.Menu

        if hasMenu:
            menuButtonIndicatorWidth = self.style().pixelMetric(
                QStyle.PM_MenuButtonIndicator, opt, self)
            splitX = self.rect().right() - menuButtonIndicatorWidth

            if event.pos().x() >= splitX:
                if not self._hoverOnArrow:
                    self._hoverOnArrow = True
                    self._hoverOnButton = False
                    self.update()
            else:
                if not self._hoverOnButton:
                    self._hoverOnButton = True
                    self._hoverOnArrow = False
                    self.update()
        else:
            self._hoverOnButton = False
            self._hoverOnArrow = False

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        """Clear hover states when mouse leaves"""
        if self._hoverOnArrow or self._hoverOnButton:
            self._hoverOnArrow = False
            self._hoverOnButton = False
            self.update()
        super().leaveEvent(event)

    def _makePixmap(self):
        pixmap = self._icon.pixmap(self.iconSize(), self.devicePixelRatio())

        p = QPainter(pixmap)
        p.setPen(Qt.NoPen)

        brush = self.palette().windowText()
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(pixmap.rect(), brush)
        p.end()

        return pixmap

    def sizeHint(self):
        size = self.iconSize() + QSize(2, 2)
        if self.toolButtonStyle() == Qt.ToolButtonTextBesideIcon:
            fm = self.fontMetrics()
            textSize = fm.size(Qt.TextShowMnemonic, self.text())
            textSize.setWidth(textSize.width() + fm.horizontalAdvance(' ') * 2)
            size.setWidth(size.width() + 4 + textSize.width())

        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        if opt.features & QStyleOptionToolButton.Menu:
            menuButtonIndicatorWidth = self.style().pixelMetric(
                QStyle.PM_MenuButtonIndicator, opt, self)
            size.setWidth(size.width() + menuButtonIndicatorWidth)

        return size
