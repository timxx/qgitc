# -*- coding: utf-8 -*-
"""Unit tests for LogsFetcherWorkerBase composite-mode incremental-emission logic."""

from datetime import datetime, timedelta

from PySide6.QtTest import QSignalSpy

from qgitc.common import Commit
from qgitc.logsfetcherworkerbase import LogsFetcherWorkerBase
from tests.base import TestBase


class _TestWorker(LogsFetcherWorkerBase):
    """Minimal concrete worker so we can instantiate the base class."""

    def run(self):
        pass


class TestLogsFetcherWorkerBaseComposite(TestBase):
    """Tests focused on the new incremental emission primitives."""

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
        c1 = Commit()
        c1.sha1 = "a" * 40
        c1.committerDateTime = now
        self._worker._mergedLogs[("key",)] = c1

        captured = []

        def _capture(logs):
            captured.append(logs)

        self._worker.logsAvailable.connect(_capture)
        self._worker._scheduleCompositeEmit()
        spy = QSignalSpy(self._worker.logsAvailable)
        spy.wait(200)

        self.assertEqual(1, len(captured))
        self.assertEqual(1, len(captured[0]))

    # ------------------------------------------------------------------
    #  _mergedLogs persistence across incremental emits
    # ------------------------------------------------------------------
    def testEmitDoesNotClearMergedLogs(self):
        now = datetime.now()
        c1 = Commit()
        c1.sha1 = "a" * 40
        c1.committerDateTime = now
        self._worker._mergedLogs[("key1",)] = c1

        self._worker._emitCompositeLogsAvailable()
        self.assertEqual(1, len(self._worker._mergedLogs),
                         "_mergedLogs must survive _emitCompositeLogsAvailable")

        c2 = Commit()
        c2.sha1 = "b" * 40
        c2.committerDateTime = now - timedelta(hours=1)
        self._worker._mergedLogs[("key2",)] = c2

        self._worker._emitCompositeLogsAvailable()
        self.assertEqual(2, len(self._worker._mergedLogs),
                         "second emit must still carry both entries")

    def testEmitEmptyMergedLogs_noEmit(self):
        spy = QSignalSpy(self._worker.logsAvailable)
        self._worker._emitCompositeLogsAvailable()
        self.assertEqual(0, spy.count())

    def testMergedLogsAccumulatesAcrossScheduleEmits(self):
        now = datetime.now()
        c1 = Commit()
        c1.sha1 = "a" * 40
        c1.committerDateTime = now
        self._worker._mergedLogs[("key1",)] = c1

        captured = []

        def _capture(logs):
            captured.append(logs)

        self._worker.logsAvailable.connect(_capture)
        self._worker._scheduleCompositeEmit()
        spy = QSignalSpy(self._worker.logsAvailable)
        spy.wait(200)
        self.assertEqual(1, len(captured))
        self.assertEqual(1, len(captured[0]))
        self.assertEqual(1, len(self._worker._mergedLogs),
                         "mergedLogs must persist")

        c2 = Commit()
        c2.sha1 = "b" * 40
        c2.committerDateTime = now - timedelta(hours=1)
        self._worker._mergedLogs[("key2",)] = c2

        self._worker._scheduleCompositeEmit()
        spy.wait(200)
        self.assertEqual(2, len(captured))
        self.assertEqual(2, len(captured[1]),
                         "second batch must include both commits")
        self.assertEqual(2, len(self._worker._mergedLogs))

    # ------------------------------------------------------------------
    #  Interruption guards
    # ------------------------------------------------------------------
    def testScheduleEmit_skipsWhenInterrupted(self):
        now = datetime.now()
        c1 = Commit()
        c1.sha1 = "a" * 40
        c1.committerDateTime = now
        self._worker._mergedLogs[("key1",)] = c1

        spy = QSignalSpy(self._worker.logsAvailable)
        self._worker._scheduleCompositeEmit()
        self._worker._interruptionRequested = True
        spy.wait(200)
        self.assertEqual(0, spy.count(),
                         "interruption must suppress timer emission")

    def testFlushEmit_skipsWhenInterrupted(self):
        now = datetime.now()
        c1 = Commit()
        c1.sha1 = "a" * 40
        c1.committerDateTime = now
        self._worker._mergedLogs[("key1",)] = c1

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
        c1 = Commit()
        c1.sha1 = "a" * 40
        c1.committerDateTime = now
        self._worker._mergedLogs[("key1",)] = c1

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
        c1 = Commit()
        c1.sha1 = "a" * 40
        c1.committerDateTime = now
        self._worker._mergedLogs[("key1",)] = c1
        self._worker._scheduleCompositeEmit()

        self._worker._cleanupCompositeEmit()
        self.assertFalse(self._worker._compositeEmitTimer.isActive())
        self.assertFalse(self._worker._pendingCompositeEmit)
        self.assertEqual(0, len(self._worker._mergedLogs))

    # ------------------------------------------------------------------
    #  _handleCompositeLogs merge / deduplication
    # ------------------------------------------------------------------
    def testHandleCompositeLogs_mergeByKey(self):
        now = datetime.now()
        c1 = Commit()
        c1.sha1 = "a" * 40
        c1.comments = "same message"
        c1.author = "same author"
        c1.repoDir = "repoA"
        c1.committerDateTime = now
        c1.subCommits = []

        c2 = Commit()
        c2.sha1 = "b" * 40
        c2.comments = "same message"
        c2.author = "same author"
        c2.repoDir = "repoB"
        c2.committerDateTime = now
        c2.subCommits = []

        self._worker._handleCompositeLogs([c1], "repoA", b"main", 0, b"")
        self.assertEqual(1, len(self._worker._mergedLogs))

        self._worker._handleCompositeLogs([c2], "repoB", b"main", 0, b"")
        self.assertEqual(1, len(self._worker._mergedLogs),
                         "same key → merged")
        key = (c1.committerDateTime.date(), c1.comments, c1.author)
        merged = self._worker._mergedLogs[key]
        self.assertEqual(1, len(merged.subCommits))

    def testHandleCompositeLogs_noMergeSameRepo(self):
        now = datetime.now()
        c1 = Commit()
        c1.sha1 = "a" * 40
        c1.comments = "msg"
        c1.author = "author"
        c1.repoDir = "repoA"
        c1.committerDateTime = now
        c1.subCommits = []

        c2 = Commit()
        c2.sha1 = "b" * 40
        c2.comments = "msg"
        c2.author = "author"
        c2.repoDir = "repoA"
        c2.committerDateTime = now
        c2.subCommits = []

        self._worker._handleCompositeLogs([c1], "repoA", b"main", 0, b"")
        self._worker._handleCompositeLogs([c2], "repoA", b"main", 0, b"")

        # c2 is stored under its sha1 as a separate key
        self.assertIn(c2.sha1, self._worker._mergedLogs)
        # The original key still holds c1 with no subCommits
        key = (c1.committerDateTime.date(), c1.comments, c1.author)
        self.assertEqual(self._worker._mergedLogs[key].sha1, c1.sha1)
        self.assertEqual(0, len(self._worker._mergedLogs[key].subCommits))

    # ------------------------------------------------------------------
    #  Sort order
    # ------------------------------------------------------------------
    def testEmitSortsDescendingByCommitterDateTime(self):
        now = datetime.now()
        c1 = Commit()
        c1.sha1 = "a" * 40
        c1.committerDateTime = now

        c2 = Commit()
        c2.sha1 = "b" * 40
        c2.committerDateTime = now - timedelta(hours=2)

        c3 = Commit()
        c3.sha1 = "c" * 40
        c3.committerDateTime = now - timedelta(hours=1)

        self._worker._mergedLogs = {
            ("k1",): c1, ("k2",): c2, ("k3",): c3,
        }

        captured = []

        def _capture(logs):
            captured.append(logs)

        self._worker.logsAvailable.connect(_capture)
        self._worker._emitCompositeLogsAvailable()
        self.assertEqual(1, len(captured))
        result = captured[0]
        self.assertEqual([c1, c3, c2], result,
                         "sorted newest-first by committerDateTime")
