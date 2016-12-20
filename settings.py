# -*- coding: utf-8 -*-

from PyQt4.QtCore import QSettings
from PyQt4.QtGui import *


def fixedFont(pointSize):
    """return a fixed font if available"""
    font = QFont("monospace", pointSize)

    font.setStyleHint(QFont.TypeWriter)
    fontInfo = QFontInfo(font)
    if fontInfo.fixedPitch():
        return QFont(fontInfo.family(), pointSize)

    font.setStyleHint(QFont.Monospace)
    fontInfo = QFontInfo(font)
    if fontInfo.fixedPitch():
        return QFont(fontInfo.family(), pointSize)

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

    def commitColorA(self):
        return self.value("colorA", QColor(255, 0, 0))

    def setCommitColorA(self, color):
        self.setValue("colorA", color)

    def commitColorB(self):
        return self.value("colorB", QColor(112, 48, 160))

    def setCommitColorB(self, color):
        self.setValue("colorB", color)

    def commitUrl(self):
        return self.value("commitUrl", "")

    def setCommitUrl(self, url):
        self.setValue("commitUrl", url)

    def bugUrl(self):
        return self.value("bugUrl", "")

    def setBugUrl(self, url):
        self.setValue("bugUrl", url)

    def bugPattern(self):
        return self.value("bugPattern", "")

    def setBugPattern(self, pattern):
        self.setValue("bugPattern", pattern)

    def showWhitespace(self):
        return self.value("showWhitespace", True, type=bool)

    def setShowWhitespace(self, show):
        self.setValue("showWhitespace", show)

    def tabSize(self):
        return self.value("tabSize", 4, type=int)

    def setTabSize(self, size):
        self.setValue("tabSize", size)
