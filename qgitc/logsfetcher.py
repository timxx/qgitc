# -*- coding: utf-8 -*-

from datetime import date, datetime, timedelta
import os
from typing import List
from PySide6.QtCore import (
    Signal,
    SIGNAL,
    QThread,
    QEventLoop,
    QObject
)

from .common import Commit, MyProfile
from .datafetcher import DataFetcher
from .gitutils import Git


log_fmt = "%H%x01%B%x01%an <%ae>%x01%ai%x01%cn <%ce>%x01%ci%x01%P"


class LogsFetcherImpl(DataFetcher):

    logsAvailable = Signal(list)

    def __init__(self, repoDir=None, parent=None):
        super().__init__(parent)
        self.separator = b'\0'
        self.repoDir = repoDir
        self._branch: bytes = None

    def parse(self, data: bytes):
        logs = data.rstrip(self.separator) \
            .decode("utf-8", "replace") \
            .split('\0')

        commits = []
        for log in logs:
            commit = Commit.fromRawString(log)
            if not commit.sha1:
                continue
            commit.repoDir = self.repoDir
            if self.repoDir:
                commit.committerDateTime = datetime.strptime(
                    commit.committerDate, "%Y-%m-%d %H:%M:%S %z")
            commits.append(commit)

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

        # reduce commits to analyze
        if self.repoDir and not self.hasSinceArg(logArgs):
            since = date.today() - timedelta(days=14)
            git_args.append(f"--since={since.isoformat()}")

        if branch:
            git_args.append(branch)

        if logArgs:
            git_args.extend(logArgs)
        else:
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


# the builtin bisect key required python >= 3.10
def insort_logs(a: List[Commit], x: Commit):
    lo = 0
    hi = len(a)

    xDate = x.committerDateTime
    while lo < hi:
        mid = (lo + hi) // 2
        t = a[mid].committerDateTime
        if xDate < t:
            lo = mid + 1
        else:
            hi = mid
    a.insert(lo, x)


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
        self._exitCode = 0

    def fetch(self, *args):
        self._args = args
        self.start()

    def run(self):
        # profile = MyProfile()
        self._eventLoop = QEventLoop()
        mergedLogs: List[Commit] = []

        needComposite = False
        self._fetchers.clear()
        if not self._submodules:
            fetcher = LogsFetcherImpl()
            fetcher.logsAvailable.connect(
                self.logsAvailable)
            fetcher.fetchFinished.connect(self._onFetchFinished)
            self._fetchers.append(fetcher)
        else:
            needComposite = True
            for submodule in self._submodules:
                fetcher = LogsFetcherImpl(submodule)
                fetcher.logsAvailable.connect(self._onLogsAvailable)
                fetcher.fetchFinished.connect(self._onFetchFinished)
                if submodule != '.':
                    fetcher.cwd = os.path.join(Git.REPO_DIR, submodule)
                self._fetchers.append(fetcher)
        for fetcher in self._fetchers:
            if self.isInterruptionRequested():
                return
            fetcher.fetch(*self._args)

        self._eventLoop.exec()
        self._eventLoop = None

        if not needComposite:
            return

        self._logs = dict(sorted(self._logs.items(), key=lambda item: len(item[1]), reverse=True))
        firstRepo = True

        for _, logs in self._logs.items():
            for log in logs:
                if self.isInterruptionRequested():
                    self._clearFetcher()
                    return
                # no need to merge for the first repo (all the logs from same repo)
                if not firstRepo and self.mergeLog(mergedLogs, log):
                    continue
                logDate = log.committerDateTime
                if len(mergedLogs) == 0 or logDate < mergedLogs[-1].committerDateTime:
                    mergedLogs.append(log)
                elif logDate > mergedLogs[0].committerDateTime:
                    mergedLogs.insert(0, log)
                else:
                    insort_logs(mergedLogs, log)
            firstRepo = False

        if mergedLogs:
            self.logsAvailable.emit(mergedLogs)
        self.fetchFinished.emit(self._exitCode)
        # profile = None

    #TODO: binary search???
    def mergeLog(self, mergedLogs: List[Commit], target: Commit):
        for log in mergedLogs:
            if self.isInterruptionRequested():
                return True

            targetDate = target.committerDateTime
            logDate = log.committerDateTime
            # since mergedLogs is sorted by committerDate, we can break here
            if targetDate.year > logDate.year or targetDate.month > logDate.month or targetDate.day > logDate.day:
                return False

            if log.repoDir == target.repoDir:
                continue
            if target.author == log.author and target.comments == log.comments:
                log.subCommits.append(target)
                # require same day at least
                return targetDate.day == logDate.day and \
                    targetDate.month == logDate.month and \
                    targetDate.year == logDate.year
        return False

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

    def _onFetchFinished(self, exitCode):
        sender: LogsFetcherImpl = self.sender()
        if not sender:
            return

        if sender.errorData and sender.errorData not in self._errors:
            if not self._submodules or not self._isIgnoredError(sender.errorData, sender._branch):
                self._errors[sender.errorData] = sender.repoDir

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

        self._exitCode |= exitCode

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
