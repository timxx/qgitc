# -*- coding: utf-8 -*-

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import os
import time
from typing import List
from PySide6.QtCore import (
    Signal,
    SIGNAL,
    QThread,
    QEventLoop,
    QObject
)

from .common import Commit, MyProfile, MyLineProfile
from .datafetcher import DataFetcher
from .gitutils import Git
from sys import version_info


log_fmt = "%H%x01%B%x01%an <%ae>%x01%ai%x01%cn <%ce>%x01%ci%x01%P"


class LogsFetcherImpl(DataFetcher):

    logsAvailable = Signal(list)

    def __init__(self, repoDir=None, parent=None):
        super().__init__(parent)
        self.separator = b'\0'
        self.repoDir = repoDir
        self._branch: bytes = None
        self.commits = []

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

        if branch and branch.startswith("(HEAD detached"):
            branch = None

        git_args = ["log", "-z", "--topo-order",
                    "--parents",
                    "--no-color",
                    "--pretty=format:{0}".format(log_fmt)]

        needBoundary = True
        # reduce commits to analyze
        if self.repoDir and not self.hasSinceArg(logArgs):
            days = qApp.settings().maxCompositeCommitsSince()
            if days > 0:
                since = date.today() - timedelta(days=days)
                git_args.append(f"--since={since.isoformat()}")
                needBoundary = False

        if branch:
            git_args.append(branch)

        if logArgs:
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


class LogsFetcherThread(QThread):

    logsAvailable = Signal(list)
    fetchFinished = Signal(int)

    def __init__(self, submodules, parent=None):
        super().__init__(parent)
        self._errors = {}  # error: repo
        self._errorData = b''
        self._fetchers = []
        self._logs = {}  # repo: logs
        self._submodules = submodules.copy()
        self._eventLoop = None

    def fetch(self, *args):
        self._args = args
        self.start()

    def run(self):
        # profile = MyProfile()
        # lineProfile = MyLineProfile(Commit.fromRawString)

        self._fetchers.clear()
        if not self._submodules:
            self._fetchNormal()
        else:
            self._fetchComposite()

        # del profile

    def _fetchNormal(self):
        self._eventLoop = QEventLoop()

        fetcher = LogsFetcherImpl()
        fetcher.logsAvailable.connect(
            self.logsAvailable)
        fetcher.fetchFinished.connect(self._onFetchFinished)
        self._fetchers.append(fetcher)

        fetcher.fetch(*self._args)
        self._eventLoop.exec()
        self._eventLoop = None

    def _fetchComposite(self):
        def _fetch(submodule):
            fetcher = LogsFetcherImpl(submodule)
            if submodule != '.':
                fetcher.cwd = os.path.join(Git.REPO_DIR, submodule)
            fetcher.fetch(*self._args)
            fetcher._process.waitForFinished()
            return fetcher._exitCode, fetcher._errorData, \
                fetcher._branch, fetcher.repoDir, fetcher.commits

        # b = time.time()

        max_workers = max(2, os.cpu_count() - 2)
        executor = ThreadPoolExecutor(max_workers=max_workers)
        tasks = [executor.submit(_fetch, submodule)
                 for submodule in self._submodules]

        mergedLogs = {}
        handleCount = 0
        exitCode = 0

        for task in as_completed(tasks):
            if self.isInterruptionRequested():
                return
            code, errorData, branch, repoDir, logs = task.result()
            for log in logs:
                handleCount += 1
                if handleCount % 100 == 0 and self.isInterruptionRequested():
                    return
                # require same day at least
                key = (log.committerDateTime.date(), log.comments, log.author)
                if key in mergedLogs.keys():
                    mergedLogs[key].subCommits.append(log)
                else:
                    mergedLogs[key] = log

            exitCode |= code
            self._handleError(errorData, branch, repoDir)

        # print(f"fetch elapsed: {time.time() - b}")
        # b = time.time()

        if mergedLogs:
            sortedLogs = sorted(mergedLogs.values(),
                                key=lambda x: x.committerDateTime, reverse=True)
            self.logsAvailable.emit(sortedLogs)

        # print(f"sort elapsed: {time.time() - b}")
        for error, _ in self._errors.items():
            self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')
        self.fetchFinished.emit(exitCode)

    def cancel(self):
        self.requestInterruption()
        if self._eventLoop:
            self._eventLoop.quit()
        self.wait(50)

    def _clearFetcher(self):
        for fetcher in self._fetchers:
            fetcher.cancel()

    @property
    def errorData(self):
        return self._errorData

    def _handleError(self, errorData, branch, repoDir):
        if errorData and errorData not in self._errors:
            if not self._submodules or not self._isIgnoredError(errorData, branch):
                self._errors[errorData] = repoDir

    def _onFetchFinished(self, exitCode):
        sender: LogsFetcherImpl = self.sender()
        if not sender:
            return

        self._handleError(sender.errorData, sender._branch, sender.repoDir)

        self._fetchers.remove(sender)
        if not self._fetchers:
            if self._eventLoop:
                self._eventLoop.quit()
            for error, repo in self._errors.items():
                self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')

            if not self._submodules:
                if self._logs:
                    self.logsAvailable.emit(list(self._logs.keys()))
                self.fetchFinished.emit(exitCode)

    def _onLogsAvailable(self, logs):
        repoDir = self.sender().repoDir
        if repoDir in self._logs:
            self._logs[repoDir].extend(logs)
        else:
            self._logs[repoDir] = logs

    def _isIgnoredError(self, error: bytes, branch: bytes):
        msgs = [b"fatal: ambiguous argument '%s': unknown revision or path" % branch,
                b"fatal: bad revision '%s'" % branch]
        for msg in msgs:
            if error.startswith(msg):
                return True
        return False


class LogsFetcher(QObject):

    logsAvailable = Signal(list)
    fetchFinished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._submodules = []
        self._errorData = b''

    def setSubmodules(self, submodules):
        self._submodules = submodules

    def fetch(self, *args):
        self.cancel()
        self._errorData = b''
        self._thread = LogsFetcherThread(self._submodules, self)
        self._thread.logsAvailable.connect(self.logsAvailable)
        self._thread.fetchFinished.connect(self._onFetchFinished)
        self._thread.fetch(*args)

    def cancel(self):
        if self._thread:
            self._thread.disconnect(self)
            self._thread.cancel()
            self._thread = None

    def isLoading(self):
        return self._thread is not None and \
            self._thread.isRunning()

    def _onFetchFinished(self, exitCode):
        if self._thread:
            self._errorData = self._thread.errorData
            self._thread = None
            self.fetchFinished.emit(exitCode)

    @property
    def errorData(self):
        return self._errorData
