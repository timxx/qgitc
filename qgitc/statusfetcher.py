# -*- coding: utf-8 -*-

import os
from PySide6.QtCore import Signal

from .cancelevent import CancelEvent
from .common import fullRepoDir, logger
from .gitutils import Git
from .submoduleexecutor import SubmoduleExecutor


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

    def cancel(self):
        super().cancel()
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
        for line in lines:
            assert (len(line) > 3)
            status = line[:2].decode()
            file = line[3:].decode()
            repoFile = os.path.join(
                submodule, file) if submodule and submodule != '.' else file
            result.append((status, os.path.normpath(repoFile)))

        logger.debug("Status fetch result for `%s`: %s", repoDir, result)

        return submodule, result
