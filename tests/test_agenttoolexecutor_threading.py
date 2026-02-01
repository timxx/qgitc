# -*- coding: utf-8 -*-

from PySide6.QtCore import QCoreApplication, QThread

from qgitc.agenttoolexecutor import AgentToolExecutor
from tests.base import TestBase


class TestAgentToolExecutorThreading(TestBase):

    def doCreateRepo(self):
        super().doCreateRepo()

    def test_toolFinished_emitted_on_main_thread(self):
        ex = AgentToolExecutor(self.app)
        done = []
        main_thread = QCoreApplication.instance().thread()

        def _on_finished(res):
            done.append(QThread.currentThread() == main_thread)

        ex.toolFinished.connect(_on_finished)

        # Use a lightweight tool that doesn't require network; repo is created in setUp.
        ok = ex.executeAsync("git_status", {"repo_dir": "", "untracked": True})
        self.assertTrue(ok)

        self.wait(2000, lambda: len(done) == 0)
        self.assertEqual(1, len(done))
        self.assertTrue(done[0])
