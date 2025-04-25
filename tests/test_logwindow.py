# -*- coding: utf-8 -*-
import os
from PySide6.QtTest import QTest, QSignalSpy
from qgitc.application import Application
from tests.base import TestBase


class TestLogWindow(TestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.window = cls.app.getWindow(Application.LogWindow)

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        super().tearDownClass()

    def testReloadRepo(self):
        logview = self.window.ui.gitViewA.logView
        spyFetcher = QSignalSpy(logview.fetcher.fetchFinished)

        self.window.show()
        QTest.qWaitForWindowExposed(self.window)
        self.assertTrue(spyFetcher.wait(3000))

        self.assertEqual(1, spyFetcher.count())

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
