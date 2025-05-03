# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QMessageBox
from qgitc.application import Application
from qgitc.gitutils import Git
from tests.base import TestBase
from unittest.mock import patch


class TestLogWindow(TestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.window = cls.app.getWindow(Application.LogWindow)
        # reduce logs to load to speed up tests
        cls.window.ui.leOpts.setText("-n50")
        QTest.keyClick(cls.window.ui.leOpts, Qt.Key_Enter)

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        super().tearDownClass()

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

            while logview.fetcher.isLoading():
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
