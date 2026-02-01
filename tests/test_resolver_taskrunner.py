# -*- coding: utf-8 -*-

import gc
import weakref

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

    def test_task_result_not_released_before_slots_run(self):
        runner = TaskRunner(self.app)
        observed = []

        t = runner.run(lambda: 123)
        wr = weakref.ref(t)

        def _on_finished(ok, res, err):
            obj = wr()
            self.assertIsNotNone(obj)
            self.assertIn(obj, runner._pending)
            observed.append((ok, res, err))

        t.finished.connect(_on_finished)

        del t
        gc.collect()

        self.wait(500, lambda: len(observed) == 0)
        self.assertEqual(1, len(observed))

        # Cleanup is deferred, so it should be gone shortly after.
        self.wait(500, lambda: len(runner._pending) != 0)
        self.assertEqual(0, len(runner._pending))
