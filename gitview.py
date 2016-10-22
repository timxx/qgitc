# -*- coding: utf-8 -*-

from PyQt4.QtGui import *

from ui.gitview import *


class GitView(QWidget):

    def __init__(self, parent=None):
        super(GitView, self).__init__(parent)

        self.ui = Ui_GitView()
        self.ui.setupUi(self)

    def setBranchDesc(self, desc):
        self.ui.lbBranch.setText(desc)
