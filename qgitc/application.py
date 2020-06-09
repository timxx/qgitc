# -*- coding: utf-8 -*-

from PySide2.QtWidgets import QApplication
from PySide2.QtGui import QIcon
from PySide2.QtCore import (Qt,
                            QTranslator,
                            QLibraryInfo,
                            QLocale)

from .common import dataDirPath
from .settings import Settings
from .events import BlameEvent, ShowCommitEvent
from .blamewindow import BlameWindow
from .mainwindow import MainWindow
from .gitutils import Git

import os


class Application(QApplication):

    LogWindow = 1
    BlameWindow = 2

    def __init__(self, argv):
        super(Application, self).__init__(argv)

        self.setAttribute(Qt.AA_DontShowIconsInMenus, False)
        self.setApplicationName("qgitc")

        iconPath = dataDirPath() + "/icons/qgitc.svg"
        self.setWindowIcon(QIcon(iconPath))

        self.setupTranslator()
        self._settings = Settings(self)

        self._logWindow = None
        self._blameWindow = None

        repoDir = Git.repoTopLevelDir(os.getcwd())
        Git.REPO_DIR = repoDir

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

        return window

    def event(self, event):
        type = event.type()
        if type == BlameEvent.Type:
            window = self.getWindow(Application.BlameWindow)
            window.blame(event.filePath, event.sha1)
            self._ensureVisible(window)
            return True
        elif type == ShowCommitEvent.Type:
            window = self.getWindow(Application.LogWindow)
            window.showCommit(event.sha1)
            self._ensureVisible(window)
            return True

        return super().event(event)

    def _onLogWindowDestroyed(self, obj):
        self._logWindow = None

    def _onBlameWindowDestroyed(self, obj):
        self._blameWindow = None

    def _ensureVisible(self, window):
        if window.isVisible():
            return
        if window.restoreState():
            window.show()
        else:
            window.showMaximized()