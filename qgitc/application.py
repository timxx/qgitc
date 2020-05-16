# -*- coding: utf-8 -*-

from PySide2.QtWidgets import QApplication
from PySide2.QtGui import QIcon
from PySide2.QtCore import (Qt,
                            QTranslator,
                            QLibraryInfo,
                            QLocale)

from .common import dataDirPath
from .settings import Settings


class Application(QApplication):

    def __init__(self, argv):
        super(Application, self).__init__(argv)

        self.setAttribute(Qt.AA_DontShowIconsInMenus, False)
        self.setApplicationName("qgitc")

        iconPath = dataDirPath() + "/icons/qgitc.svg"
        self.setWindowIcon(QIcon(iconPath))

        self.setupTranslator()
        self._settings = Settings(self)

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
