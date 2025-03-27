# -*- coding: utf-8 -*-

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from PySide6.QtCore import QThread, QObject, Signal

from qgitc.gitutils import Git


class FetchStatusThread(QThread):
    # repoDir, list[(statusCode, file)]
    resultAvailable = Signal(str, list)

    def __init__(self, submodules, parent=None):
        super().__init__(parent)

        self._submodules = submodules
        self._fetchers = []

    def run(self):
        if self.isInterruptionRequested():
            return

        submodules = self._submodules or [None]
        if len(submodules) == 1:
            repoDir, status = self._fetch(submodules[0])
            if status and not self.isInterruptionRequested():
                self.resultAvailable.emit(repoDir, status)
        else:
            max_workers = max(2, os.cpu_count() - 2)
            executor = ThreadPoolExecutor(max_workers=max_workers)
            tasks = [executor.submit(self._fetch, submodule)
                     for submodule in submodules]

            for task in as_completed(tasks):
                if self.isInterruptionRequested():
                    return
                repoDir, status = task.result()
                if status:
                    self.resultAvailable.emit(repoDir, status)

    def _fetch(self, repoDir):
        if self.isInterruptionRequested():
            return None, None

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
            file = line[4:].decode()
            repoFile = os.path.normpath(os.path.join(
                repoDir, file)) if repoDir and repoDir != '.' else file
            result.append((status, repoFile))
        return repoDir, result


class StatusFetcher(QObject):
    resultAvailable = Signal(str, list)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: FetchStatusThread = None

    def __del__(self):
        self.cancel()

    def fetch(self, submodules):
        self.cancel()
        self._thread = FetchStatusThread(submodules, self)
        self._thread.resultAvailable.connect(self.resultAvailable)
        self._thread.finished.connect(self._onFinished)
        self._thread.start()

    def cancel(self):
        if self._thread:
            self._thread.requestInterruption()
            self._thread.wait(50)
            self._thread = None

    def _onFinished(self):
        self._thread = None
        self.finished.emit()
