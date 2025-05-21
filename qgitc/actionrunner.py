# -*- coding: utf-8 -*-

from typing import Union

from PySide6.QtCore import SIGNAL, QObject, QProcess, Signal

from qgitc.common import logger


class ActionRunner(QObject):

    finished = Signal(int)
    stdoutAvailable = Signal(bytes)
    stderrAvailable = Signal(bytes)

    def __init__(self, separator=b'\n', parent=None):
        super().__init__(parent)
        self._process = None
        self._stdoutChunk = None
        self._stderrChunk = None
        self._separator = separator
        self.exitCode = 0

    def onStdoutReady(self):
        data = self._process.readAllStandardOutput().data()
        if data and self._separator:
            if self._stdoutChunk:
                data = self._stdoutChunk + data
                self._stdoutChunk = None

            if data[-1] != ord(self._separator):
                idx = data.rfind(self._separator)

                if idx != -1:
                    idx += 1
                    self._stdoutChunk = data[idx:]
                    data = data[:idx]
                else:
                    self._stdoutChunk = data
                    data = None
        if data:
            self.stdoutAvailable.emit(data)

    def onStderrReady(self):
        data = self._process.readAllStandardError().data()
        if data and self._separator:
            if self._stderrChunk:
                data = self._stderrChunk + data
                self._stderrChunk = None

            if data[-1] != ord(self._separator):
                idx = data.rfind(self._separator)

                if idx != -1:
                    idx += 1
                    self._stderrChunk = data[idx:]
                    data = data[:idx]
                else:
                    self._stderrChunk = data
                    data = None
        if data:
            self.stderrAvailable.emit(data)

    def onRunFinished(self, exitCode, exitStatus):
        if self._stdoutChunk:
            self.stdoutAvailable(self._stdoutChunk)
        if self._stderrChunk:
            self.stderrAvailable(self._stderrChunk)

        self._process = None
        self.exitCode = exitCode
        self.finished.emit(exitCode)

    def cancel(self):
        if self._process:
            QObject.disconnect(self._process,
                               SIGNAL("readyReadStandardOutput()"),
                               self.onStdoutReady)
            QObject.disconnect(self._process,
                               SIGNAL("finished(int, QProcess::ExitStatus)"),
                               self.onRunFinished)
            QObject.disconnect(self._process, SIGNAL("readyReadStandardError()"),
                               self.onStderrReady)
            self._process.close()
            self._process.waitForFinished(100)
            if self._process.state() == QProcess.Running:
                logger.warning("Kill action process")
                self._process.kill()
            self._process = None

        self._stdoutChunk = None
        self._stderrChunk = None
        self.exitCode = 0

    def run(self, args: Union[str, list], cwd=None):
        self.cancel()

        self._process = QProcess()
        self._process.setWorkingDirectory(cwd)
        self._process.readyReadStandardOutput.connect(self.onStdoutReady)
        self._process.readyReadStandardError.connect(self.onStderrReady)
        self._process.finished.connect(self.onRunFinished)

        if isinstance(args, str):
            self._process.startCommand(args)
        else:
            self._process.start(args[0], args[1:])
