# -*- coding: utf-8 -*-

from .statewindow import StateWindow
from .ui_commitwindow import Ui_CommitWindow


class CommitWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_CommitWindow()
        self.ui.setupUi(self)

        width = self.ui.splitterMain.width()
        sizes = [width * 1 / 4, width * 3 / 4]
        self.ui.splitterMain.setSizes(sizes)

        self.setWindowTitle(self.tr("QGitc Commit"))
