# -*- coding: utf-8 -*-

from PySide6.QtCore import SIGNAL, QObject, QProcess, QProcessEnvironment, Signal

from qgitc.common import logger
from qgitc.gitutils import Git, GitProcess


class DataFetcher(QObject):

    fetchFinished = Signal(int)

    def __init__(self, parent=None):
        super(DataFetcher, self).__init__(parent)
        self._process = None
        self._dataChunk = None
        self._separator = b'\n'
        self._errorData = b''
        self._cwd = None
        self._exitCode = 0

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

    @property
    def errorData(self):
        return self._errorData

    @property
    def cwd(self):
        return self._cwd

    @cwd.setter
    def cwd(self, cwd):
        self._cwd = cwd

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

    def onProcessError(self):
        if not self._process:
            return
        data = self._process.readAllStandardError().data()
        self._errorData += data

    def onDataFinished(self, exitCode, exitStatus):
        if self._dataChunk:
            self.parse(self._dataChunk)

        self._process = None
        self._exitCode = exitCode
        self.fetchFinished.emit(exitCode)

    def cancel(self):
        if self._process:
            logger.info("Cancel git process")
            # self._process.disconnect(self)
            QObject.disconnect(self._process,
                               SIGNAL("readyReadStandardOutput()"),
                               self.onDataAvailable)
            QObject.disconnect(self._process,
                               SIGNAL("finished(int, QProcess::ExitStatus)"),
                               self.onDataFinished)
            QObject.disconnect(self._process, SIGNAL("readyReadStandardError()"),
                               self.onProcessError)
            self._process.close()
            self._process.waitForFinished(100)
            if self._process.state() == QProcess.Running:
                logger.warning("Kill git process")
                self._process.kill()
            self._process = None

        self._dataChunk = None

    def makeArgs(self, args):
        """Implement in subclass"""
        return []

    def reset(self):
        self._errorData = b''

    def fetch(self, *args):
        self.cancel()
        self.reset()

        git_args = self.makeArgs(args)

        self._process = QProcess()
        cwd = self._cwd if self._cwd else Git.REPO_DIR
        self._process.setWorkingDirectory(cwd)
        self._process.readyReadStandardOutput.connect(self.onDataAvailable)
        self._process.readyReadStandardError.connect(self.onProcessError)
        self._process.finished.connect(self.onDataFinished)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("LANGUAGE", "en_US")
        self._process.setProcessEnvironment(env)

        self._process.start(GitProcess.GIT_BIN, git_args)