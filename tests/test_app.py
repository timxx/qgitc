# -*- coding: utf-8 -*-
from PySide6.QtTest import QSignalSpy, QTest

from qgitc.gitutils import Git
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestApp(TestBase):
    def testRepoName(self):
        name = self.app.repoName()
        self.assertEqual(name, "test.git")

    def testLocale(self):
        lang = self.app.uiLanguage()
        self.assertTrue(len(lang) > 0)

    def testWindows(self):
        winTypes = [
            WindowType.LogWindow,
            WindowType.BlameWindow,
            WindowType.AiAssistant,
            WindowType.CommitWindow,
        ]

        for winType in winTypes:
            window = self.app.getWindow(winType)
            self.assertIsNotNone(window)
            window.show()
            self.processEvents()

            QTest.qWaitForWindowExposed(window)
            self.processEvents()

            self.assertTrue(window.isVisible())
            spyDestroyed = QSignalSpy(window.destroyed)
            window.close()
            self.processEvents()
            self.assertEqual(spyDestroyed.count(), 1)

            self.processEvents()

    def testUpdateRepo(self):
        oldRepoDir = Git.REPO_DIR
        self.assertIsNotNone(Git.REPO_DIR)

        spy = QSignalSpy(self.app.repoDirChanged)
        self.app.updateRepoDir(None)
        self.assertEqual(spy.count(), 1)
        self.assertIsNone(Git.REPO_DIR)

        self.app.updateRepoDir(oldRepoDir)
        self.assertEqual(spy.count(), 2)
        self.assertEqual(Git.REPO_DIR, oldRepoDir)

        self.app.updateRepoDir(oldRepoDir)
        self.assertEqual(spy.count(), 2)
