# -*- coding: utf-8 -*-

from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt


class ColorWidget(QWidget):

    def __init__(self, parent=None):
        super(ColorWidget, self).__init__(parent)
        self.color = QColor(Qt.black)

        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)

    def setColor(self, color):
        self.color = color
        self.update()

    def getColor(self):
        return self.color

    def paintEvent(self, event):
        painter = QStylePainter(self)

        painter.fillRect(self.rect(), self.color)

        if self.hasFocus():
            option = QStyleOptionFocusRect()
            option.initFrom(self)
            painter.drawPrimitive(QStyle.PE_FrameFocusRect, option)

    def mouseReleaseEvent(self, event):
        colorDlg = QColorDialog(self.color, self)
        if colorDlg.exec() != QDialog.Accepted:
            return

        self.color = colorDlg.currentColor()
        self.update()
