# -*- coding: utf-8 -*-

from PySide6.QtCore import QCoreApplication, QThread

from qgitc.submoduleexecutor import SubmoduleExecutor
from tests.base import TestBase


class TestSubmoduleExecutorThreading(TestBase):

    def doCreateRepo(self):
        super().doCreateRepo()

    def test_result_handler_runs_on_main_thread(self):
        ex = SubmoduleExecutor(self.app)
        done = []
        finished = []
        main_thread = QCoreApplication.instance().thread()

        def action(submodule, userData, cancelEvent):
            return ("ok", 123)

        def on_result(tag, value):
            # This MUST run on the main Qt thread.
            done.append(QThread.currentThread() == main_thread)

        ex.finished.connect(lambda: finished.append(True))
        ex.submit([None], action, on_result, useMultiThreading=True)

        self.wait(2000, lambda: len(finished) == 0)
        self.assertEqual(1, len(done))
        self.assertTrue(done[0])
        self.assertEqual(1, len(finished))
