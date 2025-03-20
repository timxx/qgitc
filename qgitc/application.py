# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon, QDesktopServices, QPalette
from PySide6.QtCore import (
    Qt,
    QTranslator,
    QLibraryInfo,
    QLocale,
    QUrl,
    QTimer,
    qVersion,
    QEvent)

from .aichatwindow import AiChatWindow
from .colorschema import ColorSchemaDark, ColorSchemaLight, ColorSchemaMode
from .common import dataDirPath
from .settings import Settings
from .events import (
    BlameEvent,
    CodeReviewEvent,
    ShowCommitEvent,
    OpenLinkEvent,
    GitBinChanged)
from .blamewindow import BlameWindow
from .mainwindow import MainWindow
from .gitutils import Git
from .textline import Link
from .versionchecker import VersionChecker
from .newversiondialog import NewVersionDialog

from datetime import datetime
from .findwidget import FindWidget

import os
import shutil


def qtVersion():
    return tuple(map(int, qVersion().split('.')))


class Application(QApplication):

    LogWindow = 1
    BlameWindow = 2
    AiAssistant = 3

    def __init__(self, argv):
        super(Application, self).__init__(argv)

        self.setAttribute(Qt.AA_DontShowIconsInMenus, False)
        self.setAttribute(Qt.AA_DontUseNativeMenuBar, True)
        self.setApplicationName("qgitc")

        iconPath = dataDirPath() + "/icons/qgitc.svg"
        self.setWindowIcon(QIcon(iconPath))

        self.setupTranslator()
        self._settings = Settings(self)

        self._logWindow = None
        self._blameWindow = None
        self._aiChatWindow = None

        gitBin = self._settings.gitBinPath() or shutil.which("git")
        if not gitBin or not os.path.exists(gitBin):
            QTimer.singleShot(0, self._warnGitMissing)
        else:
            self._initGit(gitBin)

        QTimer.singleShot(0, self._onDelayInit)

        self._lastFocusWidget = None
        self.focusChanged.connect(self._onFocusChanged)

        self.overrideColorSchema(self._settings.colorSchemaMode())

        self._colorSchema = None
        self._isDarkTheme = False
        self._setupColorSchema()

        self._settings.colorSchemaModeChanged.connect(
            self.overrideColorSchema)

    def settings(self):
        return self._settings

    def setupTranslator(self):
        # the Qt translations
        dirPath = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
        translator = QTranslator(self)
        if translator.load(QLocale.system(), "qt", "_", dirPath):
            self.installTranslator(translator)
        else:
            translator = None

        translator = QTranslator(self)
        dirPath = dataDirPath() + "/translations"
        if translator.load(QLocale.system(), "", "", dirPath):
            self.installTranslator(translator)
        else:
            translator = None

    def getWindow(self, type):
        window = None
        if type == Application.LogWindow:
            if not self._logWindow:
                self._logWindow = MainWindow()
                self._logWindow.destroyed.connect(
                    self._onLogWindowDestroyed)
            window = self._logWindow
        elif type == Application.BlameWindow:
            if not self._blameWindow:
                self._blameWindow = BlameWindow()
                self._blameWindow.destroyed.connect(
                    self._onBlameWindowDestroyed)
            window = self._blameWindow
        elif type == Application.AiAssistant:
            if not self._aiChatWindow:
                self._aiChatWindow = AiChatWindow()
                self._aiChatWindow.destroyed.connect(
                    self._onAiChatWindowDestroyed)
            window = self._aiChatWindow

        return window

    def repoName(self):
        if not Git.available():
            return ""

        url = Git.repoUrl()
        index = url.rfind('/')
        if index == -1:
            return url
        return url[index+1:]

    def lastFocusWidget(self):
        return self._lastFocusWidget

    def event(self, event):
        type = event.type()
        if type == BlameEvent.Type:
            window = self.getWindow(Application.BlameWindow)
            window.blame(event.filePath, event.rev,
                         event.lineNo, event.repoDir)
            self._ensureVisible(window)
            return True
        elif type == ShowCommitEvent.Type:
            window = self.getWindow(Application.LogWindow)
            window.showCommit(event.sha1)
            self._ensureVisible(window)
            return True
        elif type == OpenLinkEvent.Type:
            url = None
            link = event.link
            if link.type == Link.Email:
                url = "mailto:" + link.data
            else:
                url = link.data

            if url:
                QDesktopServices.openUrl(QUrl(url))
            return True
        elif type == GitBinChanged.Type:
            self._initGit(self._settings.gitBinPath())
            if self._logWindow:
                self._logWindow.reloadRepo()

        elif type == CodeReviewEvent.Type:
            window = self.getWindow(Application.AiAssistant)
            self._ensureVisible(window)
            window.codeReview(event.commit, event.args)
        elif type == QEvent.ApplicationPaletteChange:
            self._setupColorSchema()

        return super().event(event)

    def _onLogWindowDestroyed(self, obj):
        self._logWindow = None

    def _onBlameWindowDestroyed(self, obj):
        self._blameWindow = None

    def _onAiChatWindowDestroyed(self, obj):
        self._aiChatWindow = None

    def _onNewVersionAvailable(self, version):
        ignoredVersion = self.settings().ignoredVersion()
        if ignoredVersion == version:
            return

        parent = self.activeWindow()
        versionDlg = NewVersionDialog(version, parent)
        versionDlg.exec()

    def _onVersionCheckFinished(self):
        self._checker = None
        self._settings.setLastCheck(int(datetime.now().timestamp()))

    def _onDelayInit(self):
        checkUpdates = self._settings.checkUpdatesEnabled()
        if checkUpdates:
            ts = self._settings.lastCheck()
            if ts < 86440:
                haveToCheck = True
            else:
                days = self._settings.checkUpdatesInterval()
                dt = datetime.fromtimestamp(ts)
                diff = datetime.now() - dt
                haveToCheck = diff.days >= days

            if haveToCheck:
                self._checker = VersionChecker(self)
                self._checker.newVersionAvailable.connect(
                    self._onNewVersionAvailable)
                self._checker.finished.connect(
                    self._onVersionCheckFinished)
                QTimer.singleShot(0, self._checker.startCheck)

    def _onFocusChanged(self, old, now):
        def _isFindWidget(w):
            if w is None:
                return False

            if isinstance(w, FindWidget):
                return True

            p = w.parent()
            while p:
                if isinstance(p, FindWidget):
                    return True
                p = p.parent()

            return False

        if not _isFindWidget(now):
            self._lastFocusWidget = now

    def _ensureVisible(self, window):
        if window.isVisible():
            if window.isMinimized():
                window.setWindowState(
                    window.windowState() & ~Qt.WindowMinimized)
            window.activateWindow()
            return
        if window.restoreState():
            window.show()
        else:
            window.showMaximized()

    def _warnGitMissing(self):
        QMessageBox.critical(
            self.activeWindow(),
            self.applicationName(),
            self.tr(
                "No git found, please check your settings."))

    def _initGit(self, gitBin):
        Git.initGit(gitBin)
        cwd = os.getcwd()
        repoDir = Git.repoTopLevelDir(cwd)
        Git.REPO_DIR = repoDir or cwd

    def isDarkTheme(self):
        return self._isDarkTheme

    def _isDarkThemeImpl(self):
        if qtVersion() >= (6, 5, 0):
            return self.styleHints().colorScheme() == Qt.ColorScheme.Dark
        else:
            palette = self.palette()
            textColor = palette.color(QPalette.WindowText)
            windowColor = palette.color(QPalette.Window)
            return textColor.lightness() > windowColor.lightness()

    def overrideColorSchema(self, mode):
        if qtVersion() >= (6, 8, 0):
            if mode == ColorSchemaMode.Light:
                colorSchema = Qt.ColorScheme.Light
            elif mode == ColorSchemaMode.Dark:
                colorSchema = Qt.ColorScheme.Dark
            else:
                colorSchema = Qt.ColorScheme.Unknown
            self.styleHints().setColorScheme(colorSchema)
        else:
            # TODO: implement this for older Qt versions
            pass

    def _setupColorSchema(self):
        if self._isDarkThemeImpl():
            self._colorSchema = ColorSchemaDark()
            self._isDarkTheme = True
        else:
            self._colorSchema = ColorSchemaLight()
            self._isDarkTheme = False

    def colorSchema(self):
        return self._colorSchema
