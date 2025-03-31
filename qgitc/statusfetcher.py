# -*- coding: utf-8 -*-

import os
from PySide6.QtCore import Signal

from .gitutils import Git
from .submoduleexecutor import SubmoduleExecutor


def _fetchStatus(repoDir, userData=None):
    if not repoDir or repoDir == '.':
        fullRepoDir = Git.REPO_DIR
    else:
        fullRepoDir = os.path.join(Git.REPO_DIR, repoDir)

    try:
        data = Git.status(fullRepoDir)
        if not data:
            return None, None
    except Exception:
        return None, None

    lines = data.rstrip(b'\0').split(b'\0')
    result = []
    for line in lines:
        assert (len(line) > 3)
        status = line[:2].decode()
        file = line[3:].decode()
        repoFile = os.path.join(
            repoDir, file) if repoDir and repoDir != '.' else file
        result.append((status, os.path.normpath(repoFile)))
    return repoDir, result


class StatusFetcher(SubmoduleExecutor):
    resultAvailable = Signal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._delayedTask = []

    def fetch(self, submodules):
        self.submit(submodules, _fetchStatus, self._onResultAvailable)

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
