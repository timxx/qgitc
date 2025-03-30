# -*- coding: utf-8 -*-

from typing import Callable, List
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import (
    QTextCharFormat,
    QTextCursor,
    QColor
)
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QProgressBar,
    QDialogButtonBox,
    QSpacerItem,
    QSizePolicy,
    QPlainTextEdit
)

from .submoduleexecutor import SubmoduleExecutor


class AppendResultEvent(QEvent):
    """Event to append result to the text edit area."""

    Type = QEvent.User + 1

    def __init__(self, out: str, error: str = None):
        super().__init__(QEvent.Type(AppendResultEvent.Type))
        self.out = out
        self.error = error


class GitProgressDialog(QDialog):
    """Git progress dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(self.tr("Git Progress"))
        self.setModal(True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.resize(400, 400)

        self._executor = SubmoduleExecutor(self)
        self._executor.finished.connect(self._onFinished)

        self._setupUi()

    def _setupUi(self):
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        layout.addWidget(self._progress)

        self._textEdit = QPlainTextEdit(self)
        self._textEdit.setReadOnly(True)
        self._textEdit.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._textEdit)

        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Abort)
        layout.addWidget(self.buttonBox)

        self.buttonBox.rejected.connect(self._executor.cancel)

    def executeTask(self, submodules: List[str], actionHandler: Callable, resultHandler: Callable = None):
        self._executor.submit(submodules, actionHandler, resultHandler)

        self._progress.setRange(0, 0)
        self._textEdit.clear()

        return self.exec()

    def updateProgressResult(self, out: str, error: str = None):
        """ Update the progress result to the text edit area.
         This method is thread-safe and can be called from any thread. """

        # sync to main thread to append
        qApp.postEvent(self, AppendResultEvent(out, error))

    def _onFinished(self):
        self._progress.hide()
        self.buttonBox.rejected.disconnect()
        self.buttonBox.clear()
        self.buttonBox.addButton(QDialogButtonBox.Close)
        self.buttonBox.rejected.connect(self.close)

    def event(self, evt):
        if evt.type() == AppendResultEvent.Type:
            self._textEdit.appendPlainText(evt.out)
            if evt.error:
                cursor = self._textEdit.textCursor()
                cursor.movePosition(QTextCursor.End)
                
                format = QTextCharFormat()
                format.setForeground(qApp.colorScheme().ErrorText)
                cursor.insertText(evt.error + "\n", format)
                cursor.setCharFormat(QTextCharFormat())
            self._textEdit.moveCursor(QTextCursor.End)
            self._textEdit.ensureCursorVisible()
            return True
        return super().event(evt)