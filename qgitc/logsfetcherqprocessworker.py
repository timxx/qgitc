# -*- coding: utf-8 -*-

import os
import time
from typing import List

from PySide6.QtCore import QEventLoop, QObject, QProcess, Qt, QThread, Signal

from qgitc.applicationbase import ApplicationBase
from qgitc.common import (
    Commit,
    extractFilePaths,
    filterSubmoduleByPath,
    fullRepoDir,
    logger,
)
from qgitc.gitutils import Git, GitProcess
from qgitc.logsfetcherimpl import LogsFetcherImpl
from qgitc.logsfetcherworkerbase import LogsFetcherWorkerBase


class LocalChangesFetcher(QObject):
    finished = Signal()

    def __init__(self, repoDir: str = None, isComposite=False, parent=None):
        super().__init__(parent)
        self._repoDir = repoDir
        self._process: QProcess = None
        self._processObj: QProcess = None
        self._failedStart = False
        self.isComposite = isComposite

        self.hasLCC = False
        self.hasLUC = False
        self.untrackedFiles: List[str] = []

    def fetch(self):
        self._failedStart = False
        self._process = self._startProcess()

    def cancel(self):
        # Clear active markers first so finished during wait is ignored
        process = self._process
        self._process = None
        self.hasLCC = False
        self.hasLUC = False
        self.untrackedFiles = []

        self._cancelProcess(process)

    def _createProcess(self):
        process = QProcess(self)
        process.finished.connect(self._onFinished)
        process.errorOccurred.connect(self._onError)
        return process

    def _startProcess(self):
        args = ["status", "--porcelain"]
        args.append("--untracked-files=all")
        if Git.versionGE(1, 7, 2):
            args.append("--ignore-submodules=dirty")
        args.append("-z")

        if self._processObj is None:
            self._processObj = self._createProcess()
        process = self._processObj

        process.setWorkingDirectory(self._repoDir or Git.REPO_DIR)
        process.start(GitProcess.GIT_BIN, args)
        if self._failedStart:
            return None

        return process

    def _cancelProcess(self, process: QProcess):
        if not process:
            return

        if process.state() != QProcess.NotRunning:
            process.close()
            process.waitForFinished(50)
            if process.state() == QProcess.Running:
                logger.warning("Kill git process")
                process.kill()

    def _onFinished(self, exitCode, exitStatus):
        process: QProcess = self.sender()
        if process != self._process:
            return
        self._process = None

        if exitCode == 0 and process.bytesAvailable():
            data = bytes(process.readAllStandardOutput())
            self._parseStatus(data)

        self.finished.emit()

    def _parseStatus(self, data: bytes):
        if data and data[-1] == 0:
            data = data[:-1]
        if not data:
            return

        lines = data.split(b'\0')
        self.untrackedFiles = []
        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1
            if not line:
                continue

            status = line[:2].decode("utf-8", errors="replace")

            # Untracked files
            if status == "??":
                file = line[3:].decode("utf-8", errors="replace")
                self.untrackedFiles.append(file)
                continue

            # Staged change (index status column)
            if status[0] != " ":
                self.hasLCC = True
            # Unstaged change (worktree status column)
            if status[1] != " ":
                self.hasLUC = True

            # Renames have old name on the next line
            if status[0] == "R" and i < len(lines):
                i += 1

        # Untracked files count as unstaged changes too
        if self.untrackedFiles:
            self.hasLUC = True

    def _onError(self, error: QProcess.ProcessError):
        process: QProcess = self.sender()
        if error == QProcess.FailedToStart:
            self._failedStart = True
            self.finished.emit()


