# -*- coding: utf-8 -*-

from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PySide2.QtCore import *
from .stylehelper import dpiScaled


class FindWidget(QWidget):
    find = Signal(str)
    findNext = Signal()
    findPrevious = Signal()

    def __init__(self, parent=None):
        super(FindWidget, self).__init__(
            parent, Qt.Popup | Qt.FramelessWindowHint)

        self.__setupUi()
        self.__setupSignals()

        self.setFocusPolicy(Qt.ClickFocus)
        self.setFocusProxy(self._leFind)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.__updateButtons(False)

    def __setupUi(self):
        self._leFind = QLineEdit(self)
        self._tbPrev = QToolButton(self)
        self._tbNext = QToolButton(self)

        hlayout = QHBoxLayout(self)
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.setSpacing(0)

        hlayout.addWidget(self._leFind)
        hlayout.addWidget(self._tbPrev)
        hlayout.addWidget(self._tbNext)

        self._tbPrev.setText('∧')
        self._tbNext.setText('∨')

    def __setupSignals(self):
        self._leFind.textChanged.connect(self.find)
        self._leFind.returnPressed.connect(self.findNext)

        self._tbPrev.clicked.connect(self.findPrevious)
        self._tbNext.clicked.connect(self.findNext)

    def __updateButtons(self, enable):
        self._tbNext.setEnabled(enable)
        self._tbPrev.setEnabled(enable)

    def showAnimate(self):
        # TODO: make it animate
        self.show()

    def hideAnimate(self):
        self.hide()

    def setText(self, text):
        self._leFind.setText(text)

    def updateFindStatus(self, found):
        palette = self._leFind.palette()
        color = Qt.white if found else QColor(255, 102, 102)
        palette.setColor(QPalette.Active, QPalette.Base, color)
        self._leFind.setPalette(palette)
        self.__updateButtons(found)

    def focusOutEvent(self, event):
        self.hideAnimate()

    def sizeHint(self):
        return QSize(dpiScaled(150), self._leFind.minimumSize().height())

    def showEvent(self, event):
        if isinstance(self.parent(), QAbstractScrollArea):
            viewport = self.parent().viewport()
        else:
            viewport = self.parent()
        pos = viewport.geometry().topLeft()
        pos = viewport.mapToGlobal(pos)

        offset = viewport.width() - self.width()
        pos.setX(pos.x() + offset)
        self.move(pos)
        self._leFind.setFocus()
        self._leFind.selectAll()
