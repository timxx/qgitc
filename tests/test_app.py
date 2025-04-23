# -*- coding: utf-8 -*-
from qgitc.application import Application
from PySide6.QtTest import QTest

import sys
import unittest


class TestApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(sys.argv)

    @classmethod
    def tearDownClass(cls):
        cls.processEvents(cls)
        cls.app.quit()
        del cls.app

    def processEvents(self):
        self.app.sendPostedEvents()
        self.app.processEvents()

    def testRepoName(self):
        name = self.app.repoName()
        self.assertEqual(name, "qgitc.git")

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
