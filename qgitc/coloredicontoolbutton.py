# -*- coding: utf-8 -*-

import typing

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QIcon, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyleOptionToolButton, QStylePainter, QToolButton

from qgitc.drawutils import makeColoredIconPixmap


class ColoredIconToolButton(QToolButton):

    paddingLeft = 1
    paddingRight = 2
    extraSpacing = 1

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

    def chevronSize(self) -> int:
        return max(3, min(self.height() // 5, 4))

    def _menuIndicatorWidth(self) -> int:
        chevronSize = self.chevronSize()
        arrowWidth = chevronSize * 2
        return max(arrowWidth + self.paddingLeft + self.paddingRight + self.extraSpacing, 9)

    def paintEvent(self, event):
        painter = QStylePainter(self)

        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        hasMenu = opt.features & QStyleOptionToolButton.Menu
        buttonRect = self.rect()

        menuButtonIndicatorWidth = self._menuIndicatorWidth() if hasMenu else 0

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
                arrowPartRect = QRect(buttonRect.right() - menuButtonIndicatorWidth - 3,
                                        buttonRect.top(),
                                        menuButtonIndicatorWidth + 3,
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

        pixmap = makeColoredIconPixmap(self, self._icon, self.iconSize())
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

            chevronSize = self.chevronSize()
            arrowWidth = chevronSize * 2

            indicatorLeft = buttonRect.right() - menuButtonIndicatorWidth
            availableWidth = max(0, menuButtonIndicatorWidth - self.paddingLeft - self.paddingRight)
            centeredOffset = max(0, (availableWidth - arrowWidth) // 2)
            biasToLeft = 1
            arrowX = int(indicatorLeft + self.paddingLeft + max(0, centeredOffset - biasToLeft))
            arrowY = int(buttonRect.top() + ((buttonRect.height() - chevronSize) // 2) + 1)

            painter.drawLine(arrowX, arrowY, arrowX +
                             chevronSize, arrowY + chevronSize)
            painter.drawLine(arrowX + chevronSize, arrowY + chevronSize,
                             arrowX + arrowWidth, arrowY)

        if style == Qt.ToolButtonTextBesideIcon:
            opt.rect.setLeft(opt.iconSize.width())
            painter.drawControl(QStyle.CE_ToolButtonLabel, opt)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Track which part of the button is hovered"""
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        hasMenu = opt.features & QStyleOptionToolButton.Menu

        if hasMenu:
            menuButtonIndicatorWidth = self._menuIndicatorWidth()
            splitX = self.rect().right() - menuButtonIndicatorWidth

            if event.position().x() >= splitX:
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
            menuButtonIndicatorWidth = self._menuIndicatorWidth()
            size.setWidth(size.width() + menuButtonIndicatorWidth)

        return size
