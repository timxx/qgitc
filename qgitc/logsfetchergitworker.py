# -*- coding: utf-8 -*-

import argparse
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import List

import pygit2

from qgitc.applicationbase import ApplicationBase
from qgitc.common import (
    Commit,
    extractFilePaths,
    filterSubmoduleByPath,
    fullRepoDir,
    logger,
)
from qgitc.gitutils import Git
from qgitc.logsfetcherworkerbase import LogsFetcherWorkerBase

_COMMITTED_FLAGS = (pygit2.GIT_STATUS_INDEX_NEW |
                    pygit2.GIT_STATUS_INDEX_MODIFIED |
                    pygit2.GIT_STATUS_INDEX_DELETED |
                    pygit2.GIT_STATUS_INDEX_RENAMED |
                    pygit2.GIT_STATUS_INDEX_TYPECHANGE)

_UNCOMMITTED_FLAGS = (pygit2.GIT_STATUS_WT_MODIFIED |
                      pygit2.GIT_STATUS_WT_DELETED |
                      pygit2.GIT_STATUS_WT_RENAMED |
                      pygit2.GIT_STATUS_WT_TYPECHANGE)


def _fromRawCommit(rawCommit: pygit2.Commit):
    """ Convert from pygit2's commit """
    commit = Commit()

    authorDt = datetime.fromtimestamp(float(rawCommit.author.time))
    authorDateStr = "%d-%02d-%02d %02d:%02d:%02d" % (
        authorDt.year, authorDt.month, authorDt.day,
        authorDt.hour, authorDt.minute, authorDt.second)

    commit.sha1 = str(rawCommit.id)
    commit.comments = rawCommit.message.rstrip()
    commit.author = f"{rawCommit.author.name} <{rawCommit.author.email}>"
    commit.authorDate = authorDateStr
    commit.committer = f"{rawCommit.committer.name} <{rawCommit.committer.email}>"

    if rawCommit.committer.time == rawCommit.author.time:
        commit.committerDate = authorDateStr
    else:
        committerDt = datetime.fromtimestamp(float(rawCommit.committer.time))
        commit.committerDate = "%d-%02d-%02d %02d:%02d:%02d" % (
            committerDt.year, committerDt.month, committerDt.day,
            committerDt.hour, committerDt.minute, committerDt.second)

    commit.parents = [str(id) for id in rawCommit.parent_ids]

    return commit


