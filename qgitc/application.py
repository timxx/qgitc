# -*- coding: utf-8 -*-

import os
import shutil
from datetime import datetime
from typing import Dict, List

from PySide6.QtCore import (
    SIGNAL,
    QElapsedTimer,
    QEvent,
    QLibraryInfo,
    QLocale,
    QObject,
    Qt,
    QThread,
    QTimer,
    QTranslator,
    QUrl,
    qVersion,
)
from PySide6.QtGui import QDesktopServices, QIcon, QPalette
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QMessageBox

from qgitc.aichatwindow import AiChatWindow
from qgitc.applicationbase import ApplicationBase, qtVersion
from qgitc.blamewindow import BlameWindow
from qgitc.branchcomparewindow import BranchCompareWindow
from qgitc.colorschema import ColorSchemaDark, ColorSchemaLight, ColorSchemaMode
from qgitc.commitwindow import CommitWindow
from qgitc.common import dataDirPath, logger
from qgitc.events import (
    BlameEvent,
    CodeReviewEvent,
    GitBinChanged,
    LocalChangesCommittedEvent,
    LoginFinished,
    OpenLinkEvent,
    RequestCommitEvent,
    RequestLoginGithubCopilot,
    ShowAiAssistantEvent,
    ShowBranchCompareEvent,
    ShowCommitEvent,
    ShowPickBranchEvent,
)
from qgitc.findsubmodules import FindSubmoduleThread
from qgitc.findwidget import FindWidget
from qgitc.githubcopilotlogindialog import GithubCopilotLoginDialog
from qgitc.gitutils import Git
from qgitc.mainwindow import MainWindow
from qgitc.newversiondialog import NewVersionDialog
from qgitc.otelimpl import OTelService
from qgitc.pickbranchwindow import PickBranchWindow
from qgitc.settings import Settings
from qgitc.textline import Link
from qgitc.version import __version__
from qgitc.versionchecker import VersionChecker
from qgitc.watchdog import Watchdog
from qgitc.windowtype import WindowType

try:
    from qgitc.otelenv import OTEL_AUTH, OTEL_ENDPOINT
except ImportError:
    OTEL_ENDPOINT = None


