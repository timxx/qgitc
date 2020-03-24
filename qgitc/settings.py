# -*- coding: utf-8 -*-

from PySide2.QtCore import (
    QSettings,
    Signal
)
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from .mergetool import MergeTool

import os


is_win = (os.name == "nt")


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

    showWhitespaceChanged = Signal(bool)
    ignoreWhitespaceChanged = Signal(int)

    def __init__(self, parent=None):
        super(Settings, self).__init__(
            QSettings.NativeFormat,
            QSettings.UserScope,
            "qgitc",
            parent=parent)

        self._fixedFont = fixedFont(QApplication.font().pointSize())

    def logViewFont(self):
        return self.value("lvFont", QApplication.font())

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
        self.showWhitespaceChanged.emit(show)

    def tabSize(self):
        return self.value("tabSize", 4, type=int)

    def setTabSize(self, size):
        self.setValue("tabSize", size)

    def quitViaEsc(self):
        return self.value("quitViaEsc", False, type=bool)

    def setQuitViaEsc(self, via):
        self.setValue("quitViaEsc", via)

    def rememberWindowState(self):
        return self.value("rememberWindowState", True, type=bool)

    def setRememberWindowState(self, remember):
        self.setValue("rememberWindowState", remember)

    def windowState(self):
        state = self.value("windowState", None)
        geometry = self.value("geometry", None)
        isMaximized = self.value("mwMaximized", True, type=bool)

        return state, geometry, isMaximized

    def setWindowState(self, state, geometry, isMaximized):
        self.setValue("windowState", state)
        # FIXME: make a common version
        if not isMaximized or is_win:
            self.setValue("geometry", geometry)
        self.setValue("mwMaximized", isMaximized)

    def gitViewState(self, isBranchA):
        key = "gvStateA" if isBranchA else "gvStateB"
        return self.value(key, None)

    def setGitViewState(self, state, isBranchA):
        key = "gvStateA" if isBranchA else "gvStateB"
        self.setValue(key, state)

    def diffViewState(self, isBranchA):
        key = "dvStateA" if isBranchA else "dvStateB"
        return self.value(key, None)

    def setDiffViewState(self, state, isBranchA):
        key = "dvStateA" if isBranchA else "dvStateB"
        self.setValue(key, state)

    def ignoreWhitespace(self):
        return self.value("ignoreWhitespace", 0, type=int)

    def setIgnoreWhitespace(self, index):
        self.setValue("ignoreWhitespace", index)
        self.ignoreWhitespaceChanged.emit(index)

    def mergeToolList(self):
        tools = [MergeTool(MergeTool.Nothing, ".png", "imgdiff"),
                 MergeTool(MergeTool.Nothing, ".jpg", "imgdiff")]
        return self.value("mergeTool", tools)

    def setMergeToolList(self, tools):
        self.setValue("mergeTool", tools)
