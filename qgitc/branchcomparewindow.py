# -*- coding: utf-8 -*-
from qgitc.statewindow import StateWindow
from qgitc.ui_branchcomparewindow import Ui_BranchCompareWindow


class BranchCompareWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_BranchCompareWindow()
        self.ui.setupUi(self)
