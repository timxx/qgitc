# -*- coding: utf-8 -*-
import os
import tempfile
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QMessageBox
from qgitc.application import Application
from qgitc.gitutils import Git
from tests.base import TestBase, createRepo
from unittest.mock import patch


class TestLogWindow(TestBase):
    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(Application.LogWindow)
        # reduce logs to load to speed up tests
        self.window.ui.leOpts.setText("-n50")
        QTest.keyClick(self.window.ui.leOpts, Qt.Key_Enter)

    def tearDown(self):
        self.window.close()
        self.processEvents()
        super().tearDown()

    def testReloadRepo(self):
        logview = self.window.ui.gitViewA.logView
        spyFetcher = QSignalSpy(logview.fetcher.fetchFinished)

        with patch("PySide6.QtWidgets.QMessageBox.critical") as critical:
            critical.return_value = QMessageBox.Ok

            self.assertFalse(self.window.isWindowReady)
            spyTimeout = QSignalSpy(self.window._delayTimer.timeout)
            self.window.show()
            QTest.qWaitForWindowExposed(self.window)
            self.assertTrue(self.window.isWindowReady)
            while spyTimeout.count() == 0:
                self.processEvents()

            while logview.fetcher.isLoading() or spyFetcher.count() == 0:
                self.processEvents()
            self.assertEqual(1, spyFetcher.count())

            isShallowRepo = Git.isShallowRepo()
            if isShallowRepo:
                branch = Git.activeBranch()
                hasSymbolicRef = branch is not None and branch != "HEAD"
                if not hasSymbolicRef:
                    critical.assert_called_once()
                    self.assertTrue(spyFetcher.at(0)[0] != 0)

            spyBegin = QSignalSpy(logview.beginFetch)
            spyEnd = QSignalSpy(logview.endFetch)
            spyTimer = QSignalSpy(self.window.ui.gitViewA._delayTimer.timeout)

            self.window.reloadRepo()

            spyEnd.wait(3000)
            # we don't do any abort operation, so the begin and end should be called once
            self.assertEqual(1, spyBegin.count())
            self.assertEqual(1, spyEnd.count())

            # the timer should never be triggered
            self.assertEqual(0, spyTimer.count())

            if isShallowRepo and not hasSymbolicRef:
                self.assertEqual(critical.call_count, 2)

    def testCompositeMode(self):
        spyTimeout = QSignalSpy(self.window._delayTimer.timeout)
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)
        oldRepoDir = Git.REPO_DIR

        while spyTimeout.count() == 0:
            self.processEvents()

        with tempfile.TemporaryDirectory() as dir:
            createRepo(dir)
            createRepo(os.path.join(dir, "subRepo"))

            self.window.ui.leRepo.setText(dir)
            while spyTimeout.count() == 1:
                self.processEvents()

            spySubmodule = QSignalSpy(self.window.submoduleAvailable)
            while spySubmodule.count() == 0:
                self.processEvents()

            self.assertEqual(2, self.window.ui.cbSubmodule.count())

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

        # restore
        Git.REPO_DIR = oldRepoDir
