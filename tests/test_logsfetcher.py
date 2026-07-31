# -*- coding: utf-8 -*-

import unittest
import warnings
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QThread

from qgitc.logsfetcher import LogsFetcher
from qgitc.logsfetcherworkerbase import LogsFetcherWorkerBase
from tests.base import TestBase


class _MockWorker(LogsFetcherWorkerBase):
    """Worker stub that won't try to run real git commands."""

    def run(self):
        pass

    def needReportSlowFetch(self):
        return False


class TestLogsFetcherCancel(unittest.TestCase):
    """Unit tests for cancel() — no QApplication or git repo needed."""

    def _makeWorker(self):
        worker = _MockWorker([], None, True)
        worker.requestInterruption = MagicMock()
        return worker

    def _connectWorker(self, fetcher):
        """Simulate what fetch() does: connect worker signals."""
        fetcher._worker.logsAvailable.connect(fetcher._onLogsAvailable)
        fetcher._worker.fetchFinished.connect(fetcher._onFetchFinished)
        fetcher._worker.localChangesAvailable.connect(
            fetcher._onLocalChangesAvailable)

    def testCancelClearsWorkerReference(self):
        """cancel() must set _worker to None so that a subsequent fetch()
        knows a fresh worker is needed."""
        fetcher = LogsFetcher()
        fetcher._worker = self._makeWorker()
        fetcher._thread = QThread()
        self._connectWorker(fetcher)

        fetcher.cancel()

        self.assertIsNone(fetcher._worker)

    def testDoubleCancelDoesNotWarn(self):
        """Calling cancel() twice must not produce RuntimeWarning about
        failed disconnects."""
        fetcher = LogsFetcher()
        fetcher._worker = self._makeWorker()
        fetcher._thread = QThread()
        self._connectWorker(fetcher)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            fetcher.cancel()
            # Second cancel: _worker is already None, should be a no-op.
            fetcher.cancel()

        runtimeWarnings = [
            x for x in w if issubclass(x.category, RuntimeWarning)]
        self.assertEqual(
            len(runtimeWarnings), 0,
            f"Got unexpected RuntimeWarning(s): {[str(x.message) for x in runtimeWarnings]}")

    def testCancelDoesNotReleasePendingWorkerRef(self):
        """cancel() must keep the worker alive in _pendingWorkers so that
        GC doesn't destroy QProcess children cross-thread while the
        thread is still running."""
        fetcher = LogsFetcher()
        worker = self._makeWorker()
        fetcher._worker = worker
        thread = QThread()
        fetcher._thread = thread
        fetcher._pendingWorkers[thread] = worker
        self._connectWorker(fetcher)

        fetcher.cancel()

        self.assertIsNone(fetcher._worker)
        self.assertIn(thread, fetcher._pendingWorkers)
        self.assertIs(fetcher._pendingWorkers[thread], worker)

    def testFetchCreatesNewWorkerAfterCancel(self):
        """After cancel() clears _worker, fetch() must create a brand-new
        worker instance rather than reconnecting to the stale one."""
        fetcher = LogsFetcher()
        oldWorker = self._makeWorker()
        fetcher._worker = oldWorker
        fetcher._thread = QThread()
        self._connectWorker(fetcher)

        fetcher.cancel()
        self.assertIsNone(fetcher._worker)

        # Patch the worker class so fetch() creates a stub instead of a
        # real QProcess-based worker that would try to run git commands.
        # Also stub QThread.start to avoid spawning real OS threads.
        with patch("qgitc.logsfetcher.LogsFetcherQProcessWorker",
                   return_value=self._makeWorker()):
            with patch("qgitc.logsfetcher.ApplicationBase") as mockApp:
                with patch.object(QThread, "start"):
                    mockApp.instance.return_value.settings.return_value.detectLocalChanges.return_value = False
                    fetcher._submodules = ["."]
                    fetcher.fetch("main", None, branchDir=None)

        self.assertIsNotNone(fetcher._worker)
        self.assertIsNot(fetcher._worker, oldWorker)


class TestLogsFetcherBackpressure(TestBase):
    """The worker must learn when a delivered batch has been consumed."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self._fetcher = LogsFetcher()
        self._worker = _MockWorker([], None, True)
        self._fetcher._worker = self._worker
        self._worker.logsAvailable.connect(self._fetcher._onLogsAvailable)

    def tearDown(self):
        self._worker.deleteLater()
        self.processEvents()
        super().tearDown()

    def testDeliveredBatchIsAcknowledged(self):
        forwarded = []
        self._fetcher.logsAvailable.connect(forwarded.append)

        self._worker._awaitingConsumer = True
        self._worker.logsAvailable.emit([])
        self.assertEqual([[]], forwarded)

        self.assertTrue(self._worker._awaitingConsumer,
                        "the ack is queued, not immediate")
        self.processEvents()
        self.assertFalse(self._worker._awaitingConsumer)

    def testStaleWorkerIsNotAcknowledged(self):
        self._fetcher._worker = None
        self._worker._awaitingConsumer = True

        self._worker.logsAvailable.emit([])
        self.processEvents()

        self.assertTrue(self._worker._awaitingConsumer,
                        "batches from a replaced worker must be dropped")
