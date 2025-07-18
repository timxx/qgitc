# -*- coding: utf-8 -*-
import os

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest

from qgitc.gitutils import Git
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestLogWindow(TestBase):
    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(WindowType.LogWindow)

    def tearDown(self):
        self.window.close()
        self.processEvents()
        super().tearDown()

    def createSubRepo(self):
        return True

    def waitForLoaded(self):
        spySubmodule = QSignalSpy(self.window.submoduleAvailable)

        self.window.show()
        QTest.qWaitForWindowExposed(self.window)

        delayTimer = self.window._delayTimer
        self.wait(10000, delayTimer.isActive)
        self.wait(10000, lambda: spySubmodule.count() == 0)

        logview = self.window.ui.gitViewA.ui.logView
        self.wait(10000, logview.fetcher.isLoading)
        self.wait(50)

    def testReloadRepo(self):
        self.assertFalse(self.window.isWindowReady)
        self.waitForLoaded()
        self.assertTrue(self.window.isWindowReady)

        logview = self.window.ui.gitViewA.ui.logView
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
        self.waitForLoaded()

        self.assertEqual(2, self.window.ui.cbSubmodule.count())
        self.assertEqual(".", self.window.ui.cbSubmodule.itemText(0))
        self.assertEqual("subRepo", self.window.ui.cbSubmodule.itemText(1))

        logView = self.window.ui.gitViewA.ui.logView
        spyFetch = QSignalSpy(logView.fetcher.fetchFinished)
        self.window.ui.acCompositeMode.trigger()
        self.assertTrue(self.window.ui.acCompositeMode.isChecked())

        self.wait(10000, lambda: spyFetch.count() == 0)

        self.assertFalse(self.window.ui.cbSubmodule.isEnabled())

        self.assertEqual(logView.getCount(), 3)
        commit = logView.getCommit(0)
        self.assertEqual(commit.repoDir, ".")
        self.assertEqual(0, len(commit.subCommits))

        commit = logView.getCommit(1)
        self.assertTrue(commit.repoDir in [".", "subRepo"])
        self.assertEqual(1, len(commit.subCommits))

        commit = logView.getCommit(2)
        self.assertTrue(commit.repoDir in [".", "subRepo"])
        self.assertEqual(1, len(commit.subCommits))

        self.window.cancel(True)
        self.processEvents()

    def testLocalChanges(self):
        self.waitForLoaded()

        with open(os.path.join(self.gitDir.name, "test.txt"), "w+") as f:
            f.write("test")

        Git.addFiles(repoDir=self.gitDir.name, files=["test.txt"])

        subRepoFile = os.path.join("subRepo", "test.py")
        with open(os.path.join(self.gitDir.name, subRepoFile), "a+") as f:
            f.write("# new line\n")

        logView = self.window.ui.gitViewA.ui.logView

        self.window.ui.leOpts.clear()
        QTest.keyClick(self.window.ui.leOpts, Qt.Key_Enter)
        self.wait(10000, logView.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(4, logView.getCount())
        self.assertEqual(Git.LCC_SHA1, logView.getCommit(0).sha1)

        self.assertEqual(2, self.window.ui.cbSubmodule.count())
        self.window.ui.cbSubmodule.setCurrentIndex(1)
        self.wait(10000, logView.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(3, logView.getCount())
        self.assertEqual(Git.LUC_SHA1, logView.getCommit(0).sha1)

        self.window.ui.acCompositeMode.trigger()
        self.wait(10000, logView.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(5, logView.getCount())
        self.assertEqual(Git.LUC_SHA1, logView.getCommit(0).sha1)
        self.assertEqual(Git.LCC_SHA1, logView.getCommit(1).sha1)

        diffView = self.window.ui.gitViewA.ui.diffView
        self.wait(1000, lambda: diffView.viewer._inReading)
        model = diffView.fileListModel
        self.assertEqual(model.rowCount(), 2)
        file: str = model.data(model.index(1, 0))
        self.assertTrue(file.endswith("subRepo/test.py"))

    def testInvalidFileFilter(self):
        self.waitForLoaded()

        logView = self.window.ui.gitViewA.ui.logView
        self.window.ui.leOpts.setText("-- invalidfile.txt")
        QTest.keyClick(self.window.ui.leOpts, Qt.Key_Enter)
        self.wait(1000, logView.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(0, logView.getCount())
        self.assertEqual(-1, logView.currentIndex())

        self.window.ui.leOpts.setText("-- invalidfile.py")
        QTest.keyClick(self.window.ui.leOpts, Qt.Key_Enter)
        self.wait(1000, logView.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(0, logView.getCount())
        self.assertEqual(-1, logView.currentIndex())
