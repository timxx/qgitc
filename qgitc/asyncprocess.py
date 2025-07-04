import os
import queue
import subprocess
import threading
from typing import List

from PySide6.QtCore import QObject, QThread, Signal


class AsyncProcessWorker(QObject):

    started = Signal()
    finished = Signal(int)
    readyReadStandardOutput = Signal(bytes)
    readyReadStandardError = Signal(bytes)

    def __init__(self, program: str, arguments: List[str]):
        super().__init__()
        self._process = None
        self._outputQueue = queue.Queue()
        self._errorQueue = queue.Queue()
        self._exitCode = None
        self._isRunning = False

        self._program = program
        self._arguments = arguments
        self._enableStdOut = False
        self._enableStdError = False
        self._cwd = None

    def setWorkingDirectory(self, directory: str):
        self._cwd = directory

    def run(self):
        if self._isRunning:
            return

        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW

            self._process = subprocess.Popen(
                [self._program] + self._arguments,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                cwd=self._cwd,
                creationflags=creationflags
            )
        except Exception:
            return

        self._isRunning = True
        self.started.emit()

        if self._enableStdOut:
            threading.Thread(target=self._readStdOut, daemon=True).start()
        if self._enableStdError:
            threading.Thread(target=self._readStdError, daemon=True).start()

        while self._isRunning:
            exitCode = self._process.poll()
            if exitCode is not None:
                self._exitCode = exitCode
                self._isRunning = False
                self.finished.emit(exitCode)
                break
            QThread.msleep(10)

    def setReadStdOut(self, enable: bool):
        self._enableStdOut = enable

    def setReadStdError(self, enable: bool):
        self._enableStdError = enable

    def _readStdOut(self):
        while self._isRunning:
            try:
                data = self._process.stdout.read(4096)
                if not data:
                    break
                self._outputQueue.put(data)
                self.readyReadStandardOutput.emit(data)
            except Exception:
                break

    def _readStdError(self):
        while self._isRunning:
            try:
                data = self._process.stderr.read(4096)
                if not data:
                    break
                self._errorQueue.put(data)
                self.readyReadStandardError.emit(data)
            except Exception:
                break

    def readAllStandardOutput(self):
        output = b""
        while not self._outputQueue.empty():
            output += self._outputQueue.get()
        return output

    def readAllStandardError(self):
        error = b""
        while not self._errorQueue.empty():
            error += self._errorQueue.get()
        return error

    def terminate(self):
        if self._isRunning and self._process:
            self._isRunning = False
            self._process.terminate()

    def kill(self):
        if self._isRunning and self._process:
            self._isRunning = False
            self._process.kill()

    def isRunning(self) -> bool:
        return self._isRunning

    def close(self):
        self._outputQueue.task_done()
        self._errorQueue.task_done()

    def waitForFinished(self, msecs = 30000):
        if self._isRunning and self._process:
            try:
                self._process.wait(msecs / 1000)
            except subprocess.TimeoutExpired:
                return False
            return True
        return False


class AsyncProcess(QObject):
    started = Signal()
    finished = Signal(int)
    readyReadStandardOutput = Signal(bytes)
    readyReadStandardError = Signal(bytes)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: AsyncProcessWorker = None
        self._thread: QThread = None
        self._readStdOut = False
        self._readStdError = False
        self._cwd = None

    def setWorkingDirectory(self, directory: str):
        self._cwd = directory

    def start(self, program: str, arguments: List[str]):
        if self._worker:
            return

        self._worker = AsyncProcessWorker(program, arguments)
        self._worker.started.connect(self.started)
        self._worker.finished.connect(self._onFinished)
        self._worker.readyReadStandardOutput.connect(
            self.readyReadStandardOutput)
        self._worker.readyReadStandardError.connect(
            self.readyReadStandardError)

        self._worker.setReadStdOut(self._readStdOut)
        self._worker.setReadStdError(self._readStdError)

        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def terminate(self):
        if self._worker:
            self._worker.terminate()
            self._thread.quit()
            self._worker.deleteLater()

    def kill(self):
        if self._worker:
            self._worker.kill()
            self._thread.quit()
            self._worker.deleteLater()

    def isRunning(self):
        return self._worker is not None and self._worker.isRunning()

    def close(self):
        if self._worker:
            self._worker.close()

    def waitForFinished(self, msecs=30000):
        if self._worker:
            return self._worker.waitForFinished(msecs)
        return False

    def _onFinished(self, exitCode):
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self.finished.emit(exitCode)
