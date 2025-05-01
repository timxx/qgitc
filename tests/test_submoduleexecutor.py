# -*- coding: utf-8 -*-
import time
from unittest.mock import patch
from PySide6.QtTest import QSignalSpy, QTest
from qgitc.cancelevent import CancelEvent
from qgitc.submoduleexecutor import SubmoduleExecutor
from tests.base import TestBase


def _dummyAction(submodule, data, cancelEvent: CancelEvent):
    raise Exception("Should not be called")


def _dummyAction2(submodule, data, cancelEvent: CancelEvent):
    return "Hello"


def _dummyResult(*kargs):
    raise Exception("Should not be called")


class TestSubmoduleExecutor(TestBase):
    def testSubmit(self):
        executor = SubmoduleExecutor()
        spy = QSignalSpy(executor.finished)

        with patch("test_submoduleexecutor._dummyAction") as dummy:
            dummy.return_value = "Hello"
            executor.submit(None, _dummyAction)
            QTest.qWait(100)
            self.assertTrue(spy.wait(50))
            self.assertTrue(spy.count(), 1)
            dummy.assert_called_once()

        with patch("test_submoduleexecutor._dummyResult") as dummy:
            executor.submit([None], _dummyAction2, _dummyResult)
            QTest.qWait(100)
            self.assertTrue(spy.wait(50))
            self.assertTrue(spy.count(), 1)
            dummy.assert_called_once_with("Hello")

    def _cancelAction(self, submodule, data, cancelEvent: CancelEvent):
        time.sleep(0.1)
        if cancelEvent.isSet():
            return True
        return False

    def testCancel(self):
        executor = SubmoduleExecutor()
        spy = QSignalSpy(executor.finished)

        with patch("test_submoduleexecutor._dummyResult") as dummy:
            executor.submit(None, self._cancelAction, _dummyResult)
            QTest.qWait(50)
            self.assertTrue(executor.isRunning())
            executor.cancel()
            QTest.qWait(600)
            self.assertFalse(executor.isRunning())
            # the signal is disconnected
            self.assertFalse(spy.wait(500))
            dummy.assert_not_called()

    def _blockAction(self, submodule, data, cancelEvent: CancelEvent):
        time.sleep(10)

    def testAbort(self):
        executor = SubmoduleExecutor()

        with patch("logging.Logger.warning") as warning:
            executor.submit(None, self._blockAction)
            QTest.qWait(100)
            self.assertTrue(executor.isRunning())
            executor.cancel(True)

            QTest.qWait(1000)
            self.assertFalse(executor.isRunning())

            warning.assert_called_once_with(
                "Terminating submodule thread (%s)", "_blockAction")

        with patch("logging.Logger.warning") as warning:
            executor.submit(None, self._blockAction)
            QTest.qWait(100)
            self.assertTrue(executor.isRunning())
            executor.cancel()

            # Actually running in background
            self.assertFalse(executor.isRunning())
            self.assertIsNone(executor._thread)

            warning.assert_not_called()

            self.assertEqual(1, len(executor._threads))

            # avoid crashing here
            executor._threads[0].terminate()
            self.processEvents()
            QTest.qWait(100)
