import os
from typing import List
from unittest.mock import patch

from PySide6.QtCore import QThread
from PySide6.QtTest import QSignalSpy

from qgitc.common import Commit
from qgitc.gitutils import Git
from qgitc.logsfetcherimpl import LogsFetcherImpl
from qgitc.logsfetcherqprocessworker import LogsFetcherQProcessWorker
from tests.base import TestBase


class TestLogsFetcherQProcessWorker(TestBase):

    def createSubRepo(self):
        return True

    def testFetch(self):
        submodules = [".", "subRepo"]
        worker = LogsFetcherQProcessWorker(
            submodules, self.gitDir.name, False, "main", None)
        spyFinished = QSignalSpy(worker.fetchFinished)
        spyLogsAvailable = QSignalSpy(worker.logsAvailable)
        spyLocalChangesAvailable = QSignalSpy(worker.localChangesAvailable)
        worker.run()

        self.wait(100, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)
        self.assertEqual(spyFinished.at(0)[0], 0)

        self.assertEqual(spyLogsAvailable.count(), 1)
        payload = spyLogsAvailable.at(0)[0]
        allLogs, insertPositions = payload
        self.assertIsInstance(allLogs, list)
        self.assertEqual(len(allLogs), 3)

        self.assertEqual(spyLocalChangesAvailable.count(), 1)
        lccCommit: Commit = spyLocalChangesAvailable.at(0)[0]
        lucCommit: Commit = spyLocalChangesAvailable.at(0)[1]
        self.assertEqual(lccCommit.sha1, '')
        self.assertEqual(lucCommit.sha1, '')

    def testFetchWithLocalChanges(self):
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Test content")

        submodules = [".", "subRepo"]
        worker = LogsFetcherQProcessWorker(
            submodules, self.gitDir.name, False, "main", None)
        spyFinished = QSignalSpy(worker.fetchFinished)
        spyLogsAvailable = QSignalSpy(worker.logsAvailable)
        spyLocalChangesAvailable = QSignalSpy(worker.localChangesAvailable)
        worker.run()

        self.wait(100, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)
        self.assertEqual(spyFinished.at(0)[0], 0)

        self.assertEqual(spyLogsAvailable.count(), 1)
        payload = spyLogsAvailable.at(0)[0]
        allLogs, insertPositions = payload
        self.assertIsInstance(allLogs, list)
        self.assertEqual(len(allLogs), 3)

        self.assertEqual(spyLocalChangesAvailable.count(), 1)
        lccCommit: Commit = spyLocalChangesAvailable.at(0)[0]
        lucCommit: Commit = spyLocalChangesAvailable.at(0)[1]
        self.assertEqual(lccCommit.sha1, '')
        self.assertEqual(lucCommit.sha1, Git.LUC_SHA1)

        with open(os.path.join(self.gitDir.name, "test.py"), "a+") as f:
            f.write("print('Test')")

        Git.addFiles(repoDir=self.gitDir.name, files=["test.py"])

        worker = LogsFetcherQProcessWorker(
            submodules, self.gitDir.name, False, "main", None)
        spyLocalChangesAvailable = QSignalSpy(worker.localChangesAvailable)
        worker.run()

        self.wait(100, lambda: spyLocalChangesAvailable.count() == 0)
        self.assertEqual(spyLocalChangesAvailable.count(), 1)

        lccCommit, lucCommit = spyLocalChangesAvailable.at(0)
        self.assertEqual(lccCommit.sha1, Git.LCC_SHA1)
        self.assertEqual(lucCommit.sha1, Git.LUC_SHA1)

    def testFetchMainOnly(self):
        worker = LogsFetcherQProcessWorker(
            None, self.gitDir.name, False, "main", None)
        spyFinished = QSignalSpy(worker.fetchFinished)
        spyLogsAvailable = QSignalSpy(worker.logsAvailable)
        spyLocalChangesAvailable = QSignalSpy(worker.localChangesAvailable)
        worker.run()

        self.wait(100, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)
        self.assertEqual(spyFinished.at(0)[0], 0)

        logs: List[Commit] = []
        for i in range(spyLogsAvailable.count()):
            payload = spyLogsAvailable.at(i)[0]
            if isinstance(payload, tuple):
                allLogs, _ = payload
                logs.extend(allLogs)
            else:
                logs.extend(payload)

        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[0].comments, "Add .gitignore")

        self.assertGreaterEqual(spyLogsAvailable.count(), 1)

        self.assertEqual(spyLocalChangesAvailable.count(), 1)
        lccCommit: Commit = spyLocalChangesAvailable.at(0)[0]
        lucCommit: Commit = spyLocalChangesAvailable.at(0)[1]
        self.assertEqual(lccCommit.sha1, '')
        self.assertEqual(lucCommit.sha1, '')

    def testFetchWithUntrackedFiles(self):
        with open(os.path.join(self.gitDir.name, "untracked.py"), "w") as f:
            f.write("print('untracked')")

        submodules = [".", "subRepo"]
        worker = LogsFetcherQProcessWorker(
            submodules, self.gitDir.name, False, "main", None)
        spyFinished = QSignalSpy(worker.fetchFinished)
        spyLocalChangesAvailable = QSignalSpy(worker.localChangesAvailable)
        worker.run()

        self.wait(100, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)

        self.assertEqual(spyLocalChangesAvailable.count(), 1)
        lccCommit: Commit = spyLocalChangesAvailable.at(0)[0]
        lucCommit: Commit = spyLocalChangesAvailable.at(0)[1]
        self.assertEqual(lccCommit.sha1, '')
        self.assertEqual(lucCommit.sha1, Git.LUC_SHA1)
        self.assertIn("untracked.py", lucCommit.untrackedFiles)

    def testRequestInterruptionQuitsEventLoopOnWorkerThread(self):
        class StrictEventLoop:
            def __init__(self, ownerThread):
                self.ownerThread = ownerThread
                self.quitCalled = False
                self.quitThread = None

            def quit(self):
                current = QThread.currentThread()
                if current != self.ownerThread:
                    raise AssertionError(
                        "event loop quit called from wrong thread")
                self.quitCalled = True
                self.quitThread = current

        worker = LogsFetcherQProcessWorker(
            None, self.gitDir.name, False, "main", None)
        thread = QThread()
        worker.moveToThread(thread)
        loop = StrictEventLoop(thread)
        worker._eventLoop = loop

        thread.start()
        try:
            worker.requestInterruption()
            self.wait(1000, lambda: not loop.quitCalled)

            self.assertTrue(loop.quitCalled)
            self.assertIs(loop.quitThread, thread)
        finally:
            thread.quit()
            thread.wait(1000)

    def testRequestInterruptionBeforeEventLoopSkipsExec(self):
        class FakeEventLoop:
            instance = None

            def __init__(self):
                self.execCalled = False
                self.quitCalled = False
                FakeEventLoop.instance = self

            def exec(self):
                self.execCalled = True

            def quit(self):
                self.quitCalled = True

        worker = LogsFetcherQProcessWorker(
            None, None, False, "main", None)
        worker.requestInterruption()

        with patch("qgitc.logsfetcherqprocessworker.QEventLoop", FakeEventLoop), \
                patch.object(LogsFetcherImpl, "fetch", return_value=None):
            worker._fetchNormal()

        loop = FakeEventLoop.instance
        self.assertIsNotNone(loop)
        self.assertTrue(loop.quitCalled)
        self.assertFalse(loop.execCalled)

    def testFinishedFetchersKeptAliveUntilCleanup(self):
        """After _onFetchFinished removes a fetcher, it must be kept alive via
        _finishedFetchers (with deleteLater) to prevent Python GC from destroying
        QProcess children (with internal QBasicTimers) on a potentially different
        thread, which produces:
          "QBasicTimer::stop: Failed. Possibly trying to stop from a different thread"
        """
        submodules = [".", "subRepo"]
        worker = LogsFetcherQProcessWorker(
            submodules, self.gitDir.name, False, "main", None)
        spyFinished = QSignalSpy(worker.fetchFinished)
        worker.run()

        self.wait(2000, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)

        # Verify that finished fetchers were tracked and then cleared
        self.assertEqual(len(worker._finishedFetchers), 0,
                         "_finishedFetchers must be cleared after success")

        # Verify with gc pressure: create a worker, set low GC threshold,
        # run to completion, and confirm no crash or missing entries
        import gc
        oldThresholds = gc.get_threshold()
        try:
            gc.set_threshold(1, 1, 1)

            worker2 = LogsFetcherQProcessWorker(
                submodules, self.gitDir.name, False, "main", None)
            spyFinished2 = QSignalSpy(worker2.fetchFinished)
            worker2.run()

            self.wait(5000, lambda: spyFinished2.count() == 0)
            self.assertEqual(spyFinished2.count(), 1)
            self.assertEqual(len(worker2._finishedFetchers), 0,
                             "_finishedFetchers must be cleared after success")
        finally:
            gc.set_threshold(*oldThresholds)
            gc.collect()
