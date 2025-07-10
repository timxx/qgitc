# -*- coding: utf-8 -*-

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
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


# TODO: args
def _fetchLogs(submodule: str, branchDir: str, args: List[str], since: float = None, checkLocalChanges=False):
    repoDir = fullRepoDir(submodule, branchDir)
    repo = pygit2.Repository(repoDir)
    logs = []

    branch = args[0]
    if branch.startswith("remotes/"):
        branch = branch[8:]
    gitBranch = repo.branches.get(branch)
    if gitBranch is None:
        # TODO: errors
        return submodule, logs, False, False

    for log in repo.walk(gitBranch.target, pygit2.GIT_SORT_TIME | pygit2.GIT_SORT_TOPOLOGICAL):
        if since is not None and log.commit_time < since:
            break

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
                if flags == pygit2.GIT_STATUS_WT_DELETED and os.path.exits(os.path.join(repoDir, file)):
                    continue
                hasLUC = True
                if hasLCC:
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
        span = telemetry.startTrace("fetchCompositeGit2")
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
