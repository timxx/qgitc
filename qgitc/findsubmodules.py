# -*- coding: utf-8 -*-

import os

from PySide6.QtCore import QProcess, QThread
from shiboken6 import Shiboken

from qgitc.common import logger
from qgitc.gitutils import Git, GitProcess


class FindSubmoduleThread(QThread):
    BUILD_DIR_NAMES = {"build", "debug", "release"}

    def __init__(self, repoDir, parent=None):
        super(FindSubmoduleThread, self).__init__(parent)

        self.setRepoDir(repoDir)
        self._submodules = []
        # Qt objects created in run() are retained here instead of being
        # dropped inside the worker thread: destroying a QObject there takes a
        # Qt lock and then needs the Python GIL (Shiboken::GilState), while the
        # GUI thread holds the GIL and waits for that very lock — the whole
        # process freezes until the GIL is released, which never happens.
        # releaseProcessors() drops them from the GUI thread once the thread
        # has finished.
        self._process = None

    def setRepoDir(self, repoDir):
        self._repoDir = os.path.normcase(os.path.normpath(repoDir))

    @property
    def submodules(self):
        if self.isFinished() and not self.isInterruptionRequested():
            return self._submodules
        return []

    def _isIgnoredPath(self, relPath):
        if not relPath:
            return False

        relPath = relPath.replace("\\", "/")
        data = Git.checkOutput(["check-ignore", "--", relPath],
                               text=True, repoDir=self._repoDir)
        return bool(data and data.strip())

    def _isBuildDirPath(self, relPath):
        if not relPath:
            return False

        parts = [p.lower() for p in relPath.replace("\\", "/").split("/") if p]
        return any(
            part.startswith(name) or part.endswith(name)
            for part in parts
            for name in self.BUILD_DIR_NAMES
        )

    def _filterIgnoredSubdirs(self, root, subdirs):
        if not subdirs:
            return []

        relRoot = os.path.relpath(root, self._repoDir)
        if relRoot == ".":
            relRoot = ""

        filteredSubdirs = []
        for subdir in subdirs:
            relPath = subdir if not relRoot else os.path.join(relRoot, subdir)
            if self._isBuildDirPath(relPath) and self._isIgnoredPath(relPath):
                continue
            filteredSubdirs.append(subdir)
        return filteredSubdirs

    def run(self):
        self._submodules.clear()
        if self.isInterruptionRequested():
            return

        # try git submodule first
        process = QProcess()
        # Retain the process on the instance: run() must not destroy any Qt
        # object in this worker thread (see __init__).
        self._process = process
        process.setWorkingDirectory(self._repoDir)
        args = ["submodule", "foreach", "--quiet", "echo $name"]
        process.start(GitProcess.GIT_BIN, args)
        # Wait on the process state instead of a nested QEventLoop with
        # finished/errorOccurred connections: both the loop and the
        # connections live in this thread, and tearing them down deadlocks
        # against the GUI thread. waitForFinished() needs no event loop, and a
        # failed start simply never reaches Running, so the file walk below
        # still discovers the submodules (e.g. broken git binary).
        if process.state() == QProcess.ProcessState.Starting:
            process.waitForStarted(1000)
        while process.state() == QProcess.ProcessState.Running:
            if process.waitForFinished(50):
                break
            if self.isInterruptionRequested():
                break

        if not Shiboken.isValid(process):
            # The interpreter is tearing down and already destroyed the
            # underlying C++ object; bail out without touching it.
            return

        if self.isInterruptionRequested():
            if process.state() == QProcess.ProcessState.Running:
                process.close()
                process.waitForFinished(50)
                if process.state() == QProcess.ProcessState.Running:
                    process.kill()
                    logger.warning("Kill find submodule process")
            return

        if process.exitCode() == 0:
            data = process.readAll().data()
            if data:
                self._submodules = data.decode("utf-8").rstrip().split('\n')
                self._submodules.insert(0, ".")
                return

        submodules = []
        # some projects may not use submodule or subtree
        max_level = 5 + self._repoDir.count(os.path.sep)
        for root, subdirs, files in os.walk(self._repoDir, topdown=True):
            if self.isInterruptionRequested():
                return
            isRepoRoot = os.path.normcase(root) == self._repoDir

            if not isRepoRoot and (".git" in subdirs or ".git" in files):
                directory = root.replace(self._repoDir + os.sep, "")
                if directory and Git.isRepoRoot(root):
                    submodules.append(directory)

            if root.count(os.path.sep) >= max_level or root.endswith(".git"):
                del subdirs[:]
            else:
                # ignore all '.dir'
                visibleSubdirs = [d for d in subdirs if not d.startswith(".")]
                subdirs[:] = self._filterIgnoredSubdirs(root, visibleSubdirs)

        if submodules:
            submodules.insert(0, '.')

        self._submodules = submodules

    def requestInterruption(self):
        # run()'s wait polls isInterruptionRequested() every 50ms, so no
        # cross-thread Qt call is needed to wake it up.
        super().requestInterruption()

    def releaseProcessors(self):
        """Drop the Qt objects created by run().

        Must run in the GUI thread and only after this thread has finished;
        that keeps their destruction out of the worker thread, where it would
        deadlock against the GUI thread (see __init__).
        """
        self._process = None
