# -*- coding: utf-8 -*-

import os

from PySide6.QtCore import Signal

from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.common import fullRepoDir, logger
from qgitc.gitutils import Git
from qgitc.submoduleexecutor import SubmoduleExecutor


def _fetchStatusGit(submodule, cancelEvent: CancelEvent, showUntrackedFiles=True, showIgnoredFiles=False):
    repoDir = fullRepoDir(submodule)
    try:
        data = Git.status(repoDir, showUntrackedFiles, showIgnoredFiles)
        if not data:
            return None, None
    except Exception:
        logger.exception("Error fetching status for `%s`", repoDir)
        return None, None

    if cancelEvent.isSet():
        logger.debug(
            "Cancel event set, aborting status fetch for `%s`", repoDir)
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
        if status[0] == 'R' and i < len(lines):
            oldFile = lines[i].decode()
            oldRepoFile = os.path.normpath(os.path.join(
                submodule, oldFile) if submodule and submodule != '.' else oldFile)
            i += 1

        result.append((status, repoFile, oldRepoFile))

    logger.debug("Status fetch result for `%s`: %s", repoDir, result)

    return submodule, result


def _fetchStatusGit2(submodule, userData, cancelEvent: CancelEvent):
    import pygit2

    try:
        repoDir = fullRepoDir(submodule)
        repo = pygit2.Repository(repoDir)

        showUntrackedFiles, showIgnoredFiles = userData or (True, False)
        status = repo.status(untracked_files="all" if showUntrackedFiles else "no",
                            ignored=showIgnoredFiles)
    except Exception:
        return submodule, []

    result = []
    for file, flags in status.items():
        # bug in libgit2
        if flags == pygit2.GIT_STATUS_WT_DELETED and os.path.exists(os.path.join(repoDir, file)):
            continue

        repoFile = os.path.normpath(os.path.join(
            submodule, file) if submodule and submodule != '.' else file)

        status = ''
        # TODO: support renamed (repo.status doesn't support it, but libgit2 do support it)
        oldRepoFile = None

        if flags & pygit2.GIT_STATUS_INDEX_NEW:
            status = 'A'
        elif flags & pygit2.GIT_STATUS_INDEX_MODIFIED:
            status = 'M'
        elif flags & pygit2.GIT_STATUS_INDEX_DELETED:
            status = 'D'
        elif flags & pygit2.GIT_STATUS_INDEX_TYPECHANGE:
            status = 'T'
        elif flags & pygit2.GIT_STATUS_INDEX_RENAMED:
            status = 'R'
        else:
            status = ' '

        if flags & pygit2.GIT_STATUS_WT_NEW:
            # not add to index yet
            if status == ' ':
                status = '??'
            else:
                status += 'A'
        elif flags & pygit2.GIT_STATUS_WT_MODIFIED:
            status += 'M'
        elif flags & pygit2.GIT_STATUS_WT_DELETED:
            status += 'D'
        elif flags & pygit2.GIT_STATUS_WT_TYPECHANGE:
            status += 'T'
        else:
            status += ' '

        result.append((status, repoFile, oldRepoFile))

    return submodule, result


class StatusFetcher(SubmoduleExecutor):
    resultAvailable = Signal(str, list)
    branchInfoAvailable = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._delayedTask = []
        self._showUntrackedFiles = True
        self._showIgnoredFiles = False
        self._needCheckBranch = False
        self._span = None

    def fetch(self, submodules):
        self._needCheckBranch = len(submodules) > 1
        if Git.RUN_SLOW and len(submodules) > 50 and os.name == "nt":
            submoduleData = {}
            for submodule in submodules or [None]:
                submoduleData[submodule] = (self._showUntrackedFiles, self._showIgnoredFiles)
            self.submit(submoduleData, _fetchStatusGit2, self._onResultAvailable, False)
        else:
            self.submit(submodules, self._fetchStatus, self._onResultAvailable)
        logger.debug("Begin fetch submodules: %s", ",".join(
            submodules) if submodules else "None")

        self._span = ApplicationBase.instance().telemetry().startTrace("fetchStatus")
        self._span.addTag("sm_count", len(submodules))

    def cancel(self, force=False):
        super().cancel(force)
        # do not use clear, as we don't copy the list
        self._delayedTask = []
        if self._span:
            self._span.setStatus(False, "Cancelled")
            self._span.end()
            self._span = None

    def addTask(self, submodules):
        self._delayedTask.extend(submodules)

    def onFinished(self):
        self._thread = None
        if self._delayedTask:
            self.fetch(self._delayedTask)
        else:
            self.finished.emit()
        if self._span:
            self._span.setStatus(True)
            self._span.end()
            self._span = None

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
        return _fetchStatusGit(
            submodule, cancelEvent, self._showUntrackedFiles, self._showIgnoredFiles)
