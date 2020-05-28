# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QMenu,
    QDialog)

from PySide2.QtGui import (
    QKeySequence)

from .blameview import BlameView
from .stylehelper import dpiScaled
from .gotodialog import GotoDialog


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
        self._setupMenuBar()

    def _setupMenuBar(self):
        self._setupFileMenu()
        self._setupEditMenu()

    def _setupFileMenu(self):
        fileMenu = self.menuBar().addMenu(self.tr("&File"))
        fileMenu.addAction(self.tr("&Close"),
                           self.close,
                           QKeySequence("Ctrl+W"))

    def _setupEditMenu(self):
        editMenu = self.menuBar().addMenu(self.tr("&Edit"))
        editMenu.addAction(self.tr("&Go To Line..."),
                           self._onGotoLine,
                           QKeySequence("Ctrl+G"))
        editMenu.addSeparator()
        editMenu.addAction(self.tr("Select &All"),
                           self._onSelectAll,
                           QKeySequence("Ctrl+A"))

    def _onGotoLine(self):
        gotoDialog = GotoDialog(self)
        viewer = self._view.viewer
        gotoDialog.setRange(1,
                            viewer.textLineCount(),
                            viewer.currentLineNo + 1)
        ret = gotoDialog.exec_()
        if ret != QDialog.Accepted:
            return

        viewer.gotoLine(gotoDialog.lineNo - 1)

    def _onSelectAll(self):
        self._view.viewer.selectAll()

    def blame(self, file, sha1=None):
        self._view.blame(file, sha1)