class Application(ApplicationBase):

    def __init__(self, argv, testing=False):
        super().__init__(argv)

        self.setAttribute(Qt.AA_DontShowIconsInMenus, False)
        self.setAttribute(Qt.AA_DontUseNativeMenuBar, True)
        self.setApplicationName("qgitc")

        iconPath = dataDirPath() + "/icons/qgitc.svg"
        self.setWindowIcon(QIcon(iconPath))

        self.testing = testing
        self._settings = Settings(self, testing=testing)
        self.setupTranslator()

        self._manager = QNetworkAccessManager(self)
        self._initTelemetry()

        self._logWindow = None
        self._blameWindow = None
        self._aiChatWindow = None
        self._commitWindow = None
        self._branchCompareWindow = None
        self._pickBranchWindow = None

        self._threads: List[QThread] = []
        self._findSubmoduleThread: FindSubmoduleThread = None
        self._submodules: List[str] = []

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

        self._watchDog = Watchdog(self)
        self._watchDog.start()

        self.aboutToQuit.connect(self._onAboutToQuit)

    def settings(self):
        return self._settings

    def setupTranslator(self):
        if self.testing:
            return

        locale = self.uiLocale()
        # Do nothing for English locale, as the strings are already in English.
        # This fix addresses the issue where the translator misloaded Chinese when the locale is set to "en".
        if locale.language() == QLocale.English:
            return

        # the Qt translations
        dirPath = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
        self._installTranslator(locale, dirPath, "qtbase", "_")

        dirPath = dataDirPath() + "/translations"
        self._installTranslator(locale, dirPath, "", "")

    def _installTranslator(self, locale: QLocale, dirPath: str, name: str, prefix: str):
        translator = QTranslator(self)
        if translator.load(locale, name, prefix, dirPath):
            self.installTranslator(translator)
        else:
            translator = None

    def getWindow(self, type, ensureCreated=True):
        window = None
        if type == WindowType.LogWindow:
            if not self._logWindow and ensureCreated:
                self._logWindow = MainWindow()
                self._logWindow.destroyed.connect(
                    self._onLogWindowDestroyed)
            window = self._logWindow
        elif type == WindowType.BlameWindow:
            if not self._blameWindow and ensureCreated:
                self._blameWindow = BlameWindow()
                self._blameWindow.destroyed.connect(
                    self._onBlameWindowDestroyed)
            window = self._blameWindow
        elif type == WindowType.AiAssistant:
            if not self._aiChatWindow and ensureCreated:
                self._aiChatWindow = AiChatWindow()
                self._aiChatWindow.destroyed.connect(
                    self._onAiChatWindowDestroyed)
            window = self._aiChatWindow
        elif type == WindowType.CommitWindow:
            if not self._commitWindow and ensureCreated:
                self._commitWindow = CommitWindow()
                self._commitWindow.destroyed.connect(
                    self._onCommitWindowDestroyed)
            window = self._commitWindow
        elif type == WindowType.BranchCompareWindow:
            if not self._branchCompareWindow and ensureCreated:
                self._branchCompareWindow = BranchCompareWindow()
                self._branchCompareWindow.destroyed.connect(
                    self._onBranchCompareWindowDestroyed)
            window = self._branchCompareWindow

        elif type == WindowType.PickBranchWindow:
            if not self._pickBranchWindow and ensureCreated:
                self._pickBranchWindow = PickBranchWindow()
                self._pickBranchWindow.destroyed.connect(
                    self._onPickBranchWindowDestroyed)
            window = self._pickBranchWindow

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
            window = self.getWindow(WindowType.BlameWindow)
            window.blame(event.filePath, event.rev,
                         event.lineNo, event.repoDir)
            self._ensureVisible(window)
            return True

        if type == ShowCommitEvent.Type:
            window = self.getWindow(WindowType.LogWindow)
            window.showCommit(event.sha1)
            self._ensureVisible(window)
            return True

        if type == OpenLinkEvent.Type:
            url = None
            link = event.link
            if link.type == Link.Email:
                url = "mailto:" + link.data
            else:
                url = link.data

            if url:
                QDesktopServices.openUrl(QUrl(url))
            return True

        if type == GitBinChanged.Type:
            self._initGit(self._settings.gitBinPath())
            if self._logWindow:
                self._logWindow.reloadRepo()
            return True

        if type == CodeReviewEvent.Type:
            window = self.getWindow(WindowType.AiAssistant)
            self._ensureVisible(window)
            if event.submodules is not None:
                window.codeReviewForStagedFiles(event.submodules)
            else:
                window.codeReview(event.commit, event.args)
            return True

        if type == ShowAiAssistantEvent.Type:
            window = self.getWindow(WindowType.AiAssistant)
            self._ensureVisible(window)
            return True

        if type == RequestCommitEvent.Type:
            needRefresh = self._commitWindow is not None
            window = self.getWindow(WindowType.CommitWindow)
            if needRefresh:
                window.reloadLocalChanges()
            self._ensureVisible(window)
            return True

        if type == LocalChangesCommittedEvent.Type:
            if self._logWindow:
                self._logWindow.reloadLocalChanges()
            return True

        if type == RequestLoginGithubCopilot.Type:
            dialog = GithubCopilotLoginDialog(self.activeWindow())
            dialog.setAutoClose(event.autoClose)
            dialog.exec()
            self.postEvent(event.requestor, LoginFinished(
                dialog.isLoginSuccessful()))
            return True

        if type == ShowBranchCompareEvent.Type:
            window = self.getWindow(WindowType.BranchCompareWindow)
            self._ensureVisible(window)
            if event.targetBranch or event.baseBranch:
                window.compareBranches(event.targetBranch, event.baseBranch)
            return True

        if type == ShowPickBranchEvent.Type:
            window = self.getWindow(WindowType.PickBranchWindow)
            self._ensureVisible(window)
            if event.sourceBranch or event.targetBranch:
                # Set branches if provided
                if event.sourceBranch:
                    idx = window.ui.cbSourceBranch.findText(event.sourceBranch)
                    if idx >= 0:
                        window.ui.cbSourceBranch.setCurrentIndex(idx)
                if event.targetBranch:
                    idx = window.ui.cbTargetBranch.findText(event.targetBranch)
                    if idx >= 0:
                        window.ui.cbTargetBranch.setCurrentIndex(idx)
            return True

        if type == QEvent.ApplicationPaletteChange:
            self._setupColorSchema()

        return super().event(event)

    def _onLogWindowDestroyed(self, obj):
        self._logWindow = None

    def _onBlameWindowDestroyed(self, obj):
        self._blameWindow = None

    def _onAiChatWindowDestroyed(self, obj):
        self._aiChatWindow = None

    def _onCommitWindowDestroyed(self, obj):
        self._commitWindow = None

    def _onBranchCompareWindowDestroyed(self, obj):
        self._branchCompareWindow = None

    def _onPickBranchWindowDestroyed(self, obj):
        self._pickBranchWindow = None

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
                dt = datetime.fromtimestamp(ts).date()
                now = datetime.now().date()
                diff = now - dt
                haveToCheck = diff.days >= days

            if haveToCheck and not self.testing:
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
        self.updateRepoDir(repoDir)

    def updateRepoDir(self, repoDir: str, reloadSubmodules=True):
        if Git.REPO_DIR == repoDir:
            return False

        if repoDir is not None and Git.REPO_DIR is not None:
            newDir = os.path.normpath(os.path.normcase(repoDir))
            oldDir = os.path.normpath(os.path.normcase(Git.REPO_DIR))
            if newDir == oldDir:
                return False

        Git.REPO_DIR = repoDir
        if reloadSubmodules:
            self._updateSubmodules()
        self.repoDirChanged.emit()

        return True

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

    def uiLocale(self):
        lang = self._settings.language()
        if not lang:
            locale = QLocale.system()
        else:
            locale = QLocale(lang)

        return locale

    def uiLanguage(self):
        locale = self.uiLocale()
        return locale.languageToString(locale.language())

    def terminateThread(self, thread: QThread, waitTime=3000):
        if not thread.isRunning():
            return False

        timer = QElapsedTimer()
        timer.start()
        while thread.isRunning() and timer.elapsed() <= waitTime:
            self.processEvents()
        if thread.isRunning():
            thread.terminate()
            return True
        return False

    def telemetry(self):
        return self._telemetry

    def trackFeatureUsage(self, feature: str, properties: Dict[str, object] = None):
        props = {
            "event.type": "feature_usage",
            "feature.name": feature,
            "user.id": self._settings.userId(),
        }
        if properties:
            props.update(properties)
        logger = self._telemetry.logger()
        logger.info(
            f"Feature usage: {feature}",
            extra=props
        )

    def _initTelemetry(self):
        self._telemetry = OTelService()
        if not self._settings.isTelemetryEnabled():
            return
        if not OTEL_ENDPOINT or self.testing:
            return

        # trust the cache first
        connectable = self._settings.isTelemetryServerConnectable(
            OTEL_ENDPOINT)
        if connectable:
            self._telemetry.setupService(
                self.applicationName(),
                __version__,
                qVersion(),
                OTEL_ENDPOINT,
                OTEL_AUTH
            )

        # check the endpoint every 3 days
        if connectable is not None:
            ts = self._settings.lastTelemetryServerCheck()
            dt = datetime.fromtimestamp(ts)
            diff = datetime.now() - dt
            if diff.days < 3:
                return

        request = QNetworkRequest()
        request.setUrl(OTEL_ENDPOINT)
        if OTEL_AUTH:
            request.setRawHeader(b"Authorization", OTEL_AUTH.encode('utf-8'))
        reply = self._manager.head(request)

        reply.finished.connect(
            self._onCheckEndpointFinished)

    def _onCheckEndpointFinished(self):
        reply: QNetworkReply = self.sender()
        reply.deleteLater()

        self._settings.setLastTelemetryServerCheck(
            int(datetime.now().timestamp()))

        ok = reply.error() in [
            QNetworkReply.NoError,
            QNetworkReply.ContentNotFoundError,
        ]
        self._settings.setTelemetryServerConnectable(
            OTEL_ENDPOINT, ok)

        if ok and self._settings.isTelemetryEnabled() and not self._telemetry.inited:
            self._telemetry.setupService(
                self.applicationName(),
                __version__,
                qVersion(),
                OTEL_ENDPOINT,
                OTEL_AUTH
            )

    @property
    def networkManager(self) -> QNetworkAccessManager:
        return self._manager

    def _updateSubmodules(self):
        self._submodules.clear()
        if not Git.available() or not Git.REPO_DIR:
            return

        self._findSubmodules()

        submodules = self._settings.submodulesCache(Git.REPO_DIR)
        # first, check if cache is valid
        for submodule in submodules:
            if not os.path.exists(os.path.join(Git.REPO_DIR, submodule)):
                self._settings.setSubmodulesCache(Git.REPO_DIR, [])
                return

        self._submodules = submodules[:]
        self.submoduleAvailable.emit(self._submodules, True)

    def _findSubmodules(self):
        self._cancelFindSubmodules()

        self._findSubmoduleThread = FindSubmoduleThread(Git.REPO_DIR, self)
        self._findSubmoduleThread.finished.connect(
            self._onFindSubmoduleFinished)
        self._findSubmoduleThread.finished.connect(
            self._onThreadFinished)
        self._threads.append(self._findSubmoduleThread)

        self._findSubmoduleThread.start()

    def _cancelFindSubmodules(self, force=False):
        if not self._findSubmoduleThread:
            return

        QObject.disconnect(self._findSubmoduleThread,
                           SIGNAL("finished"),
                           self._onFindSubmoduleFinished)
        self._findSubmoduleThread.requestInterruption()
        if force and self.terminateThread(self._findSubmoduleThread):
            self._threads.remove(self._findSubmoduleThread)
            self._findSubmoduleThread.finished.disconnect(
                self._onThreadFinished)
            logger.warning("Terminate find submodule thread")
        self._findSubmoduleThread = None

    def _onFindSubmoduleFinished(self):
        thread: FindSubmoduleThread = self.sender()
        if thread == self._findSubmoduleThread:
            self._findSubmoduleThread = None
        else:
            # already cancelled, but signal already in queue
            return

        self._submodules = thread.submodules[:]
        caches = self._settings.submodulesCache(Git.REPO_DIR)

        newSubmodules = list(set(self._submodules) - set(caches))
        # no new submodules
        if newSubmodules:
            self._settings.setSubmodulesCache(Git.REPO_DIR, self._submodules)
            self.submoduleAvailable.emit(newSubmodules, False)

        self.submoduleSearchCompleted.emit()

    def _onThreadFinished(self):
        thread = self.sender()
        if thread in self._threads:
            self._threads.remove(thread)

    @property
    def submodules(self) -> List[str]:
        return self._submodules

    def _onAboutToQuit(self):
        self._watchDog.stop()
        self._cancelFindSubmodules(True)

        for thread in self._threads[:]:
            self.terminateThread(thread)
