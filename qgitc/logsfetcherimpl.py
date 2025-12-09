# -*- coding: utf-8 -*-

from datetime import date, datetime, timedelta
from sys import version_info
from typing import List

from PySide6.QtCore import Signal

from qgitc.applicationbase import ApplicationBase
from qgitc.common import (
    Commit,
    extractFilePaths,
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
        self.commits: List[Commit] = []

    def parse(self, data: bytes):
        commits = LogsFetcherImpl.parseLogs(data, self.separator, self.repoDir)
        if self.repoDir:
            self.commits.extend(commits)
        else:
            self.logsAvailable.emit(commits)

    def makeArgs(self, args):
        days = ApplicationBase.instance().settings().maxCompositeCommitsSince()
        gitArgs, self._branch = LogsFetcherImpl.makeGitArgs(
            args, self.repoDir, days, self._cwd)
        return gitArgs

    @staticmethod
    def parseLogs(data: bytes, separator: bytes = b'\0', repoDir=None):
        logs = data.rstrip(separator) \
            .decode("utf-8", "replace") \
            .split('\0')

        commits = []
        for log in logs:
            commit = Commit.fromRawString(log)
            if not commit or not commit.sha1:
                continue
            commit.repoDir = repoDir
            if repoDir:
                isoDate = ''
                if version_info < (3, 11):
                    isoDate = commit.committerDate.replace(
                        ' ', 'T', 1).replace(' ', '', 1)
                    isoDate = isoDate[:-2] + ':' + isoDate[-2:]
                else:
                    isoDate = commit.committerDate
                commit.committerDateTime = datetime.fromisoformat(isoDate)
            commits.append(commit)

        return commits

    @staticmethod
    def makeGitArgs(args, repoDir=None, maxCompositeCommitsSince=0, cwd=None):
        branch: str = args[0]
        logArgs: List[str] = args[1]
        _branch = branch.encode("utf-8") if branch else None

        hasRevisionRange = LogsFetcherImpl.hasRevisionRange(logArgs)
        hasNotValue = LogsFetcherImpl.hasNotArgValue(logArgs)

        if branch and (branch.startswith("(HEAD detached") or (hasRevisionRange and not hasNotValue)):
            branch = None

        git_args = ["log", "-z", "--topo-order",
                    "--parents",
                    "--no-color",
                    "--pretty=format:{0}".format(log_fmt)]

        needBoundary = True
        paths = None
        # reduce commits to analyze
        if repoDir and not LogsFetcherImpl.hasSinceArg(logArgs) and \
                not hasRevisionRange and not hasNotValue:
            paths = extractFilePaths(logArgs) if logArgs else None
            if not paths:
                if maxCompositeCommitsSince > 0:
                    since = date.today() - timedelta(days=maxCompositeCommitsSince)
                    git_args.append(f"--since={since.isoformat()}")
                    needBoundary = False

        if branch:
            git_args.append(branch)

        if logArgs:
            if repoDir and repoDir != ".":
                paths = paths or extractFilePaths(logArgs)
                if paths:
                    for arg in logArgs:
                        if arg not in paths and arg != "--":
                            git_args.append(arg)
                    git_args.append("--")
                    for path in paths:
                        git_args.append(toSubmodulePath(repoDir, path))
                else:
                    git_args.extend(logArgs)
            else:
                git_args.extend(logArgs)
        elif needBoundary:
            git_args.append("--boundary")

        return git_args, _branch

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

    @staticmethod
    def hasNotArgValue(args: List[str]):
        if not args:
            return False
        for i, arg in enumerate(args):
            if arg == "--not" and i + 1 < len(args):
                return True
        return False
