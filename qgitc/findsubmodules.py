# -*- coding: utf-8 -*-

import os
from PySide6.QtCore import QThread

from .gitutils import GitProcess


class FindSubmoduleThread(QThread):
    def __init__(self, repoDir, parent=None):
        super(FindSubmoduleThread, self).__init__(parent)

        self._repoDir = os.path.normcase(os.path.normpath(repoDir))
        self._submodules = []

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
        process = GitProcess(self._repoDir,
                             ["submodule", "foreach", "--quiet", "echo $name"],
                             True)
        data = process.communicate()[0]
        if self.isInterruptionRequested():
            return
        if process.returncode == 0 and data:
            self._submodules = data.rstrip().split('\n')
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
