# -*- coding: utf-8 -*-
from PySide6.QtTest import QTest
from qgitc.application import Application
from tests.base import TestBase


class TestApp(TestBase):
    def testRepoName(self):
        name = self.app.repoName()
        self.assertIn(name, ["qgitc.git", "qgitc"])

    def testLocale(self):
        lang = self.app.uiLanguage()
        self.assertTrue(len(lang) > 0)

    def testWindows(self):
        winTypes = [
            Application.LogWindow,
            Application.BlameWindow,
            Application.AiAssistant,
            Application.CommitWindow,
        ]

        for winType in winTypes:
            window = self.app.getWindow(winType)
            self.assertIsNotNone(window)
            window.show()
            self.processEvents()

            QTest.qWaitForWindowExposed(window)
            self.processEvents()

            self.assertTrue(window.isVisible())
            window.close()

            self.processEvents()