class LogsFetcherQProcessWorker(LogsFetcherWorkerBase):

    _quitEventLoopRequested = Signal()

    def __init__(self, submodules: List[str], branchDir: str, noLocalChanges: bool, *args):
        super().__init__(submodules, branchDir, noLocalChanges, *args)

        self._fetchers: List[LogsFetcherImpl] = []
        self._finishedFetchers: list = []  # keep fetchers alive until explicit cleanup
        self._eventLoop = None

        self._lccCommit = Commit()
        self._lucCommit = Commit()

        self._queueTasks = []

        self._quitEventLoopRequested.connect(
            self._quitEventLoop, Qt.QueuedConnection)

    def run(self):
        if not self._submodules:
            self._fetchNormal()
        else:
            self._fetchComposite()

    def _onFetchNormalLogsFinished(self):
        fetcher = self.sender()
        self._fetchers.remove(fetcher)
        fetcher.deleteLater()
        self._finishedFetchers.append(fetcher)
        if not self._fetchers and self._eventLoop:
            self._eventLoop.quit()

    def _fetchNormal(self):
        self._eventLoop = QEventLoop()

        if self.isInterruptionRequested():
            self._quitEventLoop()
            self._eventLoop = None
            return

        fetcher = LogsFetcherImpl()
        fetcher.logsAvailable.connect(
            self.logsAvailable)
        fetcher.fetchFinished.connect(self._onFetchNormalLogsFinished)
        fetcher.cwd = self._branchDir
        self._fetchers.append(fetcher)

        fetcher.fetch(*self._args)

        lcFetcher = None
        if self.needLocalChanges():
            lcFetcher = LocalChangesFetcher(self._branchDir, False)
            lcFetcher.finished.connect(self._onFetchFinished)
            self._fetchers.append(lcFetcher)
            lcFetcher.fetch()

        self._eventLoop.exec()
        self._eventLoop = None

        if self.isInterruptionRequested():
            logger.debug("Logs fetcher cancelled")
            self._clearFetcher()
            return

        if lcFetcher:
            self.localChangesAvailable.emit(self._lccCommit, self._lucCommit)

        self._handleError(fetcher.errorData, fetcher._branch, fetcher.repoDir)

        for error, _ in self._errors.items():
            self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')

        self.fetchFinished.emit(fetcher._exitCode)
        self._finishedFetchers.clear()

    def _onFetchLogsFinished(self, fetcher: LogsFetcherImpl):
        repoDir = fetcher.repoDir

        self._handleCompositeLogs(
            fetcher.commits, repoDir, fetcher._branch,
            fetcher._exitCode, fetcher.errorData)

        self._scheduleCompositeEmit()

    def _onFetchLocalChangesFinished(self, fetcher: LocalChangesFetcher):
        hasLCC = fetcher.hasLCC
        hasLUC = fetcher.hasLUC
        untracked = fetcher.untrackedFiles if fetcher.untrackedFiles else None

        if hasLCC or hasLUC:
            repoDir = None
            if fetcher.isComposite:
                if fetcher._repoDir.startswith(self._branchDir):
                    repoDir = fetcher._repoDir[len(self._branchDir) + 1:]
                    if not repoDir:
                        repoDir = "."
            LogsFetcherWorkerBase._makeLocalCommits(
                self._lccCommit, self._lucCommit, hasLCC, hasLUC, repoDir, untracked)

    def _onFetchFinished(self):
        if self.isInterruptionRequested():
            logger.debug("Logs fetcher cancelled")
            self._clearFetcher()
            return

        fetcher = self.sender()
        self._fetchers.remove(fetcher)
        fetcher.deleteLater()
        self._finishedFetchers.append(fetcher)

        if self._queueTasks:
            nextFetcher = self._queueTasks.pop(0)
            self._fetchers.append(nextFetcher)
            if isinstance(nextFetcher, LogsFetcherImpl):
                nextFetcher.fetch(*self._args)
            else:
                nextFetcher.fetch()

        if isinstance(fetcher, LogsFetcherImpl):
            self._onFetchLogsFinished(fetcher)
        else:
            self._onFetchLocalChangesFinished(fetcher)

        if not self._fetchers and self._eventLoop:
            self._eventLoop.quit()

    def _fetchComposite(self):
        b = time.time()

        telemetry = ApplicationBase.instance().telemetry()
        span = telemetry.startTrace("fetchComposite")
        span.addTag("sm_count", len(self._submodules))

        logsArgs = self._args[1]
        paths = extractFilePaths(logsArgs)
        submodules = filterSubmoduleByPath(self._submodules, paths)

        self._exitCode = 0
        self._cleanupCompositeEmit()

        self._eventLoop = QEventLoop()
        MAX_QUEUE_SIZE = 32

        for submodule in submodules:
            if self.isInterruptionRequested():
                self._clearFetcher()
                self._eventLoop = None
                return
            fetcher = LogsFetcherImpl(submodule)
            if submodule != '.':
                fetcher.cwd = os.path.join(Git.REPO_DIR, submodule)
            fetcher.fetchFinished.connect(self._onFetchFinished)

            if len(self._fetchers) < MAX_QUEUE_SIZE:
                self._fetchers.append(fetcher)
                fetcher.fetch(*self._args)
            else:
                self._queueTasks.append(fetcher)

        if self.needLocalChanges():
            for submodule in submodules:
                if self.isInterruptionRequested():
                    self._clearFetcher()
                    self._eventLoop = None
                    return

                fetcher = LocalChangesFetcher(
                    fullRepoDir(submodule, self._branchDir), True)
                fetcher.finished.connect(self._onFetchFinished)

                if len(self._fetchers) < MAX_QUEUE_SIZE:
                    fetcher.fetch()
                    self._fetchers.append(fetcher)
                else:
                    self._queueTasks.append(fetcher)

        if self.isInterruptionRequested():
            self._clearFetcher()
            self._eventLoop = None
            span.setStatus(False, "cancelled")
            span.end()
            return

        self._eventLoop.exec()

        logger.debug("fetch elapsed: %fs", time.time() - b)

        if self.isInterruptionRequested():
            self._clearFetcher()
            logger.debug("Logs fetcher cancelled")
            span.setStatus(False, "cancelled")
            span.end()
            self._eventLoop = None
            return

        self._flushCompositeEmit()
        self.localChangesAvailable.emit(self._lccCommit, self._lucCommit)

        for error, _ in self._errors.items():
            self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')

        span.setStatus(True)
        span.end()

        self._eventLoop = None
        self.fetchFinished.emit(self._exitCode)
        self._finishedFetchers.clear()

    def requestInterruption(self):
        self._interruptionRequested = True
        if not self._eventLoop:
            return

        if self.thread() == QThread.currentThread():
            self._quitEventLoop()
        else:
            self._quitEventLoopRequested.emit()
        # we don't cancel fetchers here, because we have to cancel
        # in the thread is was started

    def _quitEventLoop(self):
        if self._eventLoop:
            self._eventLoop.quit()

    def _clearFetcher(self):
        self._queueTasks.clear()
        for fetcher in self._fetchers:
            fetcher.cancel()
        self._fetchers.clear()
        self._finishedFetchers.clear()
        self._cleanupCompositeEmit()
