# -*- coding: utf-8 -*-

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List

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


def _fetchLocalChanges(branchDir: str, submodule: str, gitBin: str):
    try:
        GitProcess.GIT_BIN = gitBin
        repoPath = fullRepoDir(submodule, branchDir)
        hasLCC = Git.hasLocalChanges(True, repoPath)
        hasLUC = Git.hasLocalChanges(repoDir=repoPath)
        return hasLCC, hasLUC
    except Exception:
        return False, False


def _fetchLogs(submodule: str, branchDir: str, args: List[str], gitBin: str, maxCompositeCommitsSince=0):
    try:
        GitProcess.GIT_BIN = gitBin
        gitArgs, branch = LogsFetcherImpl.makeGitArgs(
            args, submodule, maxCompositeCommitsSince)

        repoDir = fullRepoDir(submodule, branchDir)
        process = Git.run(gitArgs, repoDir=repoDir)
        data, error = process.communicate()
        if process.returncode != 0:
            return [], process.returncode, error

        logs = LogsFetcherImpl.parseLogs(data, repoDir=submodule)

        return logs, process.returncode, error
    except Exception as e:
        return [], 1, str(e).encode("utf-8")


class LogsFetcherMPWorker(LogsFetcherWorkerBase):

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

        # fetch logs first
        span.addEvent("begin_fetch_logs")
        if not self._doFetchCompositeLogs(executor, submodules):
            logger.debug("Fetch logs cancelled")
            span.setStatus(False, "cancelled")
            span.end()
            return
        span.addEvent("end_fetch_logs")

        # now local changes
        if self.needLocalChanges():
            span.addEvent("begin_fetch_local_changes")
            if not self._doFetchLocalChanges(executor, submodules):
                logger.debug("Fetch local changes cancelled")
                span.setStatus(False, "cancelled")
                span.end()
                return
            span.addEvent("end_fetch_local_changes")

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
        for submodule in submodules:
            task = executor.submit(
                _fetchLogs, submodule, self._branchDir, self._args, GitProcess.GIT_BIN, days)
            tasks.append(task)
            taskSubmodules[task] = submodule

        while tasks and not self.isInterruptionRequested():
            try:
                for task in as_completed(tasks, 0.01):
                    if self.isInterruptionRequested():
                        return False
                    tasks.remove(task)
                    commits, exitCode, errorData = task.result()
                    submodule = taskSubmodules[task]
                    self._handleCompositeLogs(
                        commits, submodule, exitCode, errorData)
            except Exception:
                pass

        if self.isInterruptionRequested():
            return False

        self._emitCompositeLogsAvailable()

        return True

    def _doFetchLocalChanges(self, executor: ProcessPoolExecutor, submodules: List[str]):
        tasks = []
        taskSubmodules = {}

        for submodule in submodules:
            task = executor.submit(
                _fetchLocalChanges, self._branchDir, submodule, GitProcess.GIT_BIN)
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
                    hasLCC, hasLUC = task.result()
                    self._makeLocalCommits(
                        lccCommit, lucCommit, hasLCC, hasLUC, taskSubmodules[task])
            except Exception:
                pass

        if self.isInterruptionRequested():
            return False

        self.localChangesAvailable.emit(lccCommit, lucCommit)

        return True
