# -*- coding: utf-8 -*-

import os

from PySide6.QtCore import QEventLoop, QProcess, QThread

from qgitc.common import logger
from qgitc.gitutils import GitProcess


class FindSubmoduleThread(QThread):
    def __init__(self, repoDir, parent=None):
        super(FindSubmoduleThread, self).__init__(parent)

        self.setRepoDir(repoDir)
        self._submodules = []
        self._eventLoop = None

    def setRepoDir(self, repoDir):
        self._repoDir = os.path.normcase(os.path.normpath(repoDir))

    @property
    def submodules(self):
        if self.isFinished() and not self.isInterruptionRequested():
            return self._submodules
        return []

    def run(self):
        self._submodules.clear()
        if self.isInterruptionRequested():
            return

        # try git submodule first
        self._eventLoop = QEventLoop()
        process = QProcess()
        process.setWorkingDirectory(self._repoDir)
        process.finished.connect(self._eventLoop.quit)
        args = ["submodule", "foreach", "--quiet", "echo $name"]
        process.start(GitProcess.GIT_BIN, args)
        self._eventLoop.exec()

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
            if os.path.normcase(root) == self._repoDir:
                continue

            if ".git" in subdirs or ".git" in files:
                dir = root.replace(self._repoDir + os.sep, "")
                if dir:
                    submodules.append(dir)

            if root.count(os.path.sep) >= max_level or root.endswith(".git"):
                del subdirs[:]
            else:
                # ignore all '.dir'
                subdirs[:] = [d for d in subdirs if not d.startswith(".")]

        if submodules:
            submodules.insert(0, '.')

        self._submodules = submodules

    def requestInterruption(self):
        super().requestInterruption()
        if self._eventLoop:
            self._eventLoop.quit()
