# -*- coding: utf-8 -*-
import os
import shutil
import tempfile
import time
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from qgitc.application import Application
from qgitc.gitutils import Git, GitProcess
from tests.base import TestBase, createRepo
from unittest.mock import patch


class TestLogWindow(TestBase):
    def setUp(self):
        # HACK: do not depend on application
        GitProcess.GIT_BIN = shutil.which("git")
        self.oldDir = Git.REPO_DIR or os.getcwd()
        self.gitDir = tempfile.TemporaryDirectory()
        createRepo(self.gitDir.name)
        os.chdir(self.gitDir.name)

        super().setUp()
        self.window = self.app.getWindow(Application.LogWindow)
        # reduce logs to load to speed up tests
        self.window.ui.leOpts.setText("-n50")
        QTest.keyClick(self.window.ui.leOpts, Qt.Key_Enter)

    def tearDown(self):
        self.window.close()
        self.processEvents()
        super().tearDown()
        os.chdir(self.oldDir)
        Git.REPO_DIR = self.oldDir
        time.sleep(0.5)
        self.gitDir.cleanup()

    def testReloadRepo(self):
        self.assertFalse(self.window.isWindowReady)
        spyTimeout = QSignalSpy(self.window._delayTimer.timeout)
        logview = self.window.ui.gitViewA.logView
        spyFetcher = QSignalSpy(logview.fetcher.fetchFinished)

        self.window.show()
        # wait for repo to be loaded
        while spyTimeout.count() == 0:
            self.processEvents()

        self.assertTrue(self.window.isWindowReady)
        while logview.fetcher.isLoading() or spyFetcher.count() == 0:
            self.processEvents()

        # now reload the repo
        spyBegin = QSignalSpy(logview.beginFetch)
        spyEnd = QSignalSpy(logview.endFetch)
        spyTimer = QSignalSpy(self.window.ui.gitViewA._delayTimer.timeout)

        self.window.reloadRepo()

        spyEnd.wait(3000)
        # we don't do any abort operation, so the begin and end should be called only once
        self.assertEqual(1, spyBegin.count())
        self.assertEqual(1, spyEnd.count())

        # the timer should never be triggered
        self.assertEqual(0, spyTimer.count())

    def testCompositeMode(self):
        createRepo(os.path.join(self.gitDir.name, "subRepo"))

        spyTimeout = QSignalSpy(self.window._delayTimer.timeout)
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)

        while spyTimeout.count() == 0:
            self.processEvents()

        spySubmodule = QSignalSpy(self.window.submoduleAvailable)
        while spySubmodule.count() == 0:
            self.processEvents()

        self.assertEqual(2, self.window.ui.cbSubmodule.count())
        self.assertEqual(".", self.window.ui.cbSubmodule.itemText(0))
        self.assertEqual("subRepo", self.window.ui.cbSubmodule.itemText(1))

        logView = self.window.ui.gitViewA.ui.logView
        spyFetch = QSignalSpy(logView.fetcher.fetchFinished)
        self.window.ui.acCompositeMode.trigger()
        self.assertTrue(self.window.ui.acCompositeMode.isChecked())

        while spyFetch.count() == 0:
            self.processEvents()

        self.assertFalse(self.window.ui.cbSubmodule.isEnabled())

        self.assertEqual(logView.getCount(), 2)
        commit = logView.getCommit(0)
        self.assertTrue(commit.repoDir in [".", "subRepo"])
        self.assertEqual(1, len(commit.subCommits))

        commit = logView.getCommit(1)
        self.assertTrue(commit.repoDir in [".", "subRepo"])
        self.assertEqual(1, len(commit.subCommits))

        self.window.cancel(True)
        self.processEvents()
