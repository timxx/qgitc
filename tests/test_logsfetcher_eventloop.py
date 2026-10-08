# -*- coding: utf-8 -*-
"""run() must not destroy its QEventLoop in the worker thread."""

from PySide6.QtCore import QThread

from qgitc.logsfetcherqprocessworker import LogsFetcherQProcessWorker
from tests.base import TestBase


class TestLogsFetcherEventLoopLifetime(TestBase):
    """The event loop belongs to the worker thread; its destruction must not.

    Destroying a QObject in the worker thread takes Qt object locks and then
    waits for the Python GIL, which the GUI thread holds while waiting for
    those same locks: the process freezes and even the test watchdog cannot
    fire. The worker therefore retires its loops into _finishedEventLoops and
    the GUI thread drops them from releaseFinishedFetchers().
    """

    def testEventLoopIsRetiredNotDestroyedInWorker(self):
        worker = LogsFetcherQProcessWorker(
            [], self.gitDir.name, False, None, ["test.py"])
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.start()
        try:
            self.wait(5000, lambda: not worker._finishedEventLoops)
            self.assertTrue(
                worker._finishedEventLoops,
                "run() must retire its QEventLoop instead of dropping it in "
                "the worker thread")
        finally:
            thread.quit()
            self.wait(5000, thread.isRunning)
            thread.wait(3000)

        self.assertIsNone(worker._eventLoop)
        worker.releaseFinishedFetchers()
        self.assertFalse(worker._finishedEventLoops)
