# -*- coding: utf-8 -*-

import os

from PySide6.QtCore import Signal

from qgitc.cancelevent import CancelEvent
from qgitc.common import fullRepoDir, logger
from qgitc.gitutils import Git
from qgitc.submoduleexecutor import SubmoduleExecutor


class StatusFetcher(SubmoduleExecutor):
    resultAvailable = Signal(str, list)
    branchInfoAvailable = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._delayedTask = []
        self._showUntrackedFiles = True
        self._showIgnoredFiles = False
        self._needCheckBranch = False

    def fetch(self, submodules):
        self._needCheckBranch = len(submodules) > 1
        self.submit(submodules, self._fetchStatus, self._onResultAvailable)
        logger.debug("Begin fetch submodules: %s", ",".join(
            submodules) if submodules else "None")

    def cancel(self, force=False):
        super().cancel(force)
        # do not use clear, as we don't copy the list
        self._delayedTask = []

    def addTask(self, submodules):
        self._delayedTask.extend(submodules)

    def onFinished(self):
        self._thread = None
        if self._delayedTask:
            self.fetch(self._delayedTask)
        else:
            self.finished.emit()

    def _onResultAvailable(self, repoDir, result):
        if not result:
            return
        self.resultAvailable.emit(repoDir, result)

        if self._needCheckBranch:
            branch = Git.activeBranch(fullRepoDir(repoDir))
            self.branchInfoAvailable.emit(repoDir, branch)

    def setShowUntrackedFiles(self, showUntrackedFiles: bool):
        self._showUntrackedFiles = showUntrackedFiles

    def setShowIgnoredFiles(self, showIgnoredFiles: bool):
        self._showIgnoredFiles = showIgnoredFiles

    def fetchStatus(self, submodule, cancelEvent: CancelEvent):
        _, result = self._fetchStatus(submodule, None, cancelEvent)
        if result:
            self.resultAvailable.emit(submodule, result)

    def _fetchStatus(self, submodule, userData, cancelEvent: CancelEvent):
        repoDir = fullRepoDir(submodule)
        try:
            data = Git.status(
                repoDir, self._showUntrackedFiles, self._showIgnoredFiles)
            if not data:
                return None, None
        except Exception:
            logger.exception("Error fetching status for `%s`", repoDir)
            return None, None

        if cancelEvent.isSet():
            logger.debug("Cancel event set, aborting status fetch for `%s`", repoDir)
            return None, None

        lines = data.rstrip(b'\0').split(b'\0')
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1

            assert (len(line) > 3)
            if line[2] != 32:
                logger.warning("Unexpected status line `%s`", line.decode())
                continue

            status = line[:2].decode()
            file = line[3:].decode()
            repoFile = os.path.normpath(os.path.join(
                submodule, file) if submodule and submodule != '.' else file)

            oldRepoFile = None
            # rename followed by old name
            if status[0] == 'R' and i + 1 < len(lines):
                oldFile = lines[i].decode()
                oldRepoFile = os.path.normpath(os.path.join(
                    submodule, oldFile) if submodule and submodule != '.' else oldFile)
                i += 1

            result.append((status, repoFile, oldRepoFile))

        logger.debug("Status fetch result for `%s`: %s", repoDir, result)

        return submodule, result
