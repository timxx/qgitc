# -*- coding: utf-8 -*-

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from sys import version_info
from typing import List

from PySide6.QtCore import SIGNAL, QEventLoop, QObject, QThread, Signal

from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.common import (
    Commit,
    MyLineProfile,
    MyProfile,
    extractFilePaths,
    filterSubmoduleByPath,
    isRevisionRange,
    logger,
    toSubmodulePath,
)
from qgitc.datafetcher import DataFetcher
from qgitc.gitutils import Git

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


class LogsFetcherThread(QThread):

    localChangesAvailable = Signal(Commit, Commit)
    logsAvailable = Signal(list)
    fetchFinished = Signal(int)

    def __init__(self, submodules, branchDir, parent=None):
        super().__init__(parent)
        self._errors = {}  # error: repo
        self._errorData = b''
        self._fetchers = []
        self._submodules = submodules.copy()
        self._eventLoop = None
        self._branchDir = branchDir

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

    @staticmethod
    def _fetchLocalChanges(branchDir: str, submodule: str = None):
        if not branchDir:
            return False, False

        repoPath = branchDir
        if submodule and submodule != '.':
            repoPath = os.path.join(branchDir, submodule)

        hasLCC = Git.hasLocalChanges(True, repoPath)
        hasLUC = Git.hasLocalChanges(repoDir=repoPath)

        return hasLCC, hasLUC

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

    def _fetchNormal(self):
        self._eventLoop = QEventLoop()

        if not self._args[1]:
            hasLCC, hasLUC = self._fetchLocalChanges(self._branchDir)
            if hasLCC or hasLUC:
                lccCommit = Commit()
                lucCommit = Commit()
                self._makeLocalCommits(lccCommit, lucCommit, hasLCC, hasLUC)
                self.localChangesAvailable.emit(lccCommit, lucCommit)

        fetcher = LogsFetcherImpl()
        fetcher.logsAvailable.connect(
            self.logsAvailable)
        fetcher.fetchFinished.connect(self._eventLoop.quit)
        self._fetchers.append(fetcher)

        fetcher.fetch(*self._args)
        self._eventLoop.exec()
        self._eventLoop = None

        # the fetcher may still be running
        # we have to cancel to avoid crash
        fetcher.cancel()

        self._handleError(fetcher.errorData, fetcher._branch, fetcher.repoDir)

        self._fetchers.remove(fetcher)
        for error, _ in self._errors.items():
            self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')

        self.fetchFinished.emit(fetcher._exitCode)

    def _fetchComposite(self):
        def _fetch(submodule: str, repoDir: str, cancelEvent: CancelEvent):
            if cancelEvent.isSet():
                return

            fetcher = LogsFetcherImpl(submodule)
            if submodule != '.':
                fetcher.cwd = os.path.join(repoDir, submodule)
            fetcher.fetch(*self._args)

            if cancelEvent.isSet():
                fetcher.cancel()
                return

            if not self._args[1]:
                hasLCC, hasLUC = self._fetchLocalChanges(
                    self._branchDir, submodule)
            else:
                hasLCC, hasLUC = False, False

            if cancelEvent.isSet():
                fetcher.cancel()
                return

            fetcher._process.waitForFinished()
            return fetcher._exitCode, fetcher._errorData, \
                fetcher._branch, fetcher.repoDir, fetcher.commits, \
                hasLCC, hasLUC

        b = time.time()

        logsArgs = self._args[1]
        paths = extractFilePaths(logsArgs)
        submodules = filterSubmoduleByPath(self._submodules, paths)

        max_workers = max(2, os.cpu_count() - 2)
        executor = ThreadPoolExecutor(max_workers=max_workers)
        cancelEvent = CancelEvent(self)
        tasks = [executor.submit(_fetch, submodule, Git.REPO_DIR, cancelEvent)
                 for submodule in submodules]

        mergedLogs = {}
        handleCount = 0
        exitCode = 0

        def _isSameRepoCommit(commit: Commit, repoDir: str):
            if commit.repoDir == repoDir:
                return True
            for commit in commit.subCommits:
                if commit.repoDir == repoDir:
                    return True
            return False

        lccCommit = Commit()
        lucCommit = Commit()

        while tasks and not self.isInterruptionRequested():
            try:
                for task in as_completed(tasks, 0.01):
                    if self.isInterruptionRequested():
                        logger.debug("Logs fetcher cancelled")
                        executor.shutdown(wait=False, cancel_futures=True)
                        return

                    tasks.remove(task)
                    code, errorData, branch, repoDir, logs, hasLCC, hasLUC = task.result()
                    self._makeLocalCommits(
                        lccCommit, lucCommit, hasLCC, hasLUC, repoDir)

                    for log in logs:
                        handleCount += 1
                        if handleCount % 100 == 0 and self.isInterruptionRequested():
                            logger.debug("Logs fetcher cancelled")
                            executor.shutdown(wait=False, cancel_futures=True)
                            return
                        # require same day at least
                        key = (log.committerDateTime.date(),
                               log.comments, log.author)
                        if key in mergedLogs.keys():
                            main_commit = mergedLogs[key]
                            # don't merge commits in same repo
                            if _isSameRepoCommit(main_commit, repoDir):
                                mergedLogs[log.sha1] = log
                            else:
                                main_commit.subCommits.append(log)
                        else:
                            mergedLogs[key] = log

                    exitCode |= code
                    self._handleError(errorData, branch, repoDir)
            except Exception:
                pass

        if self.isInterruptionRequested():
            logger.debug("Logs fetcher cancelled")
            executor.shutdown(wait=False, cancel_futures=True)
            return

        logger.debug("fetch elapsed: %fs", time.time() - b)
        b = time.time()

        self.localChangesAvailable.emit(lccCommit, lucCommit)

        if mergedLogs:
            sortedLogs = sorted(mergedLogs.values(),
                                key=lambda x: x.committerDateTime, reverse=True)
            self.logsAvailable.emit(sortedLogs)

        logger.debug("sort elapsed: %fms", (time.time() - b) * 1000)
        for error, _ in self._errors.items():
            self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')
        self.fetchFinished.emit(exitCode)

    def cancel(self):
        self.requestInterruption()
        if self._eventLoop:
            self._eventLoop.quit()

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
        self._thread = None
        self._submodules = []
        self._errorData = b''
        self._threads: List[QThread] = []

    def setSubmodules(self, submodules):
        self._submodules = submodules

    def fetch(self, *args, branchDir=None):
        self.cancel()
        self._errorData = b''
        self._thread = LogsFetcherThread(self._submodules, branchDir, self)
        self._thread.logsAvailable.connect(self._onLogsAvailable)
        self._thread.fetchFinished.connect(self._onFetchFinished)
        self._thread.localChangesAvailable.connect(self._onLocalChangesAvailable)
        self._thread.finished.connect(self._onThreadFinished)
        self._threads.append(self._thread)
        self._thread.fetch(*args)

    def cancel(self, force=False):
        if self._thread:
            self._thread.logsAvailable.disconnect(self._onLogsAvailable)
            self._thread.fetchFinished.disconnect(self._onFetchFinished)
            self._thread.localChangesAvailable.disconnect(
                self._onLocalChangesAvailable)
            self._thread.cancel()
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
        thread = self.sender()
        if thread == self._thread:
            self.logsAvailable.emit(logs)
        else:
            logger.info("_onLogsAvailable but thread changed")

    def _onFetchFinished(self, exitCode):
        thread = self.sender()
        if not thread:
            return

        if thread == self._thread:
            self._errorData = self._thread.errorData
            self._thread = None
            self.fetchFinished.emit(exitCode)
        else:
            logger.info("_onFetchFinished but thread changed")

    def _onLocalChangesAvailable(self, lccCommit: Commit, lucCommit: Commit):
        thread = self.sender()
        if thread == self._thread:
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
