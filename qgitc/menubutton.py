# -*- coding: utf-8 -*-

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QStyle, QStyleOptionToolButton, QStylePainter, QToolButton


class MenuButton(QToolButton):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setAutoRaise(True)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

    def paintEvent(self, event):
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)

        painter = QStylePainter(self)

        if (opt.state & QStyle.State_MouseOver) and (opt.state & QStyle.State_Enabled):
            painter.drawPrimitive(QStyle.PE_PanelButtonTool, opt)

        opt.state &= ~QStyle.State_Sunken

        fm = self.fontMetrics()
        textSize = fm.size(Qt.TextShowMnemonic, self.text())
        spaces = fm.horizontalAdvance(' ') * 2

        labelOpt = QStyleOptionToolButton(opt)
        labelOpt.rect.setWidth(textSize.width() + spaces)
        painter.drawControl(QStyle.CE_ToolButtonLabel, labelOpt)

        w = textSize.height() // 2
        opt.rect.setLeft(textSize.width() + spaces)
        opt.rect.setWidth(w)

        painter.drawPrimitive(QStyle.PE_IndicatorArrowDown, opt)

    def sizeHint(self):
        self.ensurePolished()

        w = 0
        h = 0
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)

        if opt.toolButtonStyle != Qt.ToolButtonTextOnly:
            w = opt.iconSize.width()
            h = opt.iconSize.height()

        if opt.toolButtonStyle != Qt.ToolButtonIconOnly:
            fm = self.fontMetrics()
            textSize = fm.size(Qt.TextShowMnemonic, self.text())
            textSize.setWidth(textSize.width() + fm.horizontalAdvance(' ') * 2)
            w += textSize.width()
            if textSize.height() > h:
                h = textSize.height()

            # indicator
            w += textSize.height() // 3

        sizeHint = self.style().sizeFromContents(
            QStyle.CT_ToolButton, opt, QSize(w, h), self)
        return sizeHint
