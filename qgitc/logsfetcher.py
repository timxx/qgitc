# -*- coding: utf-8 -*-

import os
import time
from ast import Dict
from datetime import date, datetime, timedelta
from sys import version_info
from typing import List

from PySide6.QtCore import SIGNAL, QEventLoop, QObject, QProcess, QThread, Signal

from qgitc.applicationbase import ApplicationBase
from qgitc.common import (
    Commit,
    MyLineProfile,
    MyProfile,
    extractFilePaths,
    filterSubmoduleByPath,
    fullRepoDir,
    isRevisionRange,
    logger,
    toSubmodulePath,
)
from qgitc.datafetcher import DataFetcher
from qgitc.gitutils import Git, GitProcess

log_fmt = "%H%x01%B%x01%an <%ae>%x01%ai%x01%cn <%ce>%x01%ci%x01%P"


class LogsFetcherImpl(DataFetcher):

    logsAvailable = Signal(list)

    def __init__(self, repoDir=None, parent=None):
        super().__init__(parent)
        self.separator = b'\0'
        self.repoDir = repoDir
        self._branch: bytes = None
        self.commits: List[Commit] = []

    def parse(self, data: bytes):
        logs = data.rstrip(self.separator) \
            .decode("utf-8", "replace") \
            .split('\0')

        commits = []
        for log in logs:
            commit = Commit.fromRawString(log)
            if not commit or not commit.sha1:
                continue
            commit.repoDir = self.repoDir
            if self.repoDir:
                isoDate = ''
                if version_info < (3, 11):
                    isoDate = commit.committerDate.replace(
                        ' ', 'T', 1).replace(' ', '', 1)
                    isoDate = isoDate[:-2] + ':' + isoDate[-2:]
                else:
                    isoDate = commit.committerDate
                commit.committerDateTime = datetime.fromisoformat(isoDate)
            commits.append(commit)

        if self.repoDir:
            self.commits.extend(commits)
        else:
            self.logsAvailable.emit(commits)

    def makeArgs(self, args):
        branch = args[0]
        logArgs = args[1]
        self._branch = branch.encode("utf-8") if branch else None

        hasRevisionRange = self.hasRevisionRange(logArgs)
        if branch and (branch.startswith("(HEAD detached") or hasRevisionRange):
            branch = None

        git_args = ["log", "-z", "--topo-order",
                    "--parents",
                    "--no-color",
                    "--pretty=format:{0}".format(log_fmt)]

        needBoundary = True
        paths = None
        # reduce commits to analyze
        if self.repoDir and not self.hasSinceArg(logArgs) and not hasRevisionRange:
            paths = extractFilePaths(logArgs) if logArgs else None
            if not paths:
                days = ApplicationBase.instance().settings().maxCompositeCommitsSince()
                if days > 0:
                    since = date.today() - timedelta(days=days)
                    git_args.append(f"--since={since.isoformat()}")
                    needBoundary = False

        if branch:
            git_args.append(branch)

        if logArgs:
            if self.repoDir and self.repoDir != ".":
                paths = paths or extractFilePaths(logArgs)
                if paths:
                    for arg in logArgs:
                        if arg not in paths and arg != "--":
                            git_args.append(arg)
                    git_args.append("--")
                    for path in paths:
                        git_args.append(toSubmodulePath(self.repoDir, path))
                else:
                    git_args.extend(logArgs)
            else:
                git_args.extend(logArgs)
        elif needBoundary:
            git_args.append("--boundary")

        return git_args

    def isLoading(self):
        return self.process is not None

    @staticmethod
    def hasSinceArg(args: List[str]):
        if not args:
            return False
        for arg in args:
            if arg.startswith("--since"):
                return True
        return False

    @staticmethod
    def hasRevisionRange(args: List[str]):
        if not args:
            return False
        for arg in args:
            if isRevisionRange(arg):
                return True
        return False


