# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QAbstractScrollArea,
    QMainWindow)
from .datafetcher import DataFetcher

import sys


__all__ = ["BlameView", "BlameWindow"]


class BlameFetcher(DataFetcher):
    def __init__(self, parent=None):
        super().__init__(parent)

    def parse(self, data):
        pass

    def makeArgs(self, args):
        return []


class BlameView(QAbstractScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)


class BlameWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("QGitc Blame"))

        self._view = BlameView(self)
        self.setCentralWidget(self._view)
