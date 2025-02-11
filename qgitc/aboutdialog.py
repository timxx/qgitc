# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QDialog, QApplication
from PySide6.QtCore import QSize
from .ui_aboutdialog import Ui_AboutDialog
from .common import dataDirPath
from .version import VERSION


class AboutDialog(QDialog):

    def __init__(self, parent=None):
        super(AboutDialog, self).__init__(parent)

        self.ui = Ui_AboutDialog()
        self.ui.setupUi(self)

        icon = qApp.windowIcon()
        self.ui.appIcon.setPixmap(icon.pixmap(64, 64))

        self.ui.tbAbout.setOpenExternalLinks(True)
        self.ui.tbLicense.setOpenExternalLinks(True)

        self.__initTabs()

        self.resize(QSize(465, 470))

    def __initTabs(self):
        about = "<center><h3>QGitc " + VERSION + "</h3></center>"
        about += "<center>"
        about += self.tr("Git file conflicts and logs viewer")
        about += "</center>"
        about += "<center><a href=https://github.com/timxx/qgitc>"
        about += self.tr("Visit project host")
        about += "</a></center><br/>"
        about += "<center>Copyright © 2016-2025 Weitian Leung</center>"

        self.ui.tbAbout.setHtml(about)

        licenseFile = dataDirPath() + "/licenses/Apache-2.0.html"
        with open(licenseFile) as f:
            self.ui.tbLicense.setHtml(f.read())
