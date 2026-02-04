# -*- coding: utf-8 -*-

import re

from PySide6.QtCore import (
    QAbstractAnimation,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    QTimer,
    Signal,
)
from PySide6.QtGui import QIcon, QKeySequence, QPainter, QPalette
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGridLayout,
    QLabel,
    QToolTip,
    QWidget,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.coloredicontoolbutton import ColoredIconToolButton
from qgitc.common import dataDirPath
from qgitc.findconstants import FindFlags
from qgitc.searchlineedit import SearchLineEdit


class FindPanel(QWidget):
    """A small find panel intended for QTextEdit/QPlainTextEdit-like widgets."""

    findRequested = Signal(str, int)
    nextRequested = Signal()
    previousRequested = Signal()
    afterHidden = Signal()

    def __init__(self, host: QWidget, parent: QWidget = None):
        super().__init__(parent)
        self._host = host
        self._flags = 0
        self._compactLayout = True

        self._setupUi()
        self._setupSignals()

        effect = QGraphicsDropShadowEffect(self)
        effect.setBlurRadius(15)
        effect.setOffset(1, 1)
        self.setGraphicsEffect(effect)

        self._host.installEventFilter(self)

        self._delayTimer = QTimer(self)
        self._delayTimer.setSingleShot(True)
        self._delayTimer.timeout.connect(self._doFind)

        self.updateStatus(0, 0, searching=False)

    def _setupUi(self):
        self._leFind = SearchLineEdit(self)

        def _newColoredButton(svg: str):
            fullPath = dataDirPath() + "/icons/" + svg
            icon = QIcon(fullPath)
            button = ColoredIconToolButton(icon, QSize(20, 20), self)
            button.setFixedSize(22, 22)
            return button

        self._tbPrev = _newColoredButton("arrow-up.svg")
        self._tbPrev.setShortcut(QKeySequence.FindPrevious)
        self._tbNext = _newColoredButton("arrow-down.svg")
        self._tbNext.setShortcut(QKeySequence.FindNext)
        self._tbClose = _newColoredButton("close.svg")
        self._lbStatus = QLabel(self)

        # Allow shrinking on small viewports.
        self._leFind.setMinimumWidth(120)

        self._layout = QGridLayout(self)
        margin = 3
        self._layout.setContentsMargins(margin, margin, margin, margin)
        self._layout.setHorizontalSpacing(margin)
        self._layout.setVerticalSpacing(margin)

        self._applyLayoutMode(compact=True)
        self.resize(self._getShowSize())

    def _setupSignals(self):
        self._leFind.textChanged.connect(self._onDelayFind)
        self._leFind.returnPressed.connect(self._onNextClicked)

        self._tbPrev.clicked.connect(self._onPreviousClicked)
        self._tbNext.clicked.connect(self._onNextClicked)
        self._tbClose.clicked.connect(self.hideAnimate)

        self._leFind.findFlagsChanged.connect(self._onFindFlagsChanged)

        # Track focus changes on all interactive children for auto-hide.
        self._leFind.installEventFilter(self)
        self._tbPrev.installEventFilter(self)
        self._tbNext.installEventFilter(self)
        self._tbClose.installEventFilter(self)

    def _applyLayoutMode(self, compact: bool):
        if self._compactLayout == compact and self._layout.count() > 0:
            return

        self._compactLayout = compact

        # Clear layout
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(self)

        # Columns: 0..4
        for col in range(0, 5):
            self._layout.setColumnStretch(col, 0)

        if compact:
            # Single row: [find][status][prev][next][close]
            self._layout.addWidget(self._leFind, 0, 0)
            self._layout.addWidget(self._lbStatus, 0, 1)
            self._layout.addWidget(self._tbPrev, 0, 2)
            self._layout.addWidget(self._tbNext, 0, 3)
            self._layout.addWidget(self._tbClose, 0, 4)
            self._layout.setColumnStretch(0, 1)
        else:
            # Two rows to avoid overlap on narrow docks.
            # Row 0: [find........................................]
            # Row 1: [status][spacer..................][prev][next][close]
            self._layout.addWidget(self._leFind, 0, 0, 1, 5)
            self._layout.addWidget(self._lbStatus, 1, 0)
            self._layout.addWidget(self._tbPrev, 1, 2)
            self._layout.addWidget(self._tbNext, 1, 3)
            self._layout.addWidget(self._tbClose, 1, 4)
            self._layout.setColumnStretch(1, 1)
            self._layout.setColumnStretch(0, 0)

    def _getShowSize(self) -> QSize:
        # Keep the panel fully visible even when the host viewport is narrow.
        idealWidth = 300
        hostWidth = self._host.width() if self._host else 0
        available = max(0, hostWidth - 4)
        width = idealWidth if available == 0 else min(idealWidth, available)
        width = max(0, int(width))

        # If the panel is narrow, switch to a 2-row layout so buttons never overlap the edit.
        self._applyLayoutMode(compact=(width >= 270))

        # Height depends on layout mode.
        if self._compactLayout:
            height = self._leFind.sizeHint().height() + 3 * 2
        else:
            row0 = self._leFind.sizeHint().height()
            row1 = max(self._tbPrev.sizeHint().height(), self._tbClose.sizeHint(
            ).height(), self._lbStatus.sizeHint().height())
            height = row0 + row1 + 3 * 3

        return QSize(int(width), int(height))

    def _getShowPos(self):
        pos = self._host.rect().topLeft()
        offset = self._host.width() - self.width()
        pos.setX(pos.x() + offset)
        pos.setY(pos.y() + 1)

        pos = self._host.mapToGlobal(pos)
        pos = self.parentWidget().mapFromGlobal(pos)

        # Clamp into the parent widget to avoid going off-screen.
        parent = self.parentWidget()
        if parent:
            maxX = max(0, parent.width() - self.width())
            pos.setX(max(0, min(pos.x(), maxX)))
        return pos

    def _updatePos(self):
        self.move(self._getShowPos())

    def _updateButtons(self, enable: bool):
        self._tbNext.setEnabled(enable)
        self._tbPrev.setEnabled(enable)

    def _doFind(self):
        self.findRequested.emit(self._leFind.text(), self.flags)

    def _verifyPattern(self, pattern: str) -> bool:
        try:
            re.compile(pattern)
            if QToolTip.isVisible():
                QToolTip.hideText()
            return True
        except re.error as e:
            self.updateStatus(0, 0, searching=False, invalidPattern=True)
            pos = self.mapToGlobal(QPoint(0, 10))
            text = self.tr("Invalid regular expression: ") + e.msg
            QToolTip.showText(pos, text)
            return False

    def _onDelayFind(self, text: str):
        if self.flags & FindFlags.UseRegExp:
            if not self._verifyPattern(text):
                return
        self._delayTimer.start(200)

    def _onFindFlagsChanged(self, flags: FindFlags):
        self._flags = flags
        if self._flags & FindFlags.UseRegExp:
            if not self._verifyPattern(self._leFind.text()):
                return
        self._doFind()

    def _onPreviousClicked(self):
        self.previousRequested.emit()

    def _onNextClicked(self):
        self.nextRequested.emit()

    def showAnimate(self):
        self.resize(self._getShowSize())
        self._updatePos()

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

    def setText(self, text: str):
        self._leFind.setText(text)

    @property
    def text(self) -> str:
        return self._leFind.text()

    @property
    def flags(self) -> int:
        return self._flags

    def updateStatus(self, currentIndex: int, totalCount: int, searching: bool = False, invalidPattern: bool = False):
        if invalidPattern:
            color = ApplicationBase.instance().colorSchema().ErrorText
            self._lbStatus.setText(self.tr("No results"))
        elif totalCount > 0:
            color = self.palette().windowText().color()
            self._lbStatus.setText(f"{currentIndex + 1}/{totalCount}")
        elif searching:
            color = self.palette().windowText().color()
            self._lbStatus.setText(self.tr("Finding..."))
        else:
            color = ApplicationBase.instance().colorSchema().ErrorText
            self._lbStatus.setText(self.tr("No results") if self.text else "")

        palette = self._lbStatus.palette()
        palette.setColor(self._lbStatus.foregroundRole(), color)
        self._lbStatus.setPalette(palette)
        self._updateButtons(totalCount > 0)

    def showEvent(self, event):
        self.resize(self._getShowSize())
        self._updatePos()
        self._leFind.setFocus()
        self._leFind.selectAll()

    def hideEvent(self, event):
        self.blockSignals(True)
        self._leFind.setText("")
        self.updateStatus(0, 0)
        self.blockSignals(False)
        self.afterHidden.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        rc = self.rect().adjusted(0, 0, -1, -1)
        palette = self.palette()
        painter.fillRect(rc, palette.window())
        painter.setPen(palette.color(QPalette.Inactive, QPalette.Window))
        painter.drawRect(rc)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            # Keep size/pos in sync with host changes.
            self.resize(self._getShowSize())
            self._updatePos()

        return super().eventFilter(obj, event)
