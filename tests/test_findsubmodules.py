# -*- coding: utf-8 -*-
from qgitc.findsubmodules import FindSubmoduleThread
from qgitc.gitutils import GitProcess
from tests.base import TestBase


class TestFindSubmoduleThread(TestBase):

    def createSubRepo(self):
        return True

    def testStartFailureFallsBackToFileWalk(self):
        """A failed process start must not hang the thread forever.

        QProcess emits errorOccurred (never finished) when the program
        cannot be started; without quitting the wait on it, the thread
        blocks until interrupted and submodules are never discovered
        (e.g. broken git binary).
        """
        oldBin = GitProcess.GIT_BIN
        GitProcess.GIT_BIN = "definitely-not-a-git-binary.exe"
        try:
            thread = FindSubmoduleThread(self.gitDir.name)
            thread.start()
            self.wait(5000, thread.isRunning)
        finally:
            GitProcess.GIT_BIN = oldBin

        self.assertFalse(thread.isRunning())
        self.assertIn("subRepo", thread.submodules)

    def testQtObjectsSurviveUntilReleasedFromGuiThread(self):
        """run() must not drop the Qt objects it created.

        Destroying a QObject in the worker thread takes a Qt lock and then
        needs the Python GIL (Shiboken::GilState), while the GUI thread holds
        the GIL and waits for that same lock: the process freezes forever and
        even the test watchdog cannot fire. The process is therefore retained
        on the thread and only dropped by releaseProcessors(), which the GUI
        thread calls after the thread has finished.
        """
        thread = FindSubmoduleThread(self.gitDir.name)
        thread.start()
        self.wait(5000, thread.isRunning)

        self.assertFalse(thread.isRunning())
        self.assertIsNotNone(thread._process)
        self.assertTrue(thread.submodules)

        thread.releaseProcessors()
        self.assertIsNone(thread._process)
