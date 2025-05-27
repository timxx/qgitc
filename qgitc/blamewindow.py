# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from qgitc.applicationbase import ApplicationBase
from qgitc.blameview import BlameView
from qgitc.gotodialog import GotoDialog
from qgitc.statewindow import StateWindow
from qgitc.textviewer import FindPart

__all__ = ["BlameWindow"]


class BlameWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("QGitc Blame"))

        centralWidget = QWidget(self)
        layout = QVBoxLayout(centralWidget)
        margin = 4
        layout.setContentsMargins(margin, margin, margin, margin)

        self._view = BlameView(self)
        layout.addWidget(self._view)

        self.setCentralWidget(centralWidget)
        self._setupMenuBar()

        self._view.blameFileAboutToChange.connect(
            self._onBlameFileAboutToChange)
        self._view.blameFileChanged.connect(
            self._onBlameFileChanged)

    def _setupMenuBar(self):
        self._setupFileMenu()
        self._setupEditMenu()

    def _setupFileMenu(self):
        fileMenu = self.menuBar().addMenu(self.tr("&File"))
        acClose = fileMenu.addAction(self.tr("Close &Window"),
                                     self.close,
                                     QKeySequence("Ctrl+W"))
        acClose.setIcon(QIcon.fromTheme("window-close"))

    def _setupEditMenu(self):
        editMenu = self.menuBar().addMenu(self.tr("&Edit"))
        ac = editMenu.addAction(self.tr("&Go To Line..."),
                                self._onGotoLine,
                                QKeySequence("Ctrl+G"))
        ac.setIcon(QIcon.fromTheme("go-jump"))
        ac = editMenu.addAction(self.tr("&Find"),
                                self.showFindWidget,
                                QKeySequence(QKeySequence.StandardKey.Find))
        ac.setIcon(QIcon.fromTheme("edit-find"))

        self.acFindNext = editMenu.addAction(
            self.tr("Find &Next"),
            self.findNext,
            QKeySequence(QKeySequence.StandardKey.FindNext))
        self.acFindPrev = editMenu.addAction(
            self.tr("Find &Previous"),
            self.findPrevious,
            QKeySequence(QKeySequence.StandardKey.FindPrevious))

        editMenu.addSeparator()
        ac = editMenu.addAction(self.tr("&Copy"),
                                self._onCopy,
                                QKeySequence(QKeySequence.StandardKey.Copy))
        ac.setIcon(QIcon.fromTheme("edit-copy"))
        editMenu.addSeparator()
        ac = editMenu.addAction(self.tr("Select &All"),
                                self._onSelectAll,
                                QKeySequence(QKeySequence.StandardKey.SelectAll))
        ac.setIcon(QIcon.fromTheme("edit-select-all"))

        editMenu.aboutToShow.connect(self._onEditMenuAboutToShow)

    def _onGotoLine(self):
        gotoDialog = GotoDialog(self)
        viewer = self._view.viewer
        gotoDialog.setRange(1,
                            viewer.textLineCount(),
                            viewer.currentLineNo + 1)
        ret = gotoDialog.exec()
        if ret != QDialog.Accepted:
            return

        viewer.gotoLine(gotoDialog.lineNo - 1)

    def _onCopy(self):
        fw = ApplicationBase.instance().focusWidget()
        if fw == self._view.commitPanel.detailPanel:
            fw.copy()
        elif fw == self._view.commitPanel.logView:
            fw.copy()
        else:
            self._view.viewer.copy()

    def _onSelectAll(self):
        if ApplicationBase.instance().focusWidget() == self._view.commitPanel.detailPanel:
            self._view.commitPanel.detailPanel.selectAll()
        else:
            self._view.viewer.selectAll()

    def _onBlameFileAboutToChange(self, file):
        if self.findWidget and self.findWidget.isVisible():
            self.findWidget.updateFindResult([])

    def _onBlameFileChanged(self, file):
        findWidget = self.findWidget
        if findWidget and findWidget.isVisible():
            # redo a find
            findWidget.setText(findWidget.text)

    def showFindWidget(self):
        self._view.viewer.executeFind()

    def blame(self, file, rev=None, lineNo=0, repoDir=None):
        self._view.blame(file, rev, lineNo, repoDir)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.findWidget and self.findWidget.isVisible():
                self.findWidget.hideAnimate()
                return

        super().keyPressEvent(event)

    def findNext(self):
        if self.findWidget:
            self.findWidget.findNext()

    def findPrevious(self):
        if self.findWidget:
            self.findWidget.findPrevious()

    def _onEditMenuAboutToShow(self):
        enabled = self.findWidget is not None and self.findWidget.isVisible()
        if not enabled:
            self.acFindNext.setEnabled(False)
            self.acFindPrev.setEnabled(False)
            return

        self.acFindNext.setEnabled(self.findWidget.canFindNext())
        self.acFindPrev.setEnabled(self.findWidget.canFindPrevious())

    def closeEvent(self, event):
        self._view.queryClose()
        super().closeEvent(event)

    @property
    def findWidget(self):
        return self._view.viewer.findWidget
