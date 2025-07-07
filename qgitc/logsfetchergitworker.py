# -*- coding: utf-8 -*-

import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
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
from qgitc.logsfetcherworkerbase import LogsFetcherWorkerBase

_COMMITTED_FLAGS = (pygit2.GIT_STATUS_INDEX_NEW |
                    pygit2.GIT_STATUS_INDEX_MODIFIED |
                    pygit2.GIT_STATUS_INDEX_DELETED |
                    pygit2.GIT_STATUS_INDEX_RENAMED |
                    pygit2.GIT_STATUS_INDEX_TYPECHANGE)

_UNCOMMITTED_FLAGS = (pygit2.GIT_STATUS_WT_NEW |
                      pygit2.GIT_STATUS_WT_MODIFIED |
                      pygit2.GIT_STATUS_WT_DELETED |
                      pygit2.GIT_STATUS_WT_RENAMED |
                      pygit2.GIT_STATUS_WT_TYPECHANGE |
                      pygit2.GIT_STATUS_WT_UNREADABLE)


def _fromRawCommit(rawCommit: pygit2.Commit):
    """ Convert from pygit2's commit """
    commit = Commit()

    def timeStr(signature: pygit2.Signature):
        dt = datetime.fromtimestamp(float(signature.time))
        return "%d-%02d-%02d %02d:%02d:%02d" % (
            dt.year, dt.month, dt.day,
            dt.hour, dt.minute, dt.second)

    def authorStr(author: pygit2.Signature):
        return author.name + " <" + author.email + ">"

    commit.sha1 = str(rawCommit.id)
    commit.comments = rawCommit.message.rstrip()
    commit.author = authorStr(rawCommit.author)
    commit.authorDate = timeStr(rawCommit.author)
    commit.committer = authorStr(rawCommit.committer)
    if rawCommit.committer.time == rawCommit.author.time:
        commit.committerDate = commit.authorDate
    else:
        commit.committerDate = timeStr(rawCommit.committer)
    commit.parents = []
    for id in rawCommit.parent_ids:
        commit.parents.append(str(id))

    return commit


# TODO: args and maxCompositeCommitsSince
def _fetchLogs(submodule: str, branchDir: str, args: List[str], maxCompositeCommitsSince=0, checkLocalChanges=False):
    repoDir = fullRepoDir(submodule, branchDir)
    repo = pygit2.Repository(repoDir)
    logs = []

    for log in repo.walk(repo.head.target, pygit2.GIT_SORT_TOPOLOGICAL):
        commit = _fromRawCommit(log)
        commit.repoDir = submodule
        isoDate = ''
        if sys.version_info < (3, 11):
            isoDate = commit.committerDate.replace(
                ' ', 'T', 1).replace(' ', '', 1)
            isoDate = isoDate[:-2] + ':' + isoDate[-2:]
        else:
            isoDate = commit.committerDate
        commit.committerDateTime = datetime.fromisoformat(isoDate)
        logs.append(commit)

    hasLCC = False
    hasLUC = False
    if checkLocalChanges:
        status = repo.status(untracked_files="no")
        for _, flags in status.items():
            if flags & _COMMITTED_FLAGS:
                hasLCC = True
            if flags & _UNCOMMITTED_FLAGS:
                hasLUC = True
            if hasLCC and hasLUC:
                break

    return submodule, logs, hasLCC, hasLUC


class LogsFetcherGitWorker(LogsFetcherWorkerBase):

    def __init__(self, submodules: List[str], branchDir: str, noLocalChanges: bool, *args):
        super().__init__(submodules, branchDir, noLocalChanges, *args)

        # only for composite fetch
        assert len(submodules) > 0, "Submodules list cannot be empty"

    def run(self):
        self._fetchComposite()

    def _fetchComposite(self):
        telemetry = ApplicationBase.instance().telemetry()
        span = telemetry.startTrace("fetchCompositeMP")
        span.addTag("sm_count", len(self._submodules))

        logsArgs = self._args[1]
        paths = extractFilePaths(logsArgs)
        submodules = filterSubmoduleByPath(self._submodules, paths)

        self._exitCode = 0
        self._mergedLogs.clear()

        max_workers = max(2, os.cpu_count())
        executor = ProcessPoolExecutor(max_workers=max_workers)

        if not self._doFetchCompositeLogs(executor, submodules):
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

    def _doFetchCompositeLogs(self, executor: ProcessPoolExecutor, submodules: List[str]):
        tasks = []
        taskSubmodules = {}

        days = ApplicationBase.instance().settings().maxCompositeCommitsSince()
        checkLocalChanges = self.needLocalChanges()
        branch = self._args[0].encode("utf-8") if self._args[0] else None

        for submodule in submodules:
            task = executor.submit(
                _fetchLogs, submodule, self._branchDir, self._args, days, checkLocalChanges)
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
                    submodule, commits, hasLCC, hasLUC = task.result()
                    self._handleCompositeLogs(
                        commits, submodule, branch, 0, b'')
                    self._makeLocalCommits(
                        lccCommit, lucCommit, hasLCC, hasLUC, submodule)
            except Exception:
                pass

        if self.isInterruptionRequested():
            return False

        self.localChangesAvailable.emit(lccCommit, lucCommit)
        self._emitCompositeLogsAvailable()

        return True
