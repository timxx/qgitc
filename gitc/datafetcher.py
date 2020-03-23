# -*- coding: utf-8 -*-

from PySide2.QtCore import *
from .gitutils import Git


class DataFetcher(QObject):

    fetchFinished = Signal()

    def __init__(self, parent=None):
        super(DataFetcher, self).__init__(parent)
        self._process = None
        self._dataChunk = None
        self._separator = b'\n'

    @property
    def process(self):
        return self._process

    @property
    def dataChunk(self):
        return self._dataChunk

    @property
    def separator(self):
        return self._separator

    @separator.setter
    def separator(self, sep):
        self._separator = sep

    def parse(self, data):
        """Implement in subclass"""
        pass

    def onDataAvailable(self):
        data = self._process.readAllStandardOutput().data()
        if self._dataChunk:
            data = self._dataChunk + data
            self._dataChunk = None

        if data[-1] != ord(self.separator):
            idx = data.rfind(self.separator)

            if idx != -1:
                idx += 1
                self._dataChunk = data[idx:]
                data = data[:idx]
            else:
                self._dataChunk = data
                data = None

        if data:
            self.parse(data)

    def onDataFinished(self, exitCode, exitStatus):
        if self._dataChunk:
            self.parse(self._dataChunk)

        self._process = None
        self.fetchFinished.emit()

    def cancel(self):
        if self._process:
            # self._process.disconnect(self)
            QObject.disconnect(self._process,
                               SIGNAL("readyReadStandardOutput()"),
                               self.onDataAvailable)
            QObject.disconnect(self._process,
                               SIGNAL("finished(int, QProcess::ExitStatus)"),
                               self.onDataFinished)
            self._process.close()
            self._process = None

        self._dataChunk = None

    def makeArgs(self, args):
        """Implement in subclass"""
        return []

    def fetch(self, *args):
        self.cancel()

        git_args = self.makeArgs(args)

        self._process = QProcess()
        self._process.setWorkingDirectory(Git.REPO_DIR)
        self._process.readyReadStandardOutput.connect(self.onDataAvailable)
        self._process.finished.connect(self.onDataFinished)

        self._process.start("git", git_args)
