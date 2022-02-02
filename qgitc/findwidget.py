# -*- coding: utf-8 -*-

from PySide6.QtGui import *
from PySide6.QtWidgets import *
from PySide6.QtCore import *

from .textcursor import TextCursor
from .waitingspinnerwidget import QtWaitingSpinner
from .textviewer import FindPart, FindFlags
from .toggleiconbutton import ToggleIconButton
from .common import dataDirPath

import bisect


class FindWidget(QWidget):
    find = Signal(str, int)
    cursorChanged = Signal(TextCursor)
    afterHidden = Signal()

    def __init__(self, host, parent=None):
        super().__init__(parent)

        self._host = host
        self._findResult = []
        self._curIndex = 0
        self._searching = False
        self._flags = 0

        self._setupUi()
        self._setupSignals()

        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(15)
        offset = 1
        effect.setOffset(offset, offset)
        self.setGraphicsEffect(effect)

        self._host.installEventFilter(self)
        self.updateFindResult([], 0)

        self._delayTimer = QTimer(self)
        self._delayTimer.setSingleShot(True)
        self._delayTimer.timeout.connect(
            self._doFind)

    def _setupUi(self):
        self._leFind = QLineEdit(self)
        self._tbPrev = QToolButton(self)
        self._tbNext = QToolButton(self)
        self._tbClose = QToolButton(self)
        self._lbStatus = QLabel(self)
        self._spinner = QtWaitingSpinner(self)

        leFindHeight = self._leFind.sizeHint().height()
        self._leFind.setFixedSize(230, leFindHeight)

        height = self._leFind.height() // 6
        self._spinner.setLineLength(height)
        self._spinner.setInnerRadius(height)
        self._spinner.setNumberOfLines(14)

        hlayout = QHBoxLayout(self)
        margin = 3
        hlayout.setContentsMargins(margin, margin, margin, margin)
        hlayout.setSpacing(margin)

        hlayout.addWidget(self._leFind)
        hlayout.addWidget(self._spinner)
        hlayout.addWidget(self._lbStatus)
        hlayout.addSpacing(5)
        hlayout.addWidget(self._tbPrev)
        hlayout.addWidget(self._tbNext)
        hlayout.addWidget(self._tbClose)

        self._tbPrev.setText('🡩')
        self._tbNext.setText('🡫')
        self._tbClose.setText('⨉')

        self._setupFindEdit()
        self.resize(self._getShowSize())

    def _setupFindEdit(self):
        width = self.style().pixelMetric(QStyle.PM_LineEditIconSize)
        size = QSize(width, width)

        def _addAction(iconPath, tooltip):
            icon = QIcon(iconPath)
            button = ToggleIconButton(icon, size, self._leFind)
            button.setToolTip(tooltip)
            action = QWidgetAction(self._leFind)
            action.setDefaultWidget(button)
            self._leFind.addAction(action, QLineEdit.TrailingPosition)
            return button

        iconPath = dataDirPath() + "/icons"
        self._matchRegexSwitch = _addAction(
            iconPath + "/find-regex.svg",
            self.tr("Use Regular Expression"))
        self._matchWholeWordSwitch = _addAction(
            iconPath + "/find-whole-words.svg",
            self.tr("Match Whole Word"))
        self._matchCaseSwitch = _addAction(
            iconPath + "/find-case-senitively.svg",
            self.tr("Match Case"))

    def _setupSignals(self):
        self._leFind.textChanged.connect(self._onDelayFind)
        self._leFind.returnPressed.connect(self._onNextClicked)

        self._tbPrev.clicked.connect(self._onPreviousClicked)
        self._tbNext.clicked.connect(self._onNextClicked)
        self._tbClose.clicked.connect(self.hideAnimate)

        self._matchCaseSwitch.toggled.connect(self._onFindFlagsChanged)
        self._matchWholeWordSwitch.toggled.connect(self._onFindFlagsChanged)
        self._matchRegexSwitch.toggled.connect(self._onFindFlagsChanged)

    def _updateButtons(self, enable):
        self._tbNext.setEnabled(enable)
        self._tbPrev.setEnabled(enable)

    def _getShowSize(self):
        width = 400
        leFindHeight = self._leFind.sizeHint().height()
        margin = 3
        heigth = leFindHeight + margin * 2

        return QSize(width, heigth)

    def _getShowPos(self):
        pos = self._host.rect().topLeft()
        offset = self._host.width() - self.width()
        pos.setX(pos.x() + offset)
        pos.setY(pos.y() + 1)

        pos = self._host.mapToGlobal(pos)
        pos = self.parentWidget().mapFromGlobal(pos)

        return pos

    def _updatePos(self):
        self.move(self._getShowPos())

    def _doFind(self):
        self.find.emit(self._leFind.text(), self.flags)

    def _onDelayFind(self, text):
        self._delayTimer.start(200)

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

    def _onFindFlagsChanged(self, checked):
        self._flags = 0
        if self._matchCaseSwitch.isChecked():
            self._flags |= FindFlags.CaseSenitively
        if self._matchWholeWordSwitch.isChecked():
            self._flags |= FindFlags.WholeWords
        if self._matchRegexSwitch.isChecked():
            self._flags |= FindFlags.UseRegExp
        self._doFind()

    def _updateStatus(self):
        if self._findResult:
            color = Qt.black
            self._lbStatus.setText("{}/{}".format(
                self._curIndex + 1, len(self._findResult)))
        elif self._searching:
            color = Qt.black
            self._lbStatus.setText(self.tr("Finding..."))
        else:
            color = Qt.red
            self._lbStatus.setText(self.tr("No results"))

        palette = self._lbStatus.palette()
        palette.setColor(self._lbStatus.foregroundRole(), color)
        self._lbStatus.setPalette(palette)

    def showAnimate(self):
        self._leFind.setFocus()
        self._leFind.selectAll()
        if not self.isVisible():
            self.show()
            animation = QPropertyAnimation(self, b"geometry", self)
            animation.setDuration(150)
            pos = self._getShowPos()
            size = self._getShowSize()
            animation.setStartValue(QRect(pos, QSize(size.width(), 0)))
            animation.setEndValue(QRect(pos, size))
            animation.start(QAbstractAnimation.DeleteWhenStopped)

    def hideAnimate(self):
        animation = QPropertyAnimation(self, b"geometry", self)
        animation.setDuration(150)
        pos = self.pos()
        animation.setStartValue(QRect(pos, QSize(self.width(), self.height())))
        animation.setEndValue(QRect(pos, QSize(self.width(), 0)))
        animation.finished.connect(self.hide)
        animation.start(QAbstractAnimation.DeleteWhenStopped)

    def setText(self, text):
        self._leFind.setText(text)

    @property
    def text(self):
        return self._leFind.text()

    @property
    def flags(self):
        return self._flags

    def updateFindResult(self, result, curIndex=0, part=FindPart.All):
        if part in [FindPart.CurrentPage, FindPart.All]:
            self._findResult = result[:]
            if curIndex >= 0:
                self._curIndex = curIndex
        elif part == FindPart.BeforeCurPage:
            if curIndex >= 0:
                self._curIndex = curIndex
            else:
                self._curIndex += len(result)
            low = bisect.bisect_left(self._findResult, result[0])
            for i in range(0, len(result)):
                self._findResult.insert(low + i, result[i])
        else:
            if curIndex >= 0:
                self._curIndex = curIndex + len(self._findResult)
            self._findResult.extend(result)

        self._updateButtons(len(self._findResult) > 0)
        self._updateStatus()

    def findStarted(self):
        self._searching = True
        self._spinner.start()

    def findFinished(self):
        self._searching = False
        self._spinner.stop()

    def showEvent(self, event):
        self._updatePos()
        self._leFind.setFocus()
        self._leFind.selectAll()

    def hideEvent(self, event):
        # FIXME: control by caller?
        self.blockSignals(True)
        self._leFind.setText("")
        self.updateFindResult([])
        self.blockSignals(False)
        self.afterHidden.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        rc = self.rect().adjusted(0, 0, -1, -1)
        painter.fillRect(rc, Qt.white)
        painter.setPen(Qt.gray)
        painter.drawRect(rc)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self._updatePos()

        return super().eventFilter(obj, event)
