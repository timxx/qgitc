# -*- coding: utf-8 -*-

from typing import Dict, List, Set

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from qgitc.common import Commit
from qgitc.gitutils import Git


class LogsFetcherWorkerBase(QObject):

    localChangesAvailable = Signal(Commit, Commit)
    # object rather than list: PySide maps `list` to QVariantList, which boxes
    # every element into a QVariant on emit and unboxes it again on delivery.
    # For composite logs that is a per-emit cost proportional to the payload.
    logsAvailable = Signal(object)
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
        # repos already represented by each merged row, so merging stays O(1)
        # instead of rescanning subCommits
        self._mergedRepoDirs: Dict[any, Set[str]] = {}
        # rows added since the last emission; only these get sent downstream
        self._newLogs: List[Commit] = []

        self._compositeEmitTimer = QTimer(self)
        self._compositeEmitTimer.setSingleShot(True)
        self._compositeEmitTimer.timeout.connect(self._onCompositeEmitTimeout)
        self._pendingCompositeEmit = False
        self._awaitingConsumer = False

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
            repoDirs = self._mergedRepoDirs.get(key)
            if repoDirs is None:
                self._addMergedLog(key, log, repoDir)
            elif repoDir in repoDirs:
                # don't merge commits in same repo
                self._addMergedLog(log.sha1, log, repoDir)
            else:
                self._mergedLogs[key].subCommits.append(log)
                repoDirs.add(repoDir)

        self._exitCode |= exitCode
        self._handleError(errorData, branch, repoDir)

    def _addMergedLog(self, key, log: Commit, repoDir: str):
        if key in self._mergedLogs:
            return
        self._mergedLogs[key] = log
        self._mergedRepoDirs[key] = {repoDir}
        self._newLogs.append(log)

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
        """Emit the rows merged since the last emission, newest first."""
        if not self._newLogs:
            return
        batch = self._newLogs
        self._newLogs = []
        batch.sort(key=lambda x: x.committerDateTime, reverse=True)
        self._awaitingConsumer = True
        self.logsAvailable.emit(batch)

    def _scheduleCompositeEmit(self):
        """Schedule a batched incremental emission after _COMPOSITE_EMIT_INTERVAL_MS.

        Call this after each submodule's logs have been merged.  The emission is
        deferred so that fast completions are batched together, reducing UI churn.
        Nothing is queued while a previous batch is still unacknowledged, which
        keeps the consumer from falling behind and piling up events.
        """
        self._pendingCompositeEmit = True
        if self._awaitingConsumer:
            return
        if not self._compositeEmitTimer.isActive():
            self._compositeEmitTimer.start(self._COMPOSITE_EMIT_INTERVAL_MS)

    @Slot()
    def logsConsumed(self):
        """Acknowledgement from the consumer that the last batch was handled."""
        self._awaitingConsumer = False
        if self._pendingCompositeEmit and not self._compositeEmitTimer.isActive():
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
        self._awaitingConsumer = False
        self._mergedLogs.clear()
        self._mergedRepoDirs.clear()
        self._newLogs.clear()

    @property
    def errorData(self):
        return self._errorData

    @staticmethod
    def _makeLocalCommits(lccCommit: Commit, lucCommit: Commit, hasLCC, hasLUC, repoDir=None,
                          untrackedFiles=None):
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

        if untrackedFiles and lucCommit.isValid():
            if not lucCommit.untrackedFiles:
                lucCommit.untrackedFiles = []
            lucCommit.untrackedFiles.extend(untrackedFiles)
