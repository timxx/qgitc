# -*- coding: utf-8 -*-

from datetime import date, datetime, timedelta
import os
from typing import List
from PySide6.QtCore import (
    Signal,
    QThread
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

    def parse(self, data):
        logs = data.rstrip(self.separator) \
            .decode("utf-8", "replace") \
            .split('\0')

        commits = []
        for log in logs:
            commit = Commit.fromRawString(log)
            commit.repoDir = self.repoDir
            commits.append(commit)

        self.logsAvailable.emit(commits)

    def makeArgs(self, args):
        branch = args[0]
        logArgs = args[1]

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


# the builtin bisect key required python >= 3.10
def insort_logs(a: List[Commit], x: Commit):
    lo = 0
    hi = len(a)

    xDate = datetime.fromisoformat(x.committerDate)
    while lo < hi:
        mid = (lo + hi) // 2
        t = datetime.fromisoformat(a[mid].committerDate)
        if xDate < t:
            lo = mid + 1
        else:
            hi = mid
    a.insert(lo, x)


class CompositeLogsThread(QThread):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logs = {}
        self.mergedLogs: List[Commit] = []

    def setLogs(self, logs):
        self.logs = logs
        self.mergedLogs.clear()

    def run(self):
        for _, logs in self.logs.items():
            for log in logs:
                if self.mergeLog(log):
                    continue
                logDate = datetime.fromisoformat(log.committerDate)
                if len(self.mergedLogs) == 0 or logDate < datetime.fromisoformat(self.mergedLogs[-1].committerDate):
                    self.mergedLogs.append(log)
                elif logDate > datetime.fromisoformat(self.mergedLogs[0].committerDate):
                    self.mergedLogs.insert(0, log)
                else:
                    insort_logs(self.mergedLogs, log)

    def mergeLog(self, target: Commit):
        for log in self.mergedLogs:
            targetDate = datetime.fromisoformat(target.committerDate)
            logDate = datetime.fromisoformat(log.committerDate)
            # since mergedLogs is sorted by committerDate, we can break here
            if targetDate.year > logDate.year or targetDate.month > logDate.month or targetDate.day > logDate.day:
                return False

            if log.repoDir == target.repoDir:
                continue
            if target.author == log.author and target.comments == log.comments:
                log.subCommits[target.repoDir] = target.sha1
                # require same day at least
                return targetDate.year == logDate.year and \
                    targetDate.month == logDate.month and \
                    targetDate.day == logDate.day
        return False


class LogsFetcher(DataFetcher):

    logsAvailable = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._errors = {}  # error: repo
        self._errorData = b''
        self._fetchers = []
        self._logs = {}  # repo: logs
        self._mergeThread = None
        self._needComposite = False

    def setSubmodules(self, submodules):
        self._errors = {}
        if not submodules:
            fetcher = LogsFetcherImpl()
            fetcher.logsAvailable.connect(self.logsAvailable)
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

    def isLoading(self):
        return len(self._fetchers) > 0

    def fetch(self, *args):
        self._errorData = b''
        self._logs.clear()

        if self._mergeThread and self._mergeThread.isRunning():
            self._mergeThread.requestInterruption()

        for fetcher in self._fetchers:
            fetcher.fetch(*args)

    def cancel(self):
        for fetcher in self._fetchers:
            fetcher.cancel()

        if self._mergeThread and self._mergeThread.isRunning():
            self._mergeThread.requestInterruption()

    @property
    def errorData(self):
        return self._errorData

    def _onFetchFinished(self, exitCode):
        sender: LogsFetcherImpl = self.sender()
        if sender.errorData and sender.errorData not in self._errors:
            self._errors[sender.errorData] = sender.repoDir

        self._fetchers.remove(sender)
        if not self._fetchers:
            for error, repo in self._errors.items():
                self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')

            if self._logs:
                if self._mergeThread is None:
                    self._mergeThread = CompositeLogsThread()
                    self._mergeThread.finished.connect(self._onMergeFinished)

                if self._needComposite:
                    if self._mergeThread.isRunning():
                        self._mergeThread.requestInterruption()
                    self._mergeThread.setLogs(self._logs)
                    self._mergeThread.start()
                else:
                    self.logsAvailable.emit(list(self._logs.keys()))

            self.fetchFinished.emit(exitCode)

    def _onLogsAvailable(self, logs):
        repoDir = self.sender().repoDir
        if repoDir in self._logs:
            self._logs[repoDir].extend(logs)
        else:
            self._logs[repoDir] = logs

    def _onMergeFinished(self):
        self.logsAvailable.emit(self._mergeThread.mergedLogs)
