# -*- coding: utf-8 -*-

import gc

from PySide6.QtTest import QSignalSpy

from qgitc.resolver.taskrunner import TaskRunner
from tests.base import TestBase


class TestTaskRunner(TestBase):

    def doCreateRepo(self):
        pass

    def test_task_result_kept_alive_until_finished(self):
        runner = TaskRunner(self.app)
        done = []

        t = runner.run(lambda: 123)
        spy = QSignalSpy(t.finished)
        t.finished.connect(lambda ok, res, err: done.append((ok, res, err)))

        # Drop the last local reference; previously this could be GC'ed before signal delivery.
        del t
        gc.collect()

        self.wait(500, lambda: len(done) == 0)
        self.assertEqual(1, len(done))
        ok, res, err = done[0]
        self.assertTrue(ok)
        self.assertEqual(123, res)
        self.assertIsNone(err)
        self.assertEqual(1, spy.count())
