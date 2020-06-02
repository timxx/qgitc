# -*- coding: utf-8 -*-

from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PySide2.QtCore import *
from .stylehelper import dpiScaled
from .textcursor import TextCursor


class FindWidget(QWidget):
    find = Signal(str)
    cursorChanged = Signal(TextCursor)
    afterHidden = Signal()

    def __init__(self, host, parent=None):
        super().__init__(parent)

        self._host = host
        self._findResult = []
        self._curIndex = 0

        self._setupUi()
        self._setupSignals()

        width = dpiScaled(280)
        heigth = self._leFind.height()
        self.resize(width, heigth)

        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(dpiScaled(15))
        offset = dpiScaled(1)
        effect.setOffset(offset, offset)
        self.setGraphicsEffect(effect)

        self._host.installEventFilter(self)
        self.updateFindResult([], 0)

    def _setupUi(self):
        self._leFind = QLineEdit(self)
        self._tbPrev = QToolButton(self)
        self._tbNext = QToolButton(self)
        self._tbClose = QToolButton(self)
        self._lbStatus = QLabel(self)

        hlayout = QHBoxLayout(self)
        margin = dpiScaled(3)
        hlayout.setContentsMargins(margin, margin, margin, margin)
        hlayout.setSpacing(margin)

        hlayout.addWidget(self._leFind)
        hlayout.addWidget(self._lbStatus)
        hlayout.addSpacing(dpiScaled(10))
        hlayout.addWidget(self._tbPrev)
        hlayout.addWidget(self._tbNext)
        hlayout.addWidget(self._tbClose)

        self._tbPrev.setText('∧')
        self._tbNext.setText('∨')
        self._tbClose.setText('X')

    def _setupSignals(self):
        self._leFind.textChanged.connect(self.find)
        self._leFind.returnPressed.connect(self._onNextClicked)

        self._tbPrev.clicked.connect(self._onPreviousClicked)
        self._tbNext.clicked.connect(self._onNextClicked)
        self._tbClose.clicked.connect(self.hideAnimate)

    def _updateButtons(self, enable):
        self._tbNext.setEnabled(enable)
        self._tbPrev.setEnabled(enable)

    def _updatePos(self):
        pos = self._host.rect().topLeft()
        offset = self._host.width() - self.width()
        pos.setX(pos.x() + offset)
        pos.setY(pos.y() + dpiScaled(1))

        pos = self._host.mapToGlobal(pos)
        pos = self.parentWidget().mapFromGlobal(pos)

        self.move(pos)

    def _onPreviousClicked(self):
        if not self._findResult:
            return

        self._curIndex -= 1
        if self._curIndex < 0:
            self._curIndex = len(self._findResult) - 1

        self._updateStatus()
        self.cursorChanged.emit(self._findResult[self._curIndex])

    def _onNextClicked(self):
        if not self._findResult:
            return

        self._curIndex += 1
        if self._curIndex >= len(self._findResult):
            self._curIndex = 0

        self._updateStatus()
        self.cursorChanged.emit(self._findResult[self._curIndex])

    def _updateStatus(self):
        if self._findResult:
            color = Qt.black
            self._lbStatus.setText("{}/{}".format(
                self._curIndex + 1, len(self._findResult)))
        else:
            color = Qt.red
            self._lbStatus.setText(self.tr("No results"))

        palette = self._lbStatus.palette()
        palette.setColor(self._lbStatus.foregroundRole(), color)
        self._lbStatus.setPalette(palette)

    def showAnimate(self):
        # TODO: make it animate
        self.show()

    def hideAnimate(self):
        self.hide()

    def setText(self, text):
        self._leFind.setText(text)

    def updateFindResult(self, result, curIndex):
        self._findResult = result
        self._curIndex = curIndex

        self._updateButtons(len(result) > 0)
        self._updateStatus()

    def showEvent(self, event):
        self._updatePos()
        self._leFind.setFocus()
        self._leFind.selectAll()

    def hideEvent(self, event):
        # FIXME: control by caller?
        self.blockSignals(True)
        self._leFind.setText("")
        self._findResult.clear()
        self.blockSignals(False)
        self.afterHidden.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        onePixel = dpiScaled(1)
        rc = self.rect().adjusted(0, 0, -onePixel, -onePixel)
        painter.fillRect(rc, Qt.white)
        painter.setPen(Qt.gray)
        painter.drawRect(rc)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self._updatePos()

        return super().eventFilter(obj, event)