class LocalChangesFetcher(QObject):
    finished = Signal()

    def __init__(self, repoDir=None, parent=None):
        super().__init__(parent)
        self._repoDir = repoDir
        self._lccProcess: QProcess = None
        self._lucProcess: QProcess = None

        self.hasLCC = False
        self.hasLUC = False

    def fetch(self):
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

        process.start(GitProcess.GIT_BIN, args)

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


class LogsFetcherWorker(QObject):

    localChangesAvailable = Signal(Commit, Commit)
    logsAvailable = Signal(list)
    fetchFinished = Signal(int)

    def __init__(self, submodules: List[str], branchDir: str, *args):
        super().__init__()
        self._args = args

        self._errors = {}  # error: repo
        self._errorData = b''
        self._exitCode = 0

        self._fetchers: List[LogsFetcherImpl] = []
        self._submodules = submodules.copy()
        self._eventLoop = None
        self._branchDir = branchDir

        self._mergedLogs: Dict[any, Commit] = {}
        self._lccCommit = Commit()
        self._lucCommit = Commit()

        self._queueTasks = []

        self._interruptionRequested = False

    def run(self):
        # profile = MyProfile()
        # lineProfile = MyLineProfile(Commit.fromRawString)

        if not self._submodules:
            self._fetchNormal()
        else:
            self._fetchComposite()

        # del profile

    @staticmethod
    def _makeLocalCommits(lccCommit: Commit, lucCommit: Commit, hasLCC, hasLUC, repoDir=None):
        if hasLCC:
            lccCommit.sha1 = Git.LCC_SHA1
            if not lccCommit.repoDir:
                lccCommit.repoDir = repoDir
            else:
                subCommit = Commit()
                subCommit.sha1 = Git.LCC_SHA1
                subCommit.repoDir = repoDir
                lccCommit.subCommits.append(subCommit)

        if hasLUC:
            lucCommit.sha1 = Git.LUC_SHA1
            if not lucCommit.repoDir:
                lucCommit.repoDir = repoDir
            else:
                subCommit = Commit()
                subCommit.sha1 = Git.LUC_SHA1
                subCommit.repoDir = repoDir
                lucCommit.subCommits.append(subCommit)

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
        self._fetchers.append(fetcher)

        fetcher.fetch(*self._args)

        lcFetcher = None
        if not self._args[1]:
            lcFetcher = LocalChangesFetcher()
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

    @staticmethod
    def _isSameRepoCommit(commit: Commit, repoDir: str):
        if commit.repoDir == repoDir:
            return True
        for commit in commit.subCommits:
            if commit.repoDir == repoDir:
                return True
        return False

    def _onFetchLogsFinished(self, fetcher: LogsFetcherImpl):
        repoDir = fetcher.repoDir
        handleCount = 0

        for log in fetcher.commits:
            handleCount += 1
            if handleCount % 100 == 0 and self.isInterruptionRequested():
                logger.debug("Logs fetcher cancelled")
                self._clearFetcher()
                return
            # require same day at least
            key = (log.committerDateTime.date(),
                   log.comments, log.author)
            if key in self._mergedLogs.keys():
                main_commit = self._mergedLogs[key]
                # don't merge commits in same repo
                if LogsFetcherWorker._isSameRepoCommit(main_commit, repoDir):
                    self._mergedLogs[log.sha1] = log
                else:
                    main_commit.subCommits.append(log)
            else:
                self._mergedLogs[key] = log

        self._exitCode |= fetcher._exitCode
        self._handleError(fetcher.errorData, fetcher._branch, repoDir)

    def _onFetchLocalChangesFinished(self, fetcher: LocalChangesFetcher):
        hasLCC = fetcher.hasLCC
        hasLUC = fetcher.hasLUC

        if hasLCC or hasLUC:
            self._makeLocalCommits(
                self._lccCommit, self._lucCommit, hasLCC, hasLUC, fetcher._repoDir)

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

        if not self._args[1]:
            b = time.time()
            for submodule in submodules:
                if self.isInterruptionRequested():
                    self._clearFetcher()
                    return

                fetcher = LocalChangesFetcher(
                    fullRepoDir(submodule, self._branchDir))
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
            return

        self.localChangesAvailable.emit(self._lccCommit, self._lucCommit)

        if self._mergedLogs:
            sortedLogs = sorted(self._mergedLogs.values(),
                                key=lambda x: x.committerDateTime, reverse=True)
            self.logsAvailable.emit(sortedLogs)
            self._mergedLogs.clear()

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

    def isInterruptionRequested(self):
        return self._interruptionRequested

    def _clearFetcher(self):
        self._queueTasks.clear()
        for fetcher in self._fetchers:
            fetcher.cancel()
        self._fetchers.clear()

    @property
    def errorData(self):
        return self._errorData

    def _handleError(self, errorData, branch, repoDir):
        if errorData and errorData not in self._errors:
            if not self._submodules or not self._isIgnoredError(errorData, branch):
                self._errors[errorData] = repoDir

    def _isIgnoredError(self, error: bytes, branch: bytes):
        msgs = [b"fatal: ambiguous argument '%s': unknown revision or path" % branch,
                b"fatal: bad revision '%s'" % branch]
        for msg in msgs:
            if error.startswith(msg):
                return True
        return False


