# -*- coding: utf-8 -*-

from datetime import date, datetime, timedelta
import os
from typing import List
from PySide6.QtCore import (
    Signal,
    QThread,
    QEventLoop
)

from .common import Commit
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
        if self.repoDir:
            last_week = date.today() - timedelta(days=7)
            git_args.append(f"--since={last_week.isoformat()}")

        if branch:
            git_args.append(branch)

        if logArgs:
            git_args.extend(logArgs)
        else:
            git_args.append("--boundary")

        return git_args

    def isLoading(self):
        return self.process is not None


def makeDateTime(dateStr: str):
    return datetime.strptime(dateStr, "%Y-%m-%d %H:%M:%S %z")


# the builtin bisect key required python >= 3.10
def insort_logs(a: List[Commit], x: Commit):
    lo = 0
    hi = len(a)

    xDate = makeDateTime(x.committerDate)
    while lo < hi:
        mid = (lo + hi) // 2
        t = makeDateTime(a[mid].committerDate)
        if xDate < t:
            lo = mid + 1
        else:
            hi = mid
    a.insert(lo, x)


class LogsFetcher(QThread):

    logsAvailable = Signal(list)
    fetchFinished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._errors = {}  # error: repo
        self._errorData = b''
        self._fetchers = []
        self._logs = {}  # repo: logs
        self._needComposite = False
        self._submodules = []
        self._eventLoop = None
        self.mergedLogs: List[Commit] = []
        self._exitCode = 0

        self.finished.connect(self._runFinished)

    def setSubmodules(self, submodules):
        self._errors = {}
        self._submodules = submodules

    def isLoading(self):
        return self._eventLoop is not None

    def fetch(self, *args):
        self._errorData = b''
        self._logs.clear()
        self._args = args

        self.start()

    def run(self):
        self._eventLoop = QEventLoop()
        submodules = self._submodules.copy()
        self.mergedLogs.clear()

        if not submodules:
            fetcher = LogsFetcherImpl()
            fetcher.logsAvailable.connect(
                self.logsAvailable)
            fetcher.fetchFinished.connect(self._onFetchFinished)
            self._fetchers = [fetcher]
            self._needComposite = False
        else:
            self._fetchers = []
            self._needComposite = True
            for submodule in submodules:
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

        if not self._needComposite:
            return

        for _, logs in self._logs.items():
            for log in logs:
                if self.isInterruptionRequested():
                    return
                if self.mergeLog(log):
                    continue
                logDate = makeDateTime(log.committerDate)
                if len(self.mergedLogs) == 0 or logDate < makeDateTime(self.mergedLogs[-1].committerDate):
                    self.mergedLogs.append(log)
                elif logDate > makeDateTime(self.mergedLogs[0].committerDate):
                    self.mergedLogs.insert(0, log)
                else:
                    insort_logs(self.mergedLogs, log)

    def mergeLog(self, target: Commit):
        for log in self.mergedLogs:
            targetDate = makeDateTime(target.committerDate)
            logDate = makeDateTime(log.committerDate)
            # since mergedLogs is sorted by committerDate, we can break here
            if targetDate.year > logDate.year or targetDate.month > logDate.month or targetDate.day > logDate.day:
                return False

            if log.repoDir == target.repoDir:
                continue
            if target.author == log.author and target.comments == log.comments:
                log.subCommits.append(target)
                # require same day at least
                return targetDate.year == logDate.year and \
                    targetDate.month == logDate.month and \
                    targetDate.day == logDate.day
        return False

    def cancel(self):
        self.requestInterruption()
        if self._eventLoop:
            self._eventLoop.quit()
        for fetcher in self._fetchers:
            fetcher.cancel()

    @property
    def errorData(self):
        return self._errorData

    def _onFetchFinished(self, exitCode):
        sender: LogsFetcherImpl = self.sender()
        if sender.errorData and sender.errorData not in self._errors:
            if not self._needComposite or not self._isIgnoredError(sender.errorData, sender._branch):
                self._errors[sender.errorData] = sender.repoDir

        self._fetchers.remove(sender)
        if not self._fetchers:
            if self._eventLoop:
                self._eventLoop.quit()
            for error, repo in self._errors.items():
                self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')

            if not self._needComposite:
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
        msg = b"fatal: ambiguous argument '%s': unknown revision or path" % branch
        return error.startswith(msg)

    def _runFinished(self):
        if self.mergedLogs:
            self.logsAvailable.emit(self.mergedLogs)
        self.fetchFinished.emit(self._exitCode)
