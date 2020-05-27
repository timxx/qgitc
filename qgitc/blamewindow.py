# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout)

from .blameview import BlameView
from .stylehelper import dpiScaled


__all__ = ["BlameWindow"]


class BlameWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("QGitc Blame"))

        centralWidget = QWidget(self)
        layout = QVBoxLayout(centralWidget)
        margin = dpiScaled(5)
        layout.setContentsMargins(margin, margin, margin, margin)

        self._view = BlameView(self)
        layout.addWidget(self._view)

        self.setCentralWidget(centralWidget)

    def blame(self, file, sha1=None):
        self._view.blame(file, sha1)
