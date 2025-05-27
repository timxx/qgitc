# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow

from qgitc.applicationbase import ApplicationBase

__all__ = ["StateWindow"]


class StateWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)

    def saveState(self):
        sett = ApplicationBase.instance().settings()
        if not sett.rememberWindowState():
            return False

        state = super().saveState()
        geometry = self.saveGeometry()
        sett.setWindowState(
            self.__class__.__name__,
            state, geometry, self.isMaximized())

        return True

    def restoreState(self):
        sett = ApplicationBase.instance().settings()
        if not sett.rememberWindowState():
            return False

        state, geometry, isMaximized = sett.windowState(
            self.__class__.__name__, self.isMaximizedByDefault())
        if state:
            super().restoreState(state)
        if geometry:
            self.restoreGeometry(geometry)

        if isMaximized:
            self.setWindowState(self.windowState() | Qt.WindowMaximized)

        return True

    def closeEvent(self, event):
        self.saveState()
        super().closeEvent(event)

    def isMaximizedByDefault(self):
        return True

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            sett = ApplicationBase.instance().settings()
            if sett.quitViaEsc():
                self.close()
                return

        super().keyPressEvent(event)
