# -*- coding: utf-8 -*-

from PyQt4.QtGui import QDialog, qApp
from ui.aboutdialog import Ui_AboutDialog
from common import dataDirPath
from version import VERSION


class AboutDialog(QDialog, Ui_AboutDialog):

    def __init__(self, parent=None):
        super(AboutDialog, self).__init__(parent)

        self.setupUi(self)

        icon = qApp.windowIcon()
        self.appIcon.setPixmap(icon.pixmap(64, 64))

        self.tbAbout.setOpenExternalLinks(True)
        self.tbLicense.setOpenExternalLinks(True)

        self.__initTabs()

    def __initTabs(self):
        about = "<center><h3>gitc " + VERSION + "</h3></center>"
        about += "<center>"
        about += self.tr("Git file conflicts and logs viewer")
        about += "</center>"
        about += "<center><a href=https://github.com/timxx/gitc>"
        about += self.tr("Visit project host")
        about += "</a></center><br/>"
        about += "<center>Copyright © 2017 Weitian Leung</center>"

        self.tbAbout.setHtml(about)

        licenseFile = dataDirPath() + "/licenses/Apache-2.0.html"
        with open(licenseFile) as f:
            self.tbLicense.setHtml(f.read())
