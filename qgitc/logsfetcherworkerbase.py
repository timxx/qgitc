# -*- coding: utf-8 -*-

from typing import Dict, List

from PySide6.QtCore import QObject, QTimer, Signal

from qgitc.common import Commit
from qgitc.gitutils import Git


class LogsFetcherWorkerBase(QObject):

    localChangesAvailable = Signal(Commit, Commit)
    logsAvailable = Signal(list)
    fetchFinished = Signal(int)

    _COMPOSITE_EMIT_INTERVAL_MS = 100

    def __init__(self, submodules: List[str], branchDir: str, noLocalChanges: bool, *args):
        super().__init__()

        self._submodules = submodules.copy() if submodules else []
        self._branchDir = branchDir
        self._noLocalChanges = noLocalChanges
        self._args = args

        self._errorData = b''
        self._exitCode = 0
        self._errors = {}  # error: repo

        self._interruptionRequested = False

        self._mergedLogs: Dict[any, Commit] = {}

        self._compositeEmitTimer = QTimer(self)
        self._compositeEmitTimer.setSingleShot(True)
        self._compositeEmitTimer.timeout.connect(self._onCompositeEmitTimeout)
        self._pendingCompositeEmit = False

    def run(self):
        """Override this method in subclasses to implement the fetching logic."""
        raise NotImplementedError("Subclasses must implement the run method.")

    def isInterruptionRequested(self):
        return self._interruptionRequested

    def requestInterruption(self):
        self._interruptionRequested = True

    def needLocalChanges(self):
        # only if branch checked out
        # and not disabled in settings
        # and no revision range
        return self._branchDir and \
            not self._noLocalChanges \
            and not self._args[1]

    def needReportSlowFetch(self):
        return self._submodules and self.needLocalChanges()

    def _handleCompositeLogs(self, commits: List[Commit], repoDir: str, branch: bytes,
                             exitCode: int, errorData: bytes):
        handleCount = 0

        for log in commits:
            handleCount += 1
            if handleCount % 100 == 0 and self.isInterruptionRequested():
                return
            # require same day at least
            key = (log.committerDateTime.date(),
                   log.comments, log.author)
            if key in self._mergedLogs.keys():
                main_commit: Commit = self._mergedLogs[key]
                # don't merge commits in same repo
                if LogsFetcherWorkerBase._isSameRepoCommit(main_commit, repoDir):
                    self._mergedLogs[log.sha1] = log
                else:
                    main_commit.subCommits.append(log)
            else:
                self._mergedLogs[key] = log

        self._exitCode |= exitCode
        self._handleError(errorData, branch, repoDir)

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

    def _emitCompositeLogsAvailable(self):
        if not self._mergedLogs:
            return
        sortedLogs = sorted(self._mergedLogs.values(),
                            key=lambda x: x.committerDateTime, reverse=True)
        self.logsAvailable.emit(sortedLogs)

    def _scheduleCompositeEmit(self):
        """Schedule a batched incremental emission after _COMPOSITE_EMIT_INTERVAL_MS.

        Call this after each submodule's logs have been merged.  The emission is
        deferred so that fast completions are batched together, reducing UI churn.
        """
        self._pendingCompositeEmit = True
        if not self._compositeEmitTimer.isActive():
            self._compositeEmitTimer.start(self._COMPOSITE_EMIT_INTERVAL_MS)

    def _onCompositeEmitTimeout(self):
        if not self._pendingCompositeEmit:
            return
        self._pendingCompositeEmit = False
        if self.isInterruptionRequested():
            return
        self._emitCompositeLogsAvailable()

    def _flushCompositeEmit(self):
        """Flush any pending batched emission immediately (used on fetch completion)."""
        self._compositeEmitTimer.stop()
        if not self._pendingCompositeEmit:
            return
        self._pendingCompositeEmit = False
        if self.isInterruptionRequested():
            return
        self._emitCompositeLogsAvailable()

    def _cleanupCompositeEmit(self):
        """Cancel pending emission and clear accumulated state."""
        self._compositeEmitTimer.stop()
        self._pendingCompositeEmit = False
        self._mergedLogs.clear()

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
