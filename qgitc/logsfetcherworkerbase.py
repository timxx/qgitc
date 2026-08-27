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
        # Full sorted list of all merged commits, maintained in the worker
        # thread so the main thread never has to merge.
        self._allLogs: List[Commit] = []
        # Commits with future dates (e.g. clock skew) are kept separate and
        # appended to the end of _allLogs after each emission.
        self._futureLogs: List[Commit] = []

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
        from datetime import datetime as _dt
        now = _dt.now().timestamp()
        handleCount = 0

        for log in commits:
            handleCount += 1
            if handleCount % 100 == 0 and self.isInterruptionRequested():
                return
            # Future-dated commits (e.g. clock skew, 2050) are set aside
            # and appended to the end of the list later.
            if log.committerDateTime.timestamp() > now:
                self._futureLogs.append(log)
                continue
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
        """Emit the rows merged since the last emission, newest first.

        Performs the merge into _allLogs in the worker thread so the main
        thread only needs to swap in the new list and remap indices.
        """
        if not self._newLogs:
            return
        batch = self._newLogs
        self._newLogs = []
        batch.sort(key=lambda x: x.committerDateTime, reverse=True)

        insertPositions = self._mergeIntoAllLogs(batch)

        # Append future-dated commits at the end
        if self._futureLogs:
            oldCount = len(self._allLogs)
            for c in self._futureLogs:
                insertPositions.append(oldCount)
                self._allLogs.append(c)
                oldCount += 1
            self._futureLogs.clear()

        self._awaitingConsumer = True
        self.logsAvailable.emit((self._allLogs, insertPositions))

    def _mergeIntoAllLogs(self, batch: List[Commit]):
        """Merge a newest-first batch into _allLogs (two-pointer, O(n+m)).

        Returns insert positions (indices into the old list) for remapping.
        """
        old = self._allLogs
        oldCount = len(old)
        insertPositions = []
        merged = []
        i = 0   # index into old
        j = 0   # index into batch
        newCount = len(batch)
        runStart = i
        while i < oldCount and j < newCount:
            if batch[j].committerDateTime > old[i].committerDateTime:
                if i > runStart:
                    merged.extend(old[runStart:i])
                insertPositions.append(i)
                merged.append(batch[j])
                j += 1
                runStart = i
            else:
                i += 1
        if i > runStart:
            merged.extend(old[runStart:i])
        while j < newCount:
            insertPositions.append(i)
            merged.append(batch[j])
            j += 1
        if i < oldCount:
            merged.extend(old[i:])

        self._allLogs = merged
        return insertPositions

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
        self._allLogs.clear()
        self._futureLogs.clear()

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

        # The subCommit (or lucCommit itself) that owns untrackedFiles for this repoDir.
        # Untracked files must be associated with their originating repoDir so that
        # _addUntrackedEntries can set the correct cwd when fetching their diff.
        untrackedOwner = None
        if hasLUC:
            lucCommit.sha1 = Git.LUC_SHA1
            if not lucCommit.repoDir:
                lucCommit.repoDir = repoDir
                untrackedOwner = lucCommit
            else:
                subCommit = Commit()
                subCommit.sha1 = Git.LUC_SHA1
                subCommit.repoDir = repoDir
                lucCommit.subCommits.append(subCommit)
                untrackedOwner = subCommit

        if untrackedFiles and untrackedOwner is not None:
            if not untrackedOwner.untrackedFiles:
                untrackedOwner.untrackedFiles = []
            untrackedOwner.untrackedFiles.extend(untrackedFiles)
