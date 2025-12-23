# -*- coding: utf-8 -*-

import os
import time
from typing import List

from PySide6.QtCore import SIGNAL, QEventLoop, QObject, QProcess, Signal

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
        self._lccProcess: QProcess = None
        self._lucProcess: QProcess = None
        self._failedStart = set()
        self.isComposite = isComposite

        self.hasLCC = False
        self.hasLUC = False

    def fetch(self):
        self._failedStart.clear()
        self._lccProcess = self._startProcess(True)
        self._lucProcess = self._startProcess(False)

    def cancel(self):
        self._cancelProcess(self._lccProcess)
        self._cancelProcess(self._lucProcess)

        self.hasLCC = False
        self.hasLUC = False
        self._lucProcess = None
        self._lccProcess = None

    def _startProcess(self, cached: bool):
        args = ["diff", "--quiet", "-s"]
        if cached:
            args.append("--cached")
        if Git.versionGE(1, 7, 2):
            args.append("--ignore-submodules=dirty")

        process = QProcess()
        process.setWorkingDirectory(self._repoDir or Git.REPO_DIR)
        process.finished.connect(self._onFinished)
        process.errorOccurred.connect(self._onError)

        process.start(GitProcess.GIT_BIN, args)
        if process in self._failedStart:
            return None

        return process

    def _cancelProcess(self, process: QProcess):
        if not process:
            return

        QObject.disconnect(process, SIGNAL(
            "finished(int, QProcess::ExitStatus)"), self._onFinished)
        process.close()
        process.waitForFinished(50)
        if process.state() == QProcess.Running:
            logger.warning("Kill git process")
            process.kill()

    def _onFinished(self, exitCode, exitStatus):
        process = self.sender()
        if process == self._lccProcess:
            self.hasLCC = exitCode == 1
            self._lccProcess = None
        else:
            self.hasLUC = exitCode == 1
            self._lucProcess = None

        if not self._lccProcess and not self._lucProcess:
            self.finished.emit()

    def _onError(self, error: QProcess.ProcessError):
        process: QProcess = self.sender()
        if error == QProcess.FailedToStart:
            self._failedStart.add(process)
            if len(self._failedStart) == 2:
                self.finished.emit()


class LogsFetcherQProcessWorker(LogsFetcherWorkerBase):

    def __init__(self, submodules: List[str], branchDir: str, noLocalChanges: bool, *args):
        super().__init__(submodules, branchDir, noLocalChanges, *args)

        self._fetchers: List[LogsFetcherImpl] = []
        self._eventLoop = None

        self._lccCommit = Commit()
        self._lucCommit = Commit()

        self._queueTasks = []

    def run(self):
        if not self._submodules:
            self._fetchNormal()
        else:
            self._fetchComposite()

    def _onFetchNormalLogsFinished(self):
        fetcher = self.sender()
        self._fetchers.remove(fetcher)
        if not self._fetchers and self._eventLoop:
            self._eventLoop.quit()

    def _fetchNormal(self):
        self._eventLoop = QEventLoop()

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

    def _onFetchLogsFinished(self, fetcher: LogsFetcherImpl):
        repoDir = fetcher.repoDir

        self._handleCompositeLogs(
            fetcher.commits, repoDir, fetcher._branch,
            fetcher._exitCode, fetcher.errorData)

        if Git.RUN_SLOW and self._fetchers and isinstance(self._fetchers[0], LocalChangesFetcher):
            self._emitCompositeLogsAvailable()

    def _onFetchLocalChangesFinished(self, fetcher: LocalChangesFetcher):
        hasLCC = fetcher.hasLCC
        hasLUC = fetcher.hasLUC

        if hasLCC or hasLUC:
            repoDir = None
            if fetcher.isComposite:
                if fetcher._repoDir.startswith(self._branchDir):
                    repoDir = fetcher._repoDir[len(self._branchDir) + 1:]
                    if not repoDir:
                        repoDir = "."
            LogsFetcherWorkerBase._makeLocalCommits(
                self._lccCommit, self._lucCommit, hasLCC, hasLUC, repoDir)

    def _onFetchFinished(self):
        if self.isInterruptionRequested():
            logger.debug("Logs fetcher cancelled")
            self._clearFetcher()
            return

        fetcher = self.sender()
        self._fetchers.remove(fetcher)

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
        self._mergedLogs.clear()

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

        self._eventLoop.exec()

        logger.debug("fetch elapsed: %fs", time.time() - b)

        if self.isInterruptionRequested():
            self._clearFetcher()
            logger.debug("Logs fetcher cancelled")
            span.setStatus(False, "cancelled")
            span.end()
            self._eventLoop = None
            return

        self.localChangesAvailable.emit(self._lccCommit, self._lucCommit)

        self._emitCompositeLogsAvailable()

        for error, _ in self._errors.items():
            self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')

        span.setStatus(True)
        span.end()

        self._eventLoop = None
        self.fetchFinished.emit(self._exitCode)

    def requestInterruption(self):
        self._interruptionRequested = True
        if self._eventLoop:
            self._eventLoop.quit()
        # we don't cancel fetchers here, because we have to cancel
        # in the thread is was started

    def _clearFetcher(self):
        self._queueTasks.clear()
        for fetcher in self._fetchers:
            fetcher.cancel()
        self._fetchers.clear()