class LogsFetcher(QObject):

    localChangesAvailable = Signal(Commit, Commit)
    logsAvailable = Signal(list)
    fetchFinished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: LogsFetcherWorker = None
        self._thread: QThread = None
        self._submodules: List[str] = []
        self._errorData = b''
        self._threads: List[QThread] = []

    def setSubmodules(self, submodules: List[str]):
        self._submodules = submodules

    def fetch(self, *args, branchDir=None):
        self.cancel()
        self._errorData = b''
        self._worker = LogsFetcherWorker(self._submodules, branchDir, *args)
        self._worker.logsAvailable.connect(self._onLogsAvailable)
        self._worker.fetchFinished.connect(self._onFetchFinished)
        self._worker.localChangesAvailable.connect(
            self._onLocalChangesAvailable)

        self._thread = QThread()
        self._thread.finished.connect(self._onThreadFinished)
        self._thread.started.connect(self._worker.run)
        self._worker.moveToThread(self._thread)
        self._thread.start()

        self._threads.append(self._thread)

    def cancel(self, force=False):
        if self._worker:
            self._worker.logsAvailable.disconnect(self._onLogsAvailable)
            self._worker.fetchFinished.disconnect(self._onFetchFinished)
            self._worker.localChangesAvailable.disconnect(
                self._onLocalChangesAvailable)
            self._worker.requestInterruption()
            self._worker.deleteLater()

        if self._thread and self._thread.isRunning():
            self._thread.quit()

            if force and ApplicationBase.instance().terminateThread(self._thread):
                self._threads.remove(self._thread)
                self._thread.finished.disconnect(self._onThreadFinished)
                logger.warning("Terminating logs fetcher thread")
                self._thread = None

        if not force:
            return

        for thread in self._threads:
            thread.finished.disconnect(self._onThreadFinished)
            ApplicationBase.instance().terminateThread(thread)
        self._threads.clear()

    def isLoading(self):
        return self._thread is not None and \
            self._thread.isRunning()

    def _onLogsAvailable(self, logs: List[Commit]):
        worker = self.sender()
        if worker == self._worker:
            self.logsAvailable.emit(logs)
        else:
            logger.info("_onLogsAvailable but thread changed")

    def _onFetchFinished(self, exitCode):
        worker = self.sender()
        if not worker:
            return

        if worker == self._worker:
            self._thread.quit()
            self._errorData = self._worker.errorData
            self._worker = None
            self.fetchFinished.emit(exitCode)
        else:
            logger.info("_onFetchFinished but thread changed")

    def _onLocalChangesAvailable(self, lccCommit: Commit, lucCommit: Commit):
        worker = self.sender()
        if worker == self._worker:
            self.localChangesAvailable.emit(lccCommit, lucCommit)
        else:
            logger.info("_onLocalChangesAvailable but thread changed")

    def _onThreadFinished(self):
        thread = self.sender()
        if thread in self._threads:
            self._threads.remove(thread)

    @property
    def errorData(self):
        return self._errorData
