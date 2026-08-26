# -*- coding: utf-8 -*-
"""Unit tests for LogsFetcherWorkerBase composite-mode incremental-emission logic."""

from datetime import datetime, timedelta

from PySide6.QtTest import QSignalSpy

from qgitc.common import Commit
from qgitc.gitutils import Git
from qgitc.logsfetcherworkerbase import LogsFetcherWorkerBase
from tests.base import TestBase


class _TestWorker(LogsFetcherWorkerBase):
    """Minimal concrete worker so we can instantiate the base class."""

    def run(self):
        pass


class TestLogsFetcherWorkerBaseComposite(TestBase):
    """Tests focused on the incremental emission primitives."""

    def doCreateRepo(self):
        """No repo needed for these unit-level tests."""
        pass

    def setUp(self):
        super().setUp()
        self._worker = _TestWorker([], "", False)

    def tearDown(self):
        self._worker.deleteLater()
        self.processEvents()
        super().tearDown()

    def _makeCommit(self, sha1, dateTime, comments="msg", author="author", repoDir="repo"):
        commit = Commit()
        commit.sha1 = sha1
        commit.comments = comments
        commit.author = author
        commit.repoDir = repoDir
        commit.committerDateTime = dateTime
        commit.subCommits = []
        return commit

    def _merge(self, key, commit):
        """Record a commit the same way _handleCompositeLogs does."""
        self._worker._mergedLogs[key] = commit
        self._worker._newLogs.append(commit)

    # ------------------------------------------------------------------
    #  _scheduleCompositeEmit
    # ------------------------------------------------------------------
    def testScheduleCompositeEmit_startsTimer(self):
        self.assertFalse(self._worker._compositeEmitTimer.isActive())
        self.assertFalse(self._worker._pendingCompositeEmit)

        self._worker._scheduleCompositeEmit()
        self.assertTrue(self._worker._pendingCompositeEmit)
        self.assertTrue(self._worker._compositeEmitTimer.isActive())

    def testScheduleCompositeEmit_multipleCalls_oneTimer(self):
        spy = QSignalSpy(self._worker._compositeEmitTimer.timeout)
        self._worker._scheduleCompositeEmit()
        self._worker._scheduleCompositeEmit()
        self._worker._scheduleCompositeEmit()
        self.assertTrue(self._worker._pendingCompositeEmit)
        self.assertTrue(self._worker._compositeEmitTimer.isActive())
        # Only one emission expected when the timer fires.
        spy.wait(200)
        self.assertEqual(1, spy.count())

    def testScheduleCompositeEmit_emitsLogsOnTimeout(self):
        now = datetime.now()
        self._merge(("key",), self._makeCommit("a" * 40, now))

        captured = []
        self._worker.logsAvailable.connect(captured.append)
        self._worker._scheduleCompositeEmit()
        spy = QSignalSpy(self._worker.logsAvailable)
        spy.wait(200)

        self.assertEqual(1, len(captured))
        allLogs, insertPositions = captured[0]
        self.assertEqual(1, len(allLogs))

    # ------------------------------------------------------------------
    #  Incremental payload: only newly merged commits are emitted
    # ------------------------------------------------------------------
    def testEmitOnlyCarriesNewLogs(self):
        now = datetime.now()
        c1 = self._makeCommit("a" * 40, now)
        self._merge(("key1",), c1)

        captured = []
        self._worker.logsAvailable.connect(captured.append)

        self._worker._emitCompositeLogsAvailable()
        self.assertEqual(1, len(captured))
        allLogs, insertPositions = captured[0]
        self.assertEqual([c1], allLogs)

        self._worker.logsConsumed()
        c2 = self._makeCommit("b" * 40, now - timedelta(hours=1))
        self._merge(("key2",), c2)

        self._worker._emitCompositeLogsAvailable()
        self.assertEqual(2, len(captured))
        allLogs2, insertPositions2 = captured[1]
        self.assertIn(c2, allLogs2,
                      "second batch must carry the newly merged commit")

    def testEmitClearsNewLogsButKeepsMergedLogs(self):
        now = datetime.now()
        self._merge(("key1",), self._makeCommit("a" * 40, now))

        self._worker._emitCompositeLogsAvailable()
        self.assertEqual(1, len(self._worker._mergedLogs),
                         "_mergedLogs must survive _emitCompositeLogsAvailable")
        self.assertEqual(0, len(self._worker._newLogs),
                         "_newLogs must be drained by the emission")

    def testEmitNoNewLogs_noEmit(self):
        now = datetime.now()
        # _mergedLogs is non-empty but nothing is new since the last emit
        self._worker._mergedLogs[("key1",)] = self._makeCommit("a" * 40, now)

        spy = QSignalSpy(self._worker.logsAvailable)
        self._worker._emitCompositeLogsAvailable()
        self.assertEqual(0, spy.count())

    def testEmitPassesSameListObject(self):
        """logsAvailable uses Signal(object) so the payload must not be copied."""
        now = datetime.now()
        self._merge(("key1",), self._makeCommit("a" * 40, now))

        captured = []
        self._worker.logsAvailable.connect(captured.append)
        self._worker._emitCompositeLogsAvailable()

        self.assertEqual(1, len(captured))
        allLogs, insertPositions = captured[0]
        self.assertIsInstance(allLogs, list)
        self.assertIs(allLogs, self._worker._allLogs,
                     "the allLogs list must be the worker's own list object")

    def testEmitSortsBatchDescendingByCommitterDateTime(self):
        now = datetime.now()
        c1 = self._makeCommit("a" * 40, now)
        c2 = self._makeCommit("b" * 40, now - timedelta(hours=2))
        c3 = self._makeCommit("c" * 40, now - timedelta(hours=1))

        self._merge(("k1",), c1)
        self._merge(("k2",), c2)
        self._merge(("k3",), c3)

        captured = []
        self._worker.logsAvailable.connect(captured.append)
        self._worker._emitCompositeLogsAvailable()

        self.assertEqual(1, len(captured))
        allLogs, insertPositions = captured[0]
        self.assertEqual([c1, c3, c2], allLogs,
                         "batch sorted newest-first by committerDateTime")

    # ------------------------------------------------------------------
    #  Backpressure handshake
    # ------------------------------------------------------------------
    def testEmitMarksAwaitingConsumer(self):
        now = datetime.now()
        self._merge(("key1",), self._makeCommit("a" * 40, now))

        self.assertFalse(self._worker._awaitingConsumer)
        self._worker._emitCompositeLogsAvailable()
        self.assertTrue(self._worker._awaitingConsumer)

    def testScheduleDoesNotArmTimerWhileAwaitingConsumer(self):
        now = datetime.now()
        self._merge(("key1",), self._makeCommit("a" * 40, now))
        self._worker._emitCompositeLogsAvailable()
        self.assertTrue(self._worker._awaitingConsumer)

        self._merge(("key2",), self._makeCommit(
            "b" * 40, now - timedelta(hours=1)))
        self._worker._scheduleCompositeEmit()

        self.assertTrue(self._worker._pendingCompositeEmit)
        self.assertFalse(self._worker._compositeEmitTimer.isActive(),
                         "must not queue more batches until the consumer acks")

    def testLogsConsumedReleasesBackpressure(self):
        now = datetime.now()
        self._merge(("key1",), self._makeCommit("a" * 40, now))
        self._worker._emitCompositeLogsAvailable()

        self._merge(("key2",), self._makeCommit(
            "b" * 40, now - timedelta(hours=1)))
        self._worker._scheduleCompositeEmit()
        self.assertFalse(self._worker._compositeEmitTimer.isActive())

        self._worker.logsConsumed()
        self.assertFalse(self._worker._awaitingConsumer)
        self.assertTrue(self._worker._compositeEmitTimer.isActive(),
                        "ack must re-arm the timer when a batch is pending")

    def testLogsConsumedWithoutPending_doesNotArmTimer(self):
        self._worker._awaitingConsumer = True
        self._worker.logsConsumed()
        self.assertFalse(self._worker._awaitingConsumer)
        self.assertFalse(self._worker._compositeEmitTimer.isActive())

    def testFlushIgnoresBackpressure(self):
        now = datetime.now()
        self._merge(("key1",), self._makeCommit("a" * 40, now))
        self._worker._emitCompositeLogsAvailable()
        self.assertTrue(self._worker._awaitingConsumer)

        self._merge(("key2",), self._makeCommit(
            "b" * 40, now - timedelta(hours=1)))
        self._worker._pendingCompositeEmit = True

        spy = QSignalSpy(self._worker.logsAvailable)
        self._worker._flushCompositeEmit()
        self.assertEqual(1, spy.count(),
                         "final flush must deliver even while awaiting an ack")

    # ------------------------------------------------------------------
    #  Interruption guards
    # ------------------------------------------------------------------
    def testScheduleEmit_skipsWhenInterrupted(self):
        now = datetime.now()
        self._merge(("key1",), self._makeCommit("a" * 40, now))

        spy = QSignalSpy(self._worker.logsAvailable)
        self._worker._scheduleCompositeEmit()
        self._worker._interruptionRequested = True
        spy.wait(200)
        self.assertEqual(0, spy.count(),
                         "interruption must suppress timer emission")

    def testFlushEmit_skipsWhenInterrupted(self):
        now = datetime.now()
        self._merge(("key1",), self._makeCommit("a" * 40, now))

        spy = QSignalSpy(self._worker.logsAvailable)
        self._worker._pendingCompositeEmit = True
        self._worker._interruptionRequested = True
        self._worker._flushCompositeEmit()
        self.assertEqual(0, spy.count(),
                         "flush must skip when interrupted")

    # ------------------------------------------------------------------
    #  _flushCompositeEmit
    # ------------------------------------------------------------------
    def testFlushEmitsImmediately(self):
        now = datetime.now()
        self._merge(("key1",), self._makeCommit("a" * 40, now))

        spy = QSignalSpy(self._worker.logsAvailable)
        self._worker._pendingCompositeEmit = True
        self._worker._flushCompositeEmit()
        self.assertEqual(1, spy.count())
        self.assertFalse(self._worker._pendingCompositeEmit)
        self.assertFalse(self._worker._compositeEmitTimer.isActive())

    def testFlushStopsActiveTimer(self):
        self._worker._scheduleCompositeEmit()
        self.assertTrue(self._worker._compositeEmitTimer.isActive())
        self._worker._flushCompositeEmit()  # no pending flag → no emit
        self.assertFalse(self._worker._compositeEmitTimer.isActive())

    def testFlushNoopWhenNoPending(self):
        spy = QSignalSpy(self._worker.logsAvailable)
        self._worker._flushCompositeEmit()
        self.assertEqual(0, spy.count(),
                         "flush with no pending should be a no-op")

    # ------------------------------------------------------------------
    #  _cleanupCompositeEmit
    # ------------------------------------------------------------------
    def testCleanupClearsEverything(self):
        now = datetime.now()
        self._merge(("key1",), self._makeCommit("a" * 40, now))
        self._worker._scheduleCompositeEmit()
        self._worker._awaitingConsumer = True

        self._worker._cleanupCompositeEmit()
        self.assertFalse(self._worker._compositeEmitTimer.isActive())
        self.assertFalse(self._worker._pendingCompositeEmit)
        self.assertFalse(self._worker._awaitingConsumer)
        self.assertEqual(0, len(self._worker._mergedLogs))
        self.assertEqual(0, len(self._worker._newLogs))

    # ------------------------------------------------------------------
    #  _handleCompositeLogs merge / deduplication
    # ------------------------------------------------------------------
    def testHandleCompositeLogs_mergeByKey(self):
        now = datetime.now()
        c1 = self._makeCommit("a" * 40, now, "same message",
                              "same author", "repoA")
        c2 = self._makeCommit("b" * 40, now, "same message",
                              "same author", "repoB")

        self._worker._handleCompositeLogs([c1], "repoA", b"main", 0, b"")
        self.assertEqual(1, len(self._worker._mergedLogs))

        self._worker._handleCompositeLogs([c2], "repoB", b"main", 0, b"")
        self.assertEqual(1, len(self._worker._mergedLogs),
                         "same key → merged")
        key = (c1.committerDateTime.date(), c1.comments, c1.author)
        merged = self._worker._mergedLogs[key]
        self.assertEqual(1, len(merged.subCommits))

    def testHandleCompositeLogs_mergedCommitIsNotReportedAsNew(self):
        """A commit folded into an existing row must not be emitted separately."""
        now = datetime.now()
        c1 = self._makeCommit("a" * 40, now, "same message",
                              "same author", "repoA")
        c2 = self._makeCommit("b" * 40, now, "same message",
                              "same author", "repoB")

        self._worker._handleCompositeLogs([c1], "repoA", b"main", 0, b"")
        self._worker._newLogs.clear()

        self._worker._handleCompositeLogs([c2], "repoB", b"main", 0, b"")
        self.assertEqual(0, len(self._worker._newLogs),
                         "sub-commit merges add no new rows")

    def testHandleCompositeLogs_newCommitIsReportedAsNew(self):
        now = datetime.now()
        c1 = self._makeCommit("a" * 40, now, "msg one", "author", "repoA")
        c2 = self._makeCommit("b" * 40, now, "msg two", "author", "repoB")

        self._worker._handleCompositeLogs([c1], "repoA", b"main", 0, b"")
        self._worker._newLogs.clear()

        self._worker._handleCompositeLogs([c2], "repoB", b"main", 0, b"")
        self.assertEqual([c2], self._worker._newLogs)

    def testHandleCompositeLogs_noMergeSameRepo(self):
        now = datetime.now()
        c1 = self._makeCommit("a" * 40, now, "msg", "author", "repoA")
        c2 = self._makeCommit("b" * 40, now, "msg", "author", "repoA")

        self._worker._handleCompositeLogs([c1], "repoA", b"main", 0, b"")
        self._worker._handleCompositeLogs([c2], "repoA", b"main", 0, b"")

        # c2 is stored under its sha1 as a separate key
        self.assertIn(c2.sha1, self._worker._mergedLogs)
        # The original key still holds c1 with no subCommits
        key = (c1.committerDateTime.date(), c1.comments, c1.author)
        self.assertEqual(self._worker._mergedLogs[key].sha1, c1.sha1)
        self.assertEqual(0, len(self._worker._mergedLogs[key].subCommits))
        self.assertEqual([c1, c2], self._worker._newLogs,
                         "a same-repo duplicate is a new row of its own")

    def testHandleCompositeLogs_thirdRepoMergesAfterSameRepoSplit(self):
        """The repoDir bookkeeping must track sub-commits, not just the main row."""
        now = datetime.now()
        c1 = self._makeCommit("a" * 40, now, "msg", "author", "repoA")
        c2 = self._makeCommit("b" * 40, now, "msg", "author", "repoB")
        c3 = self._makeCommit("c" * 40, now, "msg", "author", "repoB")

        self._worker._handleCompositeLogs([c1], "repoA", b"main", 0, b"")
        self._worker._handleCompositeLogs([c2], "repoB", b"main", 0, b"")
        self._worker._handleCompositeLogs([c3], "repoB", b"main", 0, b"")

        key = (c1.committerDateTime.date(), c1.comments, c1.author)
        self.assertEqual([c2], self._worker._mergedLogs[key].subCommits)
        self.assertIn(c3.sha1, self._worker._mergedLogs,
                      "repoB already contributed, so c3 becomes its own row")

    # ------------------------------------------------------------------
    #  _makeLocalCommits: untracked files associated with correct repoDir
    # ------------------------------------------------------------------
    def testMakeLocalCommits_untrackedFilesOnFirstRepo(self):
        """Untracked files from the first repo go on the top-level lucCommit."""
        lcc = Commit()
        luc = Commit()
        LogsFetcherWorkerBase._makeLocalCommits(
            lcc, luc, False, True, ".", ["file1.txt"])

        self.assertEqual(Git.LUC_SHA1, luc.sha1)
        self.assertEqual(".", luc.repoDir)
        self.assertEqual(["file1.txt"], luc.untrackedFiles)

    def testMakeLocalCommits_untrackedFilesOnSubCommit(self):
        """Untracked files from a second repo go on the sub-commit, not the top-level."""
        lcc = Commit()
        luc = Commit()
        # First repo (".") has LUC but no untracked files
        LogsFetcherWorkerBase._makeLocalCommits(
            lcc, luc, False, True, ".", None)
        # Second repo ("sub") has untracked files
        LogsFetcherWorkerBase._makeLocalCommits(
            lcc, luc, False, True, "sub", ["sub/file.txt"])

        self.assertEqual(".", luc.repoDir)
        self.assertEqual([], luc.untrackedFiles,
                         "top-level should not carry sub's untracked files")
        self.assertEqual(1, len(luc.subCommits))
        sub = luc.subCommits[0]
        self.assertEqual("sub", sub.repoDir)
        self.assertEqual(["sub/file.txt"], sub.untrackedFiles)

    def testMakeLocalCommits_untrackedFilesMultipleRepos(self):
        """Untracked files from multiple repos are kept on their respective owners."""
        lcc = Commit()
        luc = Commit()
        LogsFetcherWorkerBase._makeLocalCommits(
            lcc, luc, False, True, ".", ["top.txt"])
        LogsFetcherWorkerBase._makeLocalCommits(
            lcc, luc, False, True, "subA", ["subA/a.txt"])
        LogsFetcherWorkerBase._makeLocalCommits(
            lcc, luc, False, True, "subB", ["subB/b.txt"])

        self.assertEqual(["top.txt"], luc.untrackedFiles)
        self.assertEqual(2, len(luc.subCommits))

        subA = luc.subCommits[0]
        self.assertEqual("subA", subA.repoDir)
        self.assertEqual(["subA/a.txt"], subA.untrackedFiles)

        subB = luc.subCommits[1]
        self.assertEqual("subB", subB.repoDir)
        self.assertEqual(["subB/b.txt"], subB.untrackedFiles)