class LogFilter:
    def __init__(self, since=None):
        self.author = None
        self.since = since
        self.max_count = None

    def setupFilters(self, args: List[str]):
        if not args:
            return

        parser = LogsFetcherGitWorker.argParser()
        try:
            parsedArgs, _ = parser.parse_known_args(args)
        except Exception as e:
            raise ValueError(f"Invalid arguments: {e}")

        if parsedArgs.author:
            self.author = parsedArgs.author.lower()
        if parsedArgs.since:
            self.since = self._parse_date(parsedArgs.since).timestamp()
        if parsedArgs.max_count:
            self.max_count = parsedArgs.max_count

    def _parse_date(self, dateStr: str):
        formats = [
            '%Y-%m-%d',         # 2025-01-01
            '%Y-%m-%d %H:%M',   # 2025-01-01 12:00
            '%Y/%m/%d',         # 2025/01/01
            '%Y',               # 2025
            '%d %b %Y',         # 01 Jan 2025
        ]

        for fmt in formats:
            try:
                return datetime.strptime(dateStr, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            if re.match(r'^\d+ +(day|week|month|year)s? +ago$', dateStr):
                return self._parse_relative_date(dateStr)
            raise ValueError(f"Unsupported date format: {dateStr}")
        except Exception as e:
            raise ValueError(f"Invalid date format: {dateStr} - {str(e)}")

    def _parse_relative_date(self, dateStr: str):
        parts = dateStr.split(' ')
        if len(parts) != 3:
            raise ValueError(f"Invalid relative date: {dateStr}")

        quantity = int(parts[0])
        unit = parts[1].rstrip('s')
        now = datetime.now(timezone.utc)

        if unit == 'day':
            delta = timedelta(days=quantity)
        elif unit == 'week':
            delta = timedelta(weeks=quantity)
        elif unit == 'month':
            delta = timedelta(days=quantity*30)
        elif unit == 'year':
            delta = timedelta(days=quantity*365)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        return now - delta

    def isFiltered(self, commit: pygit2.Commit) -> bool:
        if self.author is not None:
            author = commit.author.name.lower()
            if self.author not in author:
                return True

        return False

    def isStop(self, commit: pygit2.Commit) -> bool:
        if self.since is not None and commit.commit_time < self.since:
            return True

        if self.max_count is not None:
            self.max_count -= 1
            if self.max_count < 0:
                return True

        return False


def _fetchLogs(submodule: str, branchDir: str, args: List[str], since: float = None, checkLocalChanges=False):
    repoDir = fullRepoDir(submodule, branchDir)
    try:
        repo = pygit2.Repository(repoDir)
    except Exception as e:
        return submodule, [], False, False, str(e).encode("utf-8")

    logs = []

    branch = args[0]
    if branch.startswith("remotes/"):
        branch = branch[8:]
    gitBranch = repo.branches.get(branch)
    if gitBranch is None:
        return submodule, logs, False, False, \
            b"fatal: ambiguous argument '%s': unknown revision or path" % args[0].encode(
                "utf-8")

    filter = LogFilter(since)
    try:
        filter.setupFilters(args[1])
    except ValueError as e:
        return submodule, logs, False, False, str(e).encode("utf-8")

    for log in repo.walk(gitBranch.target, pygit2.GIT_SORT_TIME | pygit2.GIT_SORT_TOPOLOGICAL):
        if filter.isStop(log):
            break

        if filter.isFiltered(log):
            continue

        commit = _fromRawCommit(log)
        commit.repoDir = submodule
        commit.committerDateTime = datetime.fromtimestamp(log.commit_time)

        logs.append(commit)

    hasLCC = False
    hasLUC = False
    if checkLocalChanges:
        status = repo.status(untracked_files="no")
        for file, flags in status.items():
            if not hasLCC and (flags & _COMMITTED_FLAGS):
                hasLCC = True
                if hasLUC:
                    break
            if not hasLUC and (flags & _UNCOMMITTED_FLAGS):
                # Augly way to fix libgit2 bug with deleted files
                if flags == pygit2.GIT_STATUS_WT_DELETED and os.path.exists(os.path.join(repoDir, file)):
                    continue
                hasLUC = True
                if hasLCC:
                    break

    return submodule, logs, hasLCC, hasLUC, None


class LogsFetcherGitWorker(LogsFetcherWorkerBase):

    def __init__(self, submodules: List[str], branchDir: str, noLocalChanges: bool, *args):
        super().__init__(submodules, branchDir, noLocalChanges, *args)

    def run(self):
        self._fetchComposite()

    def _fetchComposite(self):
        telemetry = ApplicationBase.instance().telemetry()
        span = telemetry.startTrace("fetchCompositeGit2")
        span.addTag("sm_count", len(self._submodules))

        logsArgs = self._args[1]
        paths = extractFilePaths(logsArgs)
        submodules = filterSubmoduleByPath(self._submodules, paths)

        self._exitCode = 0
        self._mergedLogs.clear()

        max_workers = max(2, os.cpu_count())
        executor = ProcessPoolExecutor(max_workers=max_workers)
        done = self._doFetchLogs(executor, submodules or [None])

        if sys.version_info >= (3, 9):
            executor.shutdown(wait=False, cancel_futures=True)
        else:
            executor.shutdown(wait=True)

        if not done:
            logger.debug("Fetch logs cancelled")
            span.setStatus(False, "cancelled")
            span.end()
            return

        for error, _ in self._errors.items():
            self._errorData += error + b'\n'
            self._errorData.rstrip(b'\n')

        span.setStatus(True)
        span.end()

        self.fetchFinished.emit(self._exitCode)

    def _doFetchLogs(self, executor: ProcessPoolExecutor, submodules: List[str]):
        tasks = []
        taskSubmodules = {}

        checkLocalChanges = self.needLocalChanges()
        branch = self._args[0].encode("utf-8") if self._args[0] else None

        since = None
        if len(submodules) > 1:
            days = ApplicationBase.instance().settings().maxCompositeCommitsSince()
            if days > 0:
                since = (datetime.today() - timedelta(days)).timestamp()

        for submodule in submodules:
            task = executor.submit(
                _fetchLogs, submodule, self._branchDir or Git.REPO_DIR, self._args, since, checkLocalChanges)
            tasks.append(task)
            taskSubmodules[task] = submodule

        lccCommit = Commit()
        lucCommit = Commit()

        while tasks and not self.isInterruptionRequested():
            try:
                for task in as_completed(tasks, 0.01):
                    if self.isInterruptionRequested():
                        return False
                    tasks.remove(task)
                    submodule, commits, hasLCC, hasLUC, error = task.result()
                    exitCode = 1 if error else 0
                    self._handleCompositeLogs(
                        commits, submodule, branch, exitCode, error)
                    self._makeLocalCommits(
                        lccCommit, lucCommit, hasLCC, hasLUC, submodule)
            except Exception:
                pass

        if self.isInterruptionRequested():
            return False

        self.localChangesAvailable.emit(lccCommit, lucCommit)
        self._emitCompositeLogsAvailable()

        return True

    def needReportSlowFetch(self):
        return False

    @staticmethod
    def argParser():
        if sys.version_info >= (3, 9):
            parser = argparse.ArgumentParser(exit_on_error=False)
        else:
            parser = argparse.ArgumentParser()
        parser.add_argument('--author', type=str)
        parser.add_argument('--since', type=str)
        parser.add_argument('--max-count', type=int)
        return parser

    @staticmethod
    def isSupportFilterArgs(args: List[str]) -> bool:
        if not args:
            return True

        parser = LogsFetcherGitWorker.argParser()
        _, unknownArgs = parser.parse_known_args(args)
        if unknownArgs:
            app = ApplicationBase.instance()
            telemetry = app.telemetry() if app else None
            if telemetry:
                logger = telemetry.logger()
                logger.warning(
                    f"Unsupported log fetcher arguments: {unknownArgs}")
            return False
        return True
