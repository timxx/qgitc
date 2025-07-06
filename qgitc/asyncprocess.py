# -*- coding: utf-8 -*-

import queue
import threading
import time
from typing import List

import win32api
import win32con
import win32event
import win32pipe
import win32process
import win32security
from PySide6.QtCore import QObject, QProcess, QThread, Signal


class AsyncProcessWorker(QObject):
    started = Signal()
    finished = Signal(int, QProcess.ExitStatus)
    readyReadStandardOutput = Signal(bytes)
    readyReadStandardError = Signal(bytes)

    def __init__(self, program: str, arguments: List[str]):
        super().__init__()
        self._processHandle = None
        self._threadHandle = None
        self._outputQueue = queue.Queue()
        self._errorQueue = queue.Queue()
        self._exitCode = None
        self._isRunning = False

        self._program = program
        self._arguments = arguments
        self._enableStdOut = False
        self._enableStdError = False
        self._cwd = None

        # Pipe handles
        self._hStdoutRead = None
        self._hStdoutWrite = None
        self._hStderrRead = None
        self._hStdErrWrite = None

        # Reader threads
        self._stdoutThread = None
        self._stderrThread = None

    def setWorkingDirectory(self, directory: str):
        self._cwd = directory

    def run(self):
        if self._isRunning:
            return

        # Create security attributes for pipe inheritance
        sa = win32security.SECURITY_ATTRIBUTES()
        sa.bInheritHandle = True

        # Create pipes for stdout and stderr
        if self._enableStdOut:
            self._hStdoutRead, self._hStdoutWrite = win32pipe.CreatePipe(sa, 0)
            # Ensure the read handle is not inherited
            win32api.SetHandleInformation(
                self._hStdoutRead, win32con.HANDLE_FLAG_INHERIT, 0)

        if self._enableStdError:
            self._hStderrRead, self._hStdErrWrite = win32pipe.CreatePipe(sa, 0)
            win32api.SetHandleInformation(
                self._hStderrRead, win32con.HANDLE_FLAG_INHERIT, 0)

        # Set up process startup info
        startupInfo = win32process.STARTUPINFO()
        startupInfo.dwFlags |= win32process.STARTF_USESTDHANDLES

        # Set std handles
        startupInfo.hStdInput = win32api.GetStdHandle(
            win32api.STD_INPUT_HANDLE)
        startupInfo.hStdOutput = self._hStdoutWrite if self._enableStdOut else win32api.GetStdHandle(
            win32api.STD_OUTPUT_HANDLE)
        startupInfo.hStdError = self._hStdErrWrite if self._enableStdError else win32api.GetStdHandle(
            win32api.STD_ERROR_HANDLE)

        creationFlags = win32con.CREATE_NO_WINDOW

        args = '"' + self._program + '"' if " " in self._program else self._program
        if self._arguments:
            args += " "
        for arg in self._arguments:
            if " " in arg:
                args += f'"{arg}" '
            else:
                args += f"{arg} "

        try:
            begin = time.time()
            self._processHandle, self._threadHandle, _, _ = win32process.CreateProcess(
                None,
                args,
                None,
                None,
                True,
                creationFlags,
                None,
                self._cwd,
                startupInfo)
            end = time.time()
            print(f"Process started in {(end - begin)*1000} ms")

            self._isRunning = True
            self.started.emit()

            # Close write handles in the parent process
            if self._enableStdOut:
                win32api.CloseHandle(self._hStdoutWrite)
                self._hStdoutWrite = None
                # Start reading thread for stdout
                self._stdoutThread = threading.Thread(target=self._read_stdout)
                self._stdoutThread.daemon = True
                self._stdoutThread.start()

            if self._enableStdError:
                win32api.CloseHandle(self._hStdErrWrite)
                self._hStdErrWrite = None
                # Start reading thread for stderr
                self._stderrThread = threading.Thread(target=self._read_stderr)
                self._stderrThread.daemon = True
                self._stderrThread.start()

            # Wait for process to finish in a separate thread
            # finish_thread = threading.Thread(target=self._wait_for_process)
            # finish_thread.daemon = True
            # finish_thread.start()
            self._wait_for_process()
        except Exception as e:
            self._isRunning = False
            self.finished.emit(-1, QProcess.ExitStatus.CrashExit)
            raise e

    def _read_stdout(self):
        while self._isRunning:
            try:
                # Read data from pipe
                hr, data = win32api.ReadFile(self._hStdoutRead, 4096)
                if data:
                    self._outputQueue.put(data)
                    self.readyReadStandardOutput.emit(data)
                else:
                    break
            except:
                break

    def _read_stderr(self):
        while self._isRunning:
            try:
                hr, data = win32api.ReadFile(self._hStderrRead, 4096)
                if data:
                    self._errorQueue.put(data)
                    self.readyReadStandardError.emit(data)
                else:
                    # EOF reached
                    break
            except:
                break

    def _wait_for_process(self):
        win32event.WaitForSingleObject(
            self._processHandle, win32event.INFINITE)
        self._exitCode = win32process.GetExitCodeProcess(self._processHandle)
        self._isRunning = False
        self.finished.emit(self._exitCode, QProcess.ExitStatus.NormalExit)

    def setReadStdOut(self, enable: bool):
        self._enableStdOut = enable

    def setReadStdError(self, enable: bool):
        self._enableStdError = enable

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
        if self._isRunning and self._processHandle:
            win32process.TerminateProcess(self._processHandle, 1)
            self._isRunning = False

    def kill(self):
        if self._isRunning and self._processHandle:
            win32process.TerminateProcess(self._processHandle, 1)
            self._isRunning = False

    def isRunning(self) -> bool:
        return self._isRunning

    def close(self):
        if self._hStdoutRead:
            win32api.CloseHandle(self._hStdoutRead)
            self._hStdoutRead = None
        if self._hStdoutWrite:
            win32api.CloseHandle(self._hStdoutWrite)
            self._hStdoutWrite = None
        if self._hStderrRead:
            win32api.CloseHandle(self._hStderrRead)
            self._hStderrRead = None
        if self._hStdErrWrite:
            win32api.CloseHandle(self._hStdErrWrite)
            self._hStdErrWrite = None
        if self._processHandle:
            win32api.CloseHandle(self._processHandle)
            self._processHandle = None
        if self._threadHandle:
            win32api.CloseHandle(self._threadHandle)
            self._threadHandle = None

    def waitForFinished(self, msecs=30000):
        if self._isRunning and self._processHandle:
            result = win32event.WaitForSingleObject(self._processHandle, msecs)
            return result == win32event.WAIT_OBJECT_0
        return False


class AsyncProcess(QObject):
    started = Signal()
    finished = Signal(int, QProcess.ExitStatus)
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
        if self._cwd:
            self._worker.setWorkingDirectory(self._cwd)

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

    def _onFinished(self, exitCode, exitStatus):
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self.finished.emit(exitCode, exitStatus)
