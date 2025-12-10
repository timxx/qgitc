# -*- coding: utf-8 -*-

import hashlib
import logging
import os
import platform
import uuid
from typing import List, Tuple

from PySide6.QtCore import QSettings, Signal
from PySide6.QtGui import QColor, QFont, QFontInfo
from PySide6.QtWidgets import QApplication

from qgitc.commitactiontablemodel import CommitAction
from qgitc.mergetool import MergeTool

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


def chineseFont():
    if is_win:
        defaultFont = "Microsoft YaHei UI"
    elif platform.system() == "Darwin":
        defaultFont = "PingFang SC"
    else:
        defaultFont = "WenQuanYi Micro Hei"

    return defaultFont


class Settings(QSettings):

    showWhitespaceChanged = Signal(bool)
    ignoreWhitespaceChanged = Signal(int)
    logViewFontChanged = Signal(QFont)
    diffViewFontChanged = Signal(QFont)
    bugPatternChanged = Signal()
    fallbackGlobalChanged = Signal(bool)
    tabSizeChanged = Signal(int)
    compositeModeChanged = Signal(bool)
    colorSchemaModeChanged = Signal(int)
    ignoreCommentLineChanged = Signal(bool)
    useNtpTimeChanged = Signal(bool)

    def __init__(self, parent=None, testing=False):
        super().__init__(
            QSettings.NativeFormat,
            QSettings.UserScope,
            "qgitc",
            "test" if testing else "",
            parent=parent)

        self.setFallbacksEnabled(False)
        self._fixedFont = None

    @staticmethod
    def _makeFont(families: List[str], pointSize: int):
        font = QFont()
        font.setFamilies(families)
        font.setPointSize(pointSize)
        return font

    def logViewFont(self):
        families = self.value("lvFonts", [])
        fontSize = self.value(
            "lvFontSize", QApplication.font().pointSize(), type=int)
        if not families:
            families = QApplication.font().families()
            extraFamiliy = chineseFont()
            if extraFamiliy not in families:
                families.append(extraFamiliy)
        return self._makeFont(families, fontSize)

    def setLogViewFont(self, font: QFont):
        # we can't save font directly
        # as the family will be lost
        self.setValue("lvFonts", font.families())
        self.setValue("lvFontSize", font.pointSize())
        self.logViewFontChanged.emit(font)

    def diffViewFont(self):
        families = self.value("dvFonts", [])
        fontSize = self.value(
            "dvFontSize", QApplication.font().pointSize(), type=int)
        if not families:
            if self._fixedFont is None:
                self._fixedFont = fixedFont(QApplication.font().pointSize())
            families = self._fixedFont.families()
            extraFamiliy = chineseFont()
            if extraFamiliy not in families:
                families.append(extraFamiliy)
        return self._makeFont(families, fontSize)

    def setDiffViewFont(self, font: QFont):
        self.setValue("dvFonts", font.families())
        self.setValue("dvFontSize", font.pointSize())
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

    def setBugPatterns(self, repoName: str, patterns: List[Tuple[str, str]]):
        self.setLinkValue(repoName, "bugPatterns", patterns)
        self.bugPatternChanged.emit()

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

    def windowState(self, windowName, maximized=True):
        self.beginGroup(windowName)
        state = self.value("state", None)
        geometry = self.value("geometry", None)
        isMaximized = self.value("maximized", maximized, type=bool)
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

    def localLlmServer(self):
        self.beginGroup("llm")
        value = self.value("localServer", "http://127.0.0.1:23719/v1")
        self.endGroup()
        return value

    def setLocalLlmServer(self, server):
        self.beginGroup("llm")
        self.setValue("localServer", server)
        self.endGroup()

    def defaultLlmModel(self):
        self.beginGroup("llm")
        value = self.value("defaultModel", "GithubCopilot")
        self.endGroup()
        return value

    def setDefaultLlmModel(self, model: str):
        self.beginGroup("llm")
        self.setValue("defaultModel", model)
        self.endGroup()

    def defaultLlmModelId(self, modelKey: str):
        self.beginGroup("llm")
        self.beginGroup("defaultModelId")
        value = self.value(modelKey, None)
        self.endGroup()
        self.endGroup()
        return value

    def setDefaultLlmModelId(self, modelKey: str, modelId: str):
        self.beginGroup("llm")
        self.beginGroup("defaultModelId")
        self.setValue(modelKey, modelId)
        self.endGroup()
        self.endGroup()

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
        if not repoDir:
            return []

        key = os.path.normpath(os.path.normcase(repoDir))
        self.beginGroup("submodulesCache")
        cache = self.value(key, [])
        if cache is None:
            cache = []
        self.endGroup()
        return cache

    def setSubmodulesCache(self, repoDir, cache: List[str]):
        key = os.path.normpath(os.path.normcase(repoDir))
        self.beginGroup("submodulesCache")
        self.setValue(key, cache)
        self.endGroup()

    def saveSplitterState(self, splitter, state):
        self.beginGroup("splitterState")
        self.setValue(splitter, state)
        self.endGroup()

    def getSplitterState(self, splitter):
        self.beginGroup("splitterState")
        state = self.value(splitter, None)
        self.endGroup()
        return state

    def ignoreCommentLine(self):
        self.beginGroup("commit")
        ignore = self.value("ignoreCommentLine", True, type=bool)
        self.endGroup()
        return ignore

    def setIgnoreCommentLine(self, ignore):
        if ignore == self.ignoreCommentLine():
            return
        self.beginGroup("commit")
        self.setValue("ignoreCommentLine", ignore)
        self.endGroup()
        self.ignoreCommentLineChanged.emit(ignore)

    def tabToNextGroup(self):
        self.beginGroup("commit")
        value = self.value("tabToNextGroup", True, type=bool)
        self.endGroup()
        return value

    def setTabToNextGroup(self, tab):
        self.beginGroup("commit")
        self.setValue("tabToNextGroup", tab)
        self.endGroup()

    def groupChars(self):
        self.beginGroup("commit")
        chars = self.value("groupChars", "【】 []")
        self.endGroup()
        return chars

    def setGroupChars(self, chars):
        self.beginGroup("commit")
        self.setValue("groupChars", chars)
        self.endGroup()

    def useNtpTime(self):
        self.beginGroup("commit")
        use = self.value("useNtpTime", False, type=bool)
        self.endGroup()
        return use

    def setUseNtpTime(self, use: bool):
        if use == self.useNtpTime():
            return

        self.beginGroup("commit")
        self.setValue("useNtpTime", use)
        self.endGroup()
        self.useNtpTimeChanged.emit(use)

    def commitActions(self, repoName: str) -> List[CommitAction]:
        self.beginGroup(repoName)
        defaultActions = [CommitAction("git", "push", enabled=False)]
        actions = self.value("actions", defaultActions)
        self.endGroup()
        return actions

    def setCommitActions(self, repoName: str, actions: List[CommitAction]):
        self.beginGroup(repoName)
        self.setValue("actions", actions)
        self.endGroup()

    def globalCommitActions(self) -> List[CommitAction]:
        self.beginGroup("commit")
        actions = self.value("actions", [])
        self.endGroup()
        return actions

    def setGlobalCommitActions(self, actions: List[CommitAction]):
        self.beginGroup("commit")
        self.setValue("actions", actions)
        self.endGroup()

    def useGlobalCommitActions(self):
        self.beginGroup("commit")
        use = self.value("useGlobalActions", False, type=bool)
        self.endGroup()
        return use

    def setUseGlobalCommitActions(self, use):
        self.beginGroup("commit")
        self.setValue("useGlobalActions", use)
        self.endGroup()

    def runCommitActions(self):
        self.beginGroup("commit")
        run = self.value("runActions", False, type=bool)
        self.endGroup()
        return run

    def setRunCommitActions(self, run):
        self.beginGroup("commit")
        self.setValue("runActions", run)
        self.endGroup()

    def showUntrackedFiles(self):
        self.beginGroup("commit")
        show = self.value("showUntrackedFiles", True, type=bool)
        self.endGroup()
        return show

    def setShowUntrackedFiles(self, show):
        self.beginGroup("commit")
        self.setValue("showUntrackedFiles", show)
        self.endGroup()

    def showIgnoredFiles(self):
        self.beginGroup("commit")
        show = self.value("showIgnoredFiles", False, type=bool)
        self.endGroup()
        return show

    def setShowIgnoredFiles(self, show):
        self.beginGroup("commit")
        self.setValue("showIgnoredFiles", show)
        self.endGroup()

    def githubCopilotAccessToken(self):
        self.beginGroup("GithubCopilot")
        token = self.value("accessToken", None)
        self.endGroup()
        return token

    def setGithubCopilotAccessToken(self, token: str):
        self.beginGroup("GithubCopilot")
        self.setValue("accessToken", token)
        self.endGroup()

    def githubCopilotToken(self):
        self.beginGroup("GithubCopilot")
        token = self.value("token", None)
        self.endGroup()
        return token

    def setGithubCopilotToken(self, token: str):
        self.beginGroup("GithubCopilot")
        self.setValue("token", token)
        self.endGroup()

    def setLogLevel(self, level):
        self.setValue("logLevel", level)

    def logLevel(self):
        return self.value("logLevel", logging.WARNING, type=int)

    def aiExcludedFileExtensions(self):
        return self.value("aiExcludedFileExtensions", [])

    def setAiExcludedFileExtensions(self, extensions: List[str]):
        self.setValue("aiExcludedFileExtensions", extensions)

    def styleName(self):
        return self.value("styleName", "")

    def setStyleName(self, style):
        self.setValue("styleName", style)

    def language(self) -> str:
        return self.value("language", "")

    def setLanguage(self, lang: str):
        self.setValue("language", lang)

    def isTelemetryEnabled(self) -> bool:
        self.beginGroup("telemetry")
        value = self.value("enableTelemetry", True, type=bool)
        self.endGroup()
        return value

    def setTelemetryEnabled(self, enabled: bool):
        self.beginGroup("telemetry")
        self.setValue("enableTelemetry", enabled)
        self.endGroup()

    @staticmethod
    def _endPointHash(endpoint: str) -> str:
        m = hashlib.md5()
        m.update(endpoint.encode('utf-8'))
        return m.hexdigest()

    def isTelemetryServerConnectable(self, endpoint: str):
        self.beginGroup("telemetry")
        key = Settings._endPointHash(endpoint)
        if self.contains(key):
            value = self.value(key, False, type=bool)
        else:
            value = None
        self.endGroup()
        return value

    def setTelemetryServerConnectable(self, endpoint: str, connectable: bool):
        self.beginGroup("telemetry")
        key = Settings._endPointHash(endpoint)
        self.setValue(key, connectable)
        self.endGroup()

    def lastTelemetryServerCheck(self):
        self.beginGroup("telemetry")
        value = self.value("lastCheck", 0, type=int)
        self.endGroup()
        return value

    def setLastTelemetryServerCheck(self, datetime: int):
        self.beginGroup("telemetry")
        self.setValue("lastCheck", datetime)
        self.endGroup()

    def userId(self) -> str:
        self.beginGroup("telemetry")
        userId = self.value("userId", "")
        if not userId:
            userId = str(uuid.uuid4())
            self.setValue("userId", userId)
        self.endGroup()
        return userId

    def setDetectLocalChanges(self, detect: bool):
        self.setValue("detectLocalChanges", detect)

    def detectLocalChanges(self) -> bool:
        return self.value("detectLocalChanges", True, type=bool)

    def setShowFetchSlowAlert(self, show: bool):
        self.setValue("showFetchSlowAlert", show)

    def showFetchSlowAlert(self) -> bool:
        return self.value("showFetchSlowAlert", True, type=bool)

    def recentRepositories(self) -> List[str]:
        """Get list of recently visited repositories"""
        return self.value("recentRepositories", [])

    def setRecentRepositories(self, repos: List[str]):
        """Set list of recently visited repositories"""
        self.setValue("recentRepositories", repos)

    def addRecentRepository(self, repoPath: str, maxRecentRepos: int = 10):
        """Add a repository to the recent list, moving it to front if already exists"""
        if not repoPath:
            return

        normalRepoPath = os.path.normpath(os.path.normcase(repoPath))
        recent = self.recentRepositories()

        # Remove if already exists
        for repo in recent:
            if os.path.normpath(os.path.normcase(repo)) == normalRepoPath:
                recent.remove(repo)
                break

        # Add to front
        recent.insert(0, repoPath)

        # Limit to maxRecentRepos
        if len(recent) > maxRecentRepos:
            recent = recent[:maxRecentRepos]

        self.setRecentRepositories(recent)

    def chatHistories(self):
        """Get saved chat histories"""
        self.beginGroup("AiChat")
        self.beginGroup("histories")
        histories = []
        for key in self.allKeys():
            value = self.value(key)
            if value:
                histories.append(value)
        self.endGroup()
        self.endGroup()
        return histories

    def saveChatHistory(self, historyId: str, historyData: dict):
        """Save a chat history session"""
        self.beginGroup("AiChat")
        self.beginGroup("histories")
        self.setValue(historyId, historyData)
        self.endGroup()
        self.endGroup()

    def removeChatHistory(self, historyId: str):
        """Remove a chat history session"""
        self.beginGroup("AiChat")
        self.beginGroup("histories")
        self.remove(historyId)
        self.endGroup()
        self.endGroup()

    # Cherry-Pick Settings Group
    def recordOrigin(self):
        """Whether to record origin commit SHA in cherry-picked commit message"""
        self.beginGroup("cherryPick")
        value = self.value("recordOrigin", True, type=bool)
        self.endGroup()
        return value

    def setRecordOrigin(self, record: bool):
        self.beginGroup("cherryPick")
        self.setValue("recordOrigin", record)
        self.endGroup()

    def filterRevertedCommits(self):
        """Whether to filter out reverted commits when cherry-picking"""
        self.beginGroup("cherryPick")
        value = self.value("filterReverted", False, type=bool)
        self.endGroup()
        return value

    def setFilterRevertedCommits(self, filter: bool):
        self.beginGroup("cherryPick")
        self.setValue("filterReverted", filter)
        self.endGroup()

    def filterCommitPatterns(self):
        """Get the list of patterns to filter commits"""
        self.beginGroup("cherryPick")
        size = self.beginReadArray("filterPatterns")
        patterns = []
        for i in range(size):
            self.setArrayIndex(i)
            pattern = self.value("pattern", "", type=str)
            if pattern:
                patterns.append(pattern)
        self.endArray()
        self.endGroup()
        return patterns

    def setFilterCommitPatterns(self, patterns: list):
        """Set the list of patterns to filter commits"""
        self.beginGroup("cherryPick")
        self.beginWriteArray("filterPatterns")
        for i, pattern in enumerate(patterns):
            self.setArrayIndex(i)
            self.setValue("pattern", pattern)
        self.endArray()
        self.endGroup()

    def filterUseRegex(self):
        """Whether to use regex for pattern matching"""
        self.beginGroup("cherryPick")
        value = self.value("filterUseRegex", False, type=bool)
        self.endGroup()
        return value

    def setFilterUseRegex(self, useRegex: bool):
        self.beginGroup("cherryPick")
        self.setValue("filterUseRegex", useRegex)
        self.endGroup()

    def applyFilterByDefault(self):
        """Whether to apply cherry-pick filter automatically when loading commits"""
        self.beginGroup("cherryPick")
        value = self.value("applyFilterByDefault", False, type=bool)
        self.endGroup()
        return value

    def setApplyFilterByDefault(self, apply: bool):
        self.beginGroup("cherryPick")
        self.setValue("applyFilterByDefault", apply)
        self.endGroup()

    def confirmCheckoutFiles(self):
        """Whether to show confirmation dialog when checking out files"""
        self.beginGroup("commit")
        value = self.value("confirmCheckoutFiles", True, type=bool)
        self.endGroup()
        return value

    def setConfirmCheckoutFiles(self, confirm: bool):
        self.beginGroup("commit")
        self.setValue("confirmCheckoutFiles", confirm)
        self.endGroup()

    def confirmRestoreFiles(self):
        """Whether to show confirmation dialog when restoring files"""
        self.beginGroup("commit")
        value = self.value("confirmRestoreFiles", True, type=bool)
        self.endGroup()
        return value

    def setConfirmRestoreFiles(self, confirm: bool):
        self.beginGroup("commit")
        self.setValue("confirmRestoreFiles", confirm)
        self.endGroup()

    def confirmDeleteFiles(self):
        """Whether to show confirmation dialog when deleting files"""
        self.beginGroup("commit")
        value = self.value("confirmDeleteFiles", True, type=bool)
        self.endGroup()
        return value

    def setConfirmDeleteFiles(self, confirm: bool):
        self.beginGroup("commit")
        self.setValue("confirmDeleteFiles", confirm)
        self.endGroup()
