# -*- coding: utf-8 -*-

from PySide2.QtWidgets import QApplication
from PySide2.QtGui import QIcon
from PySide2.QtCore import (Qt,
                            QTranslator,
                            QLibraryInfo,
                            QLocale)

from .common import dataDirPath
from .settings import Settings
from .events import BlameEvent
from .blamewindow import BlameWindow


class Application(QApplication):

    def __init__(self, argv):
        super(Application, self).__init__(argv)

        self.setAttribute(Qt.AA_DontShowIconsInMenus, False)
        self.setApplicationName("qgitc")

        iconPath = dataDirPath() + "/icons/qgitc.svg"
        self.setWindowIcon(QIcon(iconPath))

        self.setupTranslator()
        self._settings = Settings(self)

        self._blameWindow = None

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

    def event(self, event):
        if event.type() == BlameEvent.Type:
            if not self._blameWindow:
                self._blameWindow = BlameWindow()
                # is it necessary?
                self._blameWindow.destroyed.connect(
                    self._onBlameWindowDestroyed)

            self._blameWindow.blame(event.filePath, event.sha1)
            self._blameWindow.showMaximized()
            return True

        return super().event(event)

    def _onBlameWindowDestroyed(self, obj):
        self._blameWindow = None
