# -*- coding: utf-8 -*-

from typing import List
from PySide6.QtCore import (
    QSettings,
    Signal)
from PySide6.QtGui import (
    QFont,
    QFontInfo,
    QColor)
from PySide6.QtWidgets import (
    QApplication)
from .mergetool import MergeTool

import os
import platform


is_win = (os.name == "nt")


def fixedFont(pointSize):
    """return a fixed font if available"""
    if is_win:
        default_font = "Consolas"
    elif platform.system() == "Darwin":
        default_font = "Menlo"
    else:
        default_font = "Monospace"

    font = QFont(default_font, pointSize)

    font.setStyleHint(QFont.TypeWriter)
    fontInfo = QFontInfo(font)
    if fontInfo.fixedPitch():
        return QFont(fontInfo.family(), pointSize)

    font.setStyleHint(QFont.Monospace)
    fontInfo = QFontInfo(font)
    if fontInfo.fixedPitch():
        return QFont(fontInfo.family(), pointSize)

    font.setFamily("Courier New")
    return font


class Settings(QSettings):

    showWhitespaceChanged = Signal(bool)
    ignoreWhitespaceChanged = Signal(int)
    logViewFontChanged = Signal(QFont)
    diffViewFontChanged = Signal(QFont)
    bugPatternChanged = Signal(str)
    fallbackGlobalChanged = Signal(bool)
    tabSizeChanged = Signal(int)
    compositeModeChanged = Signal(bool)
    colorSchemaModeChanged = Signal(int)

    def __init__(self, parent=None):
        super(Settings, self).__init__(
            QSettings.NativeFormat,
            QSettings.UserScope,
            "qgitc",
            parent=parent)

        self._fixedFont = None

    def logViewFont(self):
        return self.value("lvFont", QApplication.font())

    def setLogViewFont(self, font):
        self.setValue("lvFont", font)
        self.logViewFontChanged.emit(font)

    def diffViewFont(self):
        font = self.value("dvFont", None, QFont)
        if font is None:
            if self._fixedFont is None:
                self._fixedFont = fixedFont(QApplication.font().pointSize())
            return self._fixedFont
        return font

    def setDiffViewFont(self, font):
        self.setValue("dvFont", font)
        self.diffViewFontChanged.emit(font)

    def commitColorA(self):
        return self.value("colorA", QColor(255, 0, 0))

    def setCommitColorA(self, color):
        self.setValue("colorA", color)

    def commitColorB(self):
        return self.value("colorB", QColor(112, 48, 160))

    def setCommitColorB(self, color):
        self.setValue("colorB", color)

    def _linkGroup(self, repoName):
        return repoName if repoName else "Global"

    def getLinkValue(self, repoName, key, default=None, type=None):
        self.beginGroup(self._linkGroup(repoName))
        if type is not None:  # BUG!!!
            value = self.value(key, default, type=type)
        else:
            value = self.value(key, default)
        self.endGroup()
        return value

    def setLinkValue(self, repoName, key, value):
        self.beginGroup(self._linkGroup(repoName))
        self.setValue(key, value)
        self.endGroup()

    def commitUrl(self, repoName):
        return self.getLinkValue(repoName, "commitUrl", "")

    def setCommitUrl(self, repoName, url):
        self.setLinkValue(repoName, "commitUrl", url)

    def setBugPatterns(self, repoName, patterns):
        self.setLinkValue(repoName, "bugPatterns", patterns)
        self.bugPatternChanged.emit(patterns)

    def bugPatterns(self, repoName):
        patterns = self.getLinkValue(repoName, "bugPatterns", None)
        if patterns is not None:
            return patterns

        # keep the old settings
        url = self.getLinkValue(repoName, "bugUrl", "")
        pattern = self.getLinkValue(repoName, "bugPattern", "")
        if pattern:
            return [(pattern, url)]
        return None

    def fallbackGlobalLinks(self, repoName):
        return self.getLinkValue(repoName, "fallback", True, type=bool)

    def setFallbackGlobalLinks(self, repoName, fallback):
        self.setLinkValue(repoName, "fallback", fallback)
        self.fallbackGlobalChanged.emit(fallback)

    def showWhitespace(self):
        return self.value("showWhitespace", True, type=bool)

    def setShowWhitespace(self, show):
        self.setValue("showWhitespace", show)
        self.showWhitespaceChanged.emit(show)

    def tabSize(self):
        return self.value("tabSize", 4, type=int)

    def setTabSize(self, size):
        self.setValue("tabSize", size)
        self.tabSizeChanged.emit(size)

    def quitViaEsc(self):
        return self.value("quitViaEsc", False, type=bool)

    def setQuitViaEsc(self, via):
        self.setValue("quitViaEsc", via)

    def rememberWindowState(self):
        return self.value("rememberWindowState", True, type=bool)

    def setRememberWindowState(self, remember):
        self.setValue("rememberWindowState", remember)

    def windowState(self, windowName):
        self.beginGroup(windowName)
        state = self.value("state", None)
        geometry = self.value("geometry", None)
        isMaximized = self.value("maximized", True, type=bool)
        self.endGroup()

        return state, geometry, isMaximized

    def setWindowState(self, windowName, state, geometry, isMaximized):
        self.beginGroup(windowName)
        self.setValue("state", state)
        # FIXME: make a common version
        if not isMaximized or is_win:
            self.setValue("geometry", geometry)
        self.setValue("maximized", isMaximized)
        self.endGroup()

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

    def ignoredVersion(self):
        return self.value("ignoredVersion", "")

    def setIgnoredVersion(self, version):
        self.setValue("ignoredVersion", version)

    def lastCheck(self):
        return self.value("lastCheck", 0, type=int)

    def setLastCheck(self, datetime):
        self.setValue("lastCheck", datetime)

    def checkUpdatesEnabled(self):
        return self.value("checkUpdates", True, type=bool)

    def setCheckUpdatesEnabled(self, enabled):
        self.setValue("checkUpdates", enabled)

    def checkUpdatesInterval(self):
        return self.value("checkInterval", 1, type=int)

    def setCheckUpdatesInterval(self, days):
        self.setValue("checkInterval", days)

    def diffToolName(self):
        return self.value("diffToolName", "")

    def setDiffToolName(self, name):
        self.setValue("diffToolName", name)

    def mergeToolName(self):
        return self.value("mergeToolName", "")

    def setMergeToolName(self, name):
        self.setValue("mergeToolName", name)

    def gitBinPath(self):
        return self.value("gitBin", "")

    def setGitBinPath(self, path):
        self.setValue("gitBin", path)

    def isFullCommitMessage(self):
        return self.value("fullCommitMsg", False, type=bool)

    def setFullCommitMessage(self, full):
        self.setValue("fullCommitMsg", full)

    def llmServer(self):
        return self.value("llmServer", "http://127.0.0.1:23719/v1")

    def setLlmServer(self, server):
        self.setValue("llmServer", server)

    def isCompositeMode(self):
        return self.value("compositeMode", False, type=bool)

    def setCompositeMode(self, composite):
        self.setValue("compositeMode", composite)
        self.compositeModeChanged.emit(composite)

    def maxCompositeCommitsSince(self):
        return self.value("maxCompositeCommitsSince", 365, type=int)

    def setMaxCompositeCommitsSince(self, days):
        self.setValue("maxCompositeCommitsSince", days)

    def showParentChild(self):
        return self.value("showParentChild", True, type=bool)

    def setShowParentChild(self, show):
        self.setValue("showParentChild", show)

    def colorSchemaMode(self):
        return self.value("colorSchemaMode", 0, type=int)

    def setColorSchemaMode(self, mode):
        oldMode = self.colorSchemaMode()
        if mode != oldMode:
            self.setValue("colorSchemaMode", mode)
            self.colorSchemaModeChanged.emit(mode)

    def submodulesCache(self, repoDir):
        key = os.path.normpath(os.path.normcase(repoDir))
        self.beginGroup("submodulesCache")
        cache = self.value(key, [])
        self.endGroup()
        return cache

    def setSubmodulesCache(self, repoDir, cache: List[str]):
        key = os.path.normpath(os.path.normcase(repoDir))
        self.beginGroup("submodulesCache")
        self.setValue(key, cache)
        self.endGroup()
