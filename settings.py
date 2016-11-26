# -*- coding: utf-8 -*-

from PyQt4.QtCore import QSettings
from PyQt4.QtGui import *


def fixedFont(pointSize):
    """return a fixed font if available"""
    font = QFont("monospace", pointSize)

    font.setStyleHint(QFont.TypeWriter)
    if QFontInfo(font).fixedPitch():
        return font

    font.setStyleHint(QFont.Monospace)
    if QFontInfo(font).fixedPitch():
        return font

    # for Windows
    font.setFamily("Courier")
    return font


class Settings(QSettings):

    def __init__(self, parent=None):
        super(Settings, self).__init__(
            QSettings.NativeFormat,
            QSettings.UserScope,
            "gitc",
            parent=parent)

        self._fixedFont = fixedFont(QApplication.font().pointSize())

    def logViewFont(self):
        font = self.value("lvFont", QApplication.font())
        return font

    def setLogViewFont(self, font):
        self.setValue("lvFont", font)

    def diffViewFont(self):
        font = self.value("dvFont", self._fixedFont)
        return font

    def setDiffViewFont(self, font):
        self.setValue("dvFont", font)
