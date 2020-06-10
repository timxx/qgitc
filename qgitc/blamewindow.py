# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QMenu,
    QDialog)

from PySide2.QtGui import (
    QKeySequence)
from PySide2.QtCore import (
    Qt)

from .blameview import BlameView
from .stylehelper import dpiScaled
from .gotodialog import GotoDialog
from .findwidget import FindWidget


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

        self._findWidget = None

        self._view.blameFileAboutToChange.connect(
            self._onBlameFileAboutToChange)
        self._view.blameFileChanged.connect(
            self._onBlameFileChanged)

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
        editMenu.addSeparator()
        editMenu.addAction(self.tr("&Find"),
                           self.showFindWidget,
                           QKeySequence("Ctrl+F"))

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

    def _onFindFind(self, text):
        viewer = self._view.viewer
        findResult = viewer.findAll(text)

        curFindIndex = 0
        textCursor = viewer.textCursor
        if textCursor.isValid() and textCursor.hasSelection() and not textCursor.hasMultiLines():
            for i in range(0, len(findResult)):
                r = findResult[i]
                if r == textCursor:
                    curFindIndex = i
                    break

        viewer.highlightFindResult(findResult)
        if findResult:
            viewer.select(findResult[curFindIndex])

        self._findWidget.updateFindResult(findResult, curFindIndex)

    def _onFindCursorChanged(self, cursor):
        self._view.viewer.select(cursor)

    def _onFindHidden(self):
        self._view.viewer.highlightFindResult([])

    def _onBlameFileAboutToChange(self, file):
        if self._findWidget and self._findWidget.isVisible():
            self._findWidget.updateFindResult([])

    def _onBlameFileChanged(self, file):
        if self._findWidget and self._findWidget.isVisible():
            # redo a find
            self._onFindFind(self._findWidget.text)

    def showFindWidget(self):
        if not self._findWidget:
            self._findWidget = FindWidget(
                self._view.viewer.viewport(), self)
            self._findWidget.find.connect(
                self._onFindFind)
            self._findWidget.cursorChanged.connect(
                self._onFindCursorChanged)
            self._findWidget.afterHidden.connect(
                self._onFindHidden)

        text = self._view.viewer.selectedText
        if text:
            text = text.lstrip('\n')
            index = text.find('\n')
            if index != -1:
                text = text[:index]
            self._findWidget.setText(text)

        self._findWidget.showAnimate()

    def blame(self, file, sha1=None):
        self._view.blame(file, sha1)

    def restoreState(self):
        return False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self._findWidget and self._findWidget.isVisible():
                self._findWidget.hideAnimate()
            else:
                sett = qApp.instance().settings()
                if sett.quitViaEsc():
                    self.close()
                    return

        super().keyPressEvent(event)
