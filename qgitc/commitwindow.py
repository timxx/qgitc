# -*- coding: utf-8 -*-

from .statewindow import StateWindow
from .ui_commitwindow import Ui_CommitWindow


class CommitWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_CommitWindow()
        self.ui.setupUi(self)

        width = self.ui.splitterMain.sizeHint().width()
        sizes = [width * 2 / 5, width * 3 / 5]
        self.ui.splitterMain.setSizes(sizes)

        height = self.ui.splitterRight.sizeHint().height()
        sizes = [height * 3 / 5, height * 2 / 5]
        self.ui.splitterRight.setSizes(sizes)

        self.setWindowTitle(self.tr("QGitc Commit"))
