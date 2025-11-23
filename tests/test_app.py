# -*- coding: utf-8 -*-
import os
from unittest.mock import patch

from PySide6.QtTest import QSignalSpy, QTest

from qgitc.gitutils import Git, GitProcess
from qgitc.windowtype import WindowType
from tests.base import TemporaryDirectory, TestBase


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
            WindowType.BranchCompareWindow,
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

        if self.app._findSubmoduleThread and self.app._findSubmoduleThread.isRunning():
            self.app._findSubmoduleThread.requestInterruption()
            self.app._findSubmoduleThread.wait()


class TestAppNoRepo(TestBase):
    def doCreateRepo(self):
        self.gitDir = TemporaryDirectory()
        self.submoduleDir = None

    def testNoRepo(self):
        os.chdir(self.gitDir.name)
        with patch.object(self.app, "_findSubmodules", return_value=None) as mock:
            self.app._initGit(GitProcess.GIT_BIN)
            self.assertIsNone(Git.REPO_DIR)
            name = self.app.repoName()
            self.assertEqual(len(name), 0)
            mock.assert_not_called()
