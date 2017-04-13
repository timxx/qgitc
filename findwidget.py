# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *


# TODO: implement
class FindOption():
    CaseSensitive = 0x01
    WholeWordsOnly = 0x02
    UseRegEx = 0x04


class SearchBox(QLineEdit):

    def __init__(self, parent=None):
        super(SearchBox, self).__init__(parent)


class FindWidget(QWidget):
    find = pyqtSignal(str)
    findNext = pyqtSignal(bool)

    def __init__(self, parent=None):
        super(FindWidget, self).__init__(parent, Qt.Popup)

        self.setFocusPolicy(Qt.ClickFocus)
        self.resize(150, 24)

        self._options = 0

        self.__setupUi()
        self.__setupSignals()

    def __setupUi(self):
        self._sbox = SearchBox(self)
        self._tbPrev = QToolButton(self)
        self._tbNext = QToolButton(self)

        hlayout = QHBoxLayout(self)
        hlayout.setMargin(0)
        hlayout.setSpacing(0)

        hlayout.addWidget(self._sbox)
        hlayout.addWidget(self._tbPrev)
        hlayout.addWidget(self._tbNext)

        self._tbPrev.setText('∧')
        self._tbNext.setText('∨')
        # TODO: not supported at the moment
        self._tbPrev.setVisible(False)
        self._tbNext.setVisible(False)

    def __setupSignals(self):
        self._sbox.textChanged.connect(
            self.__onTextChanged)

        self._tbPrev.clicked.connect(
            self.__onPrevClicked)
        self._tbNext.clicked.connect(
            self.__onNextClicked)

    def __onTextChanged(self, text):
        self.doFind()

    def __onPrevClicked(self):
        self.findNext.emit(True)

    def __onNextClicked(self):
        self.findNext.emit(False)

    def doFind(self):
        text = self._sbox.text()
        self.find.emit(text)

    def showAnimate(self):
        # TODO: make it animate
        if isinstance(self.parent(), QAbstractScrollArea):
            viewport = self.parent().viewport()
        else:
            viewport = self.parent()
        pos = viewport.geometry().topLeft()
        pos = viewport.mapToGlobal(pos)

        offset = viewport.width() - self.width()
        pos.setX(pos.x() + offset)
        self.move(pos)
        self._sbox.setFocus()
        self._sbox.selectAll()
        self.show()

    def hideAnimate(self):
        self.hide()

    def setText(self, text):
        self._sbox.setText(text)

    def setNotFound(self):
        # TODO:
        pass

    def focusOutEvent(self, event):
        self.hideAnimate()
