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
        # event loops run() is done with: kept referenced so that they are not
        # destroyed in this worker thread (see _retireEventLoop)
        self._finishedEventLoops: List[QEventLoop] = []

        self._lccCommit = Commit()
        self._lucCommit = Commit()

        self._queueTasks = []

        # Track local-changes fetcher completion so localChangesAvailable
        # can be emitted as soon as all LocalChangesFetchers finish, without
        # waiting for log fetchers to complete.
        self._localChangesTotal = 0
        self._localChangesDone = 0
        self._localChangesEmitted = False

        self._quitEventLoopRequested.connect(
            self._quitEventLoop, Qt.QueuedConnection)

    def run(self):
        if not self._submodules:
            self._fetchNormal()
        else:
            self._fetchComposite()

    def _retireEventLoop(self):
        """Drop the event loop reference without destroying it here.

        The loop was created in this worker thread, and destroying it in this
        thread takes Qt object locks and then waits for the Python GIL — which
        the GUI thread holds while waiting for those very locks, freezing the
        whole process. The reference is kept until
        releaseFinishedFetchers() drops it from the GUI thread, once this
        thread has stopped.
        """
        if self._eventLoop is not None:
            self._finishedEventLoops.append(self._eventLoop)
            self._eventLoop = None

    def _onFetchNormalLogsFinished(self):
        fetcher = self.sender()
        self._fetchers.remove(fetcher)
        # Do NOT call fetcher.deleteLater() here: the DeferredDelete would be
        # processed by this thread's event loop with the GIL released, and
        # destroying the QObject acquires Qt locks while Shiboken waits for
        # the GIL — deadlocking against the GUI thread which holds the GIL
        # while waiting for those Qt locks. The fetcher stays alive in
        # _finishedFetchers and is released in the GUI thread by
        # releaseFinishedFetchers().
        self._finishedFetchers.append(fetcher)
        if not self._fetchers and self._eventLoop:
            self._eventLoop.quit()

    def _fetchNormal(self):
        self._eventLoop = QEventLoop()

        if self.isInterruptionRequested():
            self._quitEventLoop()
            self._retireEventLoop()
            return

        # Start local-changes fetcher first (fast: git status) so local
        # changes appear before the log fetch (slow: git log) completes.
        if self.needLocalChanges():
            lcFetcher = LocalChangesFetcher(self._branchDir, False)
            lcFetcher.finished.connect(self._onFetchFinished)
            self._fetchers.append(lcFetcher)
            lcFetcher.fetch()
            self._localChangesTotal = 1

        fetcher = LogsFetcherImpl()
        fetcher.logsAvailable.connect(
            self.logsAvailable)
        fetcher.fetchFinished.connect(self._onFetchNormalLogsFinished)
        fetcher.cwd = self._branchDir
        self._fetchers.append(fetcher)

        fetcher.fetch(*self._args)

        self._eventLoop.exec()
        self._retireEventLoop()

        if self.isInterruptionRequested():
            logger.debug("Logs fetcher cancelled")
            self._clearFetcher()
            return

        # localChangesAvailable was already emitted in _onFetchLocalChangesFinished
        # as soon as the LocalChangesFetcher finished. Emit here only as a fallback.
        if not self._localChangesEmitted:
            self.localChangesAvailable.emit(self._lccCommit, self._lucCommit)

        self._handleError(fetcher.errorData, fetcher._branch, fetcher.repoDir)

        for error, _ in self._errors.items():
            self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')

        self.fetchFinished.emit(fetcher._exitCode)
        # The local-change commits were emitted and are owned by the
        # consumer now; drop our references.
        self._lccCommit = Commit()
        self._lucCommit = Commit()

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

        self._localChangesDone += 1
        # Emit once all local-changes fetchers are done so local changes
        # appear before log fetchers complete (they started first and are fast).
        if (self._localChangesTotal > 0
                and self._localChangesDone >= self._localChangesTotal
                and not self._localChangesEmitted):
            self._localChangesEmitted = True
            self.localChangesAvailable.emit(self._lccCommit, self._lucCommit)

    def _onFetchFinished(self):
        if self.isInterruptionRequested():
            logger.debug("Logs fetcher cancelled")
            self._clearFetcher()
            return

        fetcher = self.sender()
        self._fetchers.remove(fetcher)
        # Do NOT deleteLater() here — see the comment in
        # _onFetchNormalLogsFinished. Released in the GUI thread instead.
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

        # Start local-changes fetchers first (they are fast: git status),
        # then log fetchers (they are slow: git log). Both run concurrently,
        # but local changes get priority for the limited QProcess slots so
        # they appear at the top of the list as early as possible.
        if self.needLocalChanges():
            for submodule in submodules:
                if self.isInterruptionRequested():
                    self._clearFetcher()
                    self._retireEventLoop()
                    return

                fetcher = LocalChangesFetcher(
                    fullRepoDir(submodule, self._branchDir), True)
                fetcher.finished.connect(self._onFetchFinished)

                if len(self._fetchers) < MAX_QUEUE_SIZE:
                    fetcher.fetch()
                    self._fetchers.append(fetcher)
                else:
                    self._queueTasks.append(fetcher)
            self._localChangesTotal = len(submodules)

        for submodule in submodules:
            if self.isInterruptionRequested():
                self._clearFetcher()
                self._retireEventLoop()
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

        if self.isInterruptionRequested():
            self._clearFetcher()
            self._retireEventLoop()
            span.setStatus(False, "cancelled")
            span.end()
            return

        self._eventLoop.exec()

        logger.debug("fetch elapsed: %fs, localChangesEmitted=%s",
                     time.time() - b, self._localChangesEmitted)

        if self.isInterruptionRequested():
            self._clearFetcher()
            logger.debug("Logs fetcher cancelled")
            span.setStatus(False, "cancelled")
            span.end()
            self._retireEventLoop()
            return

        self._flushCompositeEmit()
        # localChangesAvailable was already emitted incrementally as each
        # LocalChangesFetcher finished. Emit here only as a fallback if
        # there were no local changes fetchers or none had changes.
        if not self._localChangesEmitted:
            self.localChangesAvailable.emit(self._lccCommit, self._lucCommit)
        self._localChangesEmitted = True

        for error, _ in self._errors.items():
            self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')

        span.setStatus(True)
        span.end()

        self._retireEventLoop()
        self.fetchFinished.emit(self._exitCode)
        # All data-carrying signals have been queued and are owned by their
        # receivers now; drop our copy so a lingering worker wrapper does
        # not retain the whole commit set (see _releaseCompositeData).
        self._releaseCompositeData()
        self._lccCommit = Commit()
        self._lucCommit = Commit()

    def releaseData(self):
        """Release fetch data retained by this worker (see base class).

        Also drops the local-change commits: they were emitted to the
        consumer, which keeps its own references.
        """
        super().releaseData()
        self._lccCommit = Commit()
        self._lucCommit = Commit()

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
        for fetcher in self._fetchers:
            fetcher.cancel()
        # Keep every fetcher alive: destroying QObjects in this worker thread
        # can deadlock against the GUI thread (this thread would hold the
        # Python GIL while acquiring Qt object locks that the GUI thread may
        # hold while waiting for the GIL). They are released in the GUI
        # thread by releaseFinishedFetchers() once this thread has stopped.
        self._finishedFetchers.extend(self._fetchers)
        self._fetchers.clear()
        self._finishedFetchers.extend(self._queueTasks)
        self._queueTasks.clear()
        self._cleanupCompositeEmit()

    def releaseFinishedFetchers(self):
        """Drop references to all fetchers so they are destroyed.

        Must be called from the GUI thread after the worker thread has
        stopped. Destroying the fetchers (and their QProcess children) in
        the worker thread deadlocks: the worker would hold the Python GIL
        while acquiring Qt object locks that the GUI thread may hold while
        waiting for the GIL (e.g. inside QMetaObject::activate delivering a
        signal to a Python slot).
        """
        self._finishedFetchers.clear()
        # same reasoning for the event loops run() retired (see
        # _retireEventLoop)
        self._finishedEventLoops.clear()
