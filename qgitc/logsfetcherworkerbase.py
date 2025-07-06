# -*- coding: utf-8 -*-

from git import Commit, List
from PySide6.QtCore import QObject, Signal


class LogsFetcherWorkerBase(QObject):

    localChangesAvailable = Signal(Commit, Commit)
    logsAvailable = Signal(list)
    fetchFinished = Signal(int)

    def __init__(self, submodules: List[str], branchDir: str, noLocalChanges: bool, *args):
        super().__init__()

        self._submodules = submodules.copy()
        self._branchDir = branchDir
        self._noLocalChanges = noLocalChanges
        self._args = args

        self._errorData = b''
        self._exitCode = 0

        self._interruptionRequested = False

    def run(self):
        """Override this method in subclasses to implement the fetching logic."""
        raise NotImplementedError("Subclasses must implement the run method.")

    def isInterruptionRequested(self):
        return self._interruptionRequested

    def requestInterruption(self):
        self._interruptionRequested = True

    def needLocalChanges(self):
        return not self._noLocalChanges and not self._args[1]

    @property
    def errorData(self):
        return self._errorData

    @staticmethod
    def _isSameRepoCommit(commit: Commit, repoDir: str):
        if commit.repoDir == repoDir:
            return True
        for commit in commit.subCommits:
            if commit.repoDir == repoDir:
                return True
        return False
