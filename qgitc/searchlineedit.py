# -*- coding: utf-8 -*-

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLineEdit, QStyle, QWidgetAction

from qgitc.coloredicontoolbutton import ColoredIconToolButton
from qgitc.common import dataDirPath
from qgitc.findconstants import FindFlags


class SearchLineEdit(QLineEdit):
    """
    A reusable QLineEdit with search capabilities including regex, whole word,
    and case sensitive matching options.
    """
    findFlagsChanged = Signal(FindFlags)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextMargins(1, 1, 2, 2)

        self._matchRegexSwitch = None
        self._matchWholeWordSwitch = None
        self._matchCaseSwitch = None

        self._setupActions()

    def _setupActions(self):
        width = self.style().pixelMetric(QStyle.PM_LineEditIconSize)
        size = QSize(width, width)

        iconPath = dataDirPath() + "/icons"
        self._matchRegexSwitch = self._addAction(
            iconPath + "/find-regex.svg",
            self.tr("Use Regular Expression"),
            size)
        self._matchWholeWordSwitch = self._addAction(
            iconPath + "/find-whole-words.svg",
            self.tr("Match Whole Word"),
            size)
        self._matchCaseSwitch = self._addAction(
            iconPath + "/find-case-senitively.svg",
            self.tr("Match Case"),
            size)

        self._matchRegexSwitch.toggled.connect(self._onFindFlagsChanged)
        self._matchWholeWordSwitch.toggled.connect(self._onFindFlagsChanged)
        self._matchCaseSwitch.toggled.connect(self._onFindFlagsChanged)

    def _addAction(self, iconPath, tooltip, size):
        icon = QIcon(iconPath)
        button = ColoredIconToolButton(icon, size, self)
        button.setToolTip(tooltip)
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        action = QWidgetAction(self)
        action.setDefaultWidget(button)
        self.addAction(action, QLineEdit.TrailingPosition)
        return button

    @property
    def matchRegexSwitch(self):
        return self._matchRegexSwitch

    @property
    def matchWholeWordSwitch(self):
        return self._matchWholeWordSwitch

    @property
    def matchCaseSwitch(self):
        return self._matchCaseSwitch

    @property
    def findFlags(self):
        flags = 0
        if self._matchRegexSwitch.isChecked():
            flags |= FindFlags.UseRegExp
        if self._matchWholeWordSwitch.isChecked():
            flags |= FindFlags.WholeWords
        if self._matchCaseSwitch.isChecked():
            flags |= FindFlags.CaseSenitively
        return flags

    def _onFindFlagsChanged(self):
        self.findFlagsChanged.emit(self.findFlags)
