# -*- coding: utf-8 -*-

from typing import Union

from PySide6.QtCore import SIGNAL, QObject, QProcess, Signal

from qgitc.common import logger


class ActionRunner(QObject):

    finished = Signal(int)
    stdoutAvailable = Signal(bytes)
    stderrAvailable = Signal(bytes)
    stdinRequired = Signal(str, bool)

    def __init__(self, separator=b'\n', parent=None):
        super().__init__(parent)
        self._process = None
        self._stdoutChunk = None
        self._stderrChunk = None
        self._separator = separator
        self._lastPrompt = None
        self.exitCode = 0

    def _emitSignal(self, signal, data):
        if hasattr(signal, 'emit'):
            signal.emit(data)
        else:
            signal(data)

    def _emitPromptIfNeeded(self, data: bytes):
        if not data:
            self._lastPrompt = None
            return

        text = data.decode('utf-8', errors='replace').rstrip('\r\n')
        if not text or not (text.endswith(': ') or text.endswith('? ')):
            self._lastPrompt = None
            return

        if text == self._lastPrompt:
            return

        lowered = text.lower()
        isSecret = any(token in lowered
                       for token in ('password', 'passphrase', 'token', 'pin'))
        self._lastPrompt = text
        self.stdinRequired.emit(text, isSecret)

    def _shouldEmitTrailingChunk(self, data: bytes):
        if not data:
            return False

        text = data.decode('utf-8', errors='replace').rstrip('\r\n')
        if text.endswith(': ') or text.endswith('? '):
            return True

        return b'\r' in data

    def _processOutput(self, data: bytes, chunk: bytes, signal):
        shouldEmitChunk = False
        if data and self._separator:
            if chunk:
                data = chunk + data
                chunk = None

            if data[-1] != ord(self._separator):
                idx = data.rfind(self._separator)

                if idx != -1:
                    idx += 1
                    chunk = data[idx:]
                    data = data[:idx]
                else:
                    chunk = data
                    data = None

            if chunk and self._shouldEmitTrailingChunk(chunk):
                shouldEmitChunk = True
        if data:
            self._emitSignal(signal, data)
            self._lastPrompt = None

        if shouldEmitChunk:
            self._emitSignal(signal, chunk)
            self._emitPromptIfNeeded(chunk)
            chunk = None

        return chunk

    def writeInput(self, data: bytes):
        if self._process:
            self._process.write(data)

    def onStdoutReady(self):
        data = self._process.readAllStandardOutput().data()
        self._stdoutChunk = self._processOutput(data, self._stdoutChunk,
                                                self.stdoutAvailable)

    def onStderrReady(self):
        data = self._process.readAllStandardError().data()
        self._stderrChunk = self._processOutput(data, self._stderrChunk,
                                                self.stderrAvailable)

    def onRunFinished(self, exitCode, exitStatus):
        if self._stdoutChunk:
            self._emitSignal(self.stdoutAvailable, self._stdoutChunk)
        if self._stderrChunk:
            self._emitSignal(self.stderrAvailable, self._stderrChunk)

        self._lastPrompt = None

        self._process = None
        self._stdoutChunk = None
        self._stderrChunk = None
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
        self._lastPrompt = None
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
