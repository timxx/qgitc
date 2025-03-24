# -*- coding: utf-8 -*-

from .statewindow import StateWindow


class CommitWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("QGitc Commit"))
