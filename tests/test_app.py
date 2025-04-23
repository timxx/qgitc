# -*- coding: utf-8 -*-
from PySide6.QtTest import QTest, QSignalSpy
from qgitc.application import Application
from qgitc.gitutils import Git
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
