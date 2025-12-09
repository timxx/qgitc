# -*- coding: utf-8 -*-

import os
import time
from typing import List

from PySide6.QtCore import QObject, QThread, Signal

from qgitc.applicationbase import ApplicationBase
from qgitc.common import Commit, logger
from qgitc.gitutils import Git
from qgitc.logsfetcherqprocessworker import LogsFetcherQProcessWorker
from qgitc.logsfetcherworkerbase import LogsFetcherWorkerBase


class LogsFetcher(QObject):

    localChangesAvailable = Signal(Commit, Commit)
    logsAvailable = Signal(list)
    fetchFinished = Signal(int)
    fetchTooSlow = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: LogsFetcherWorkerBase = None
        self._thread: QThread = None
        self._submodules: List[str] = []
        self._errorData = b''
        self._threads: List[QThread] = []
        self._beginTime = None

    def setSubmodules(self, submodules: List[str]):
        self._submodules = submodules

    def fetch(self, *args, branchDir=None):
        self.cancel()
        self._errorData = b''
        # always detect local changes for single repo
        noLocalChanges = len(self._submodules) > 0 and not ApplicationBase.instance(
        ).settings().detectLocalChanges()

        if Git.RUN_SLOW and len(self._submodules) > 50 and os.name == "nt":
            from qgitc.logsfetchergitworker import LogsFetcherGitWorker
            if LogsFetcherGitWorker.isSupportFilterArgs(args[1]):
                self._worker = LogsFetcherGitWorker(
                    self._submodules, branchDir, noLocalChanges, *args)
        if not self._worker:
            self._worker = LogsFetcherQProcessWorker(
                self._submodules, branchDir, noLocalChanges, *args)
        self._worker.logsAvailable.connect(self._onLogsAvailable)
        self._worker.fetchFinished.connect(self._onFetchFinished)
        self._worker.localChangesAvailable.connect(
            self._onLocalChangesAvailable)

        self._thread = QThread()
        self._thread.finished.connect(self._onThreadFinished)
        self._thread.started.connect(self._worker.run)
        self._worker.moveToThread(self._thread)
        self._thread.start()

        self._threads.append(self._thread)
        if self._worker.needReportSlowFetch():
            self._beginTime = time.time()

    def cancel(self, force=False):
        if self._worker:
            self._worker.logsAvailable.disconnect(self._onLogsAvailable)
            self._worker.fetchFinished.disconnect(self._onFetchFinished)
            self._worker.localChangesAvailable.disconnect(
                self._onLocalChangesAvailable)
            self._worker.requestInterruption()
            self._worker.deleteLater()
            self._worker = None

        if self._thread and self._thread.isRunning():
            self._thread.quit()

            if force and ApplicationBase.instance().terminateThread(self._thread):
                self._threads.remove(self._thread)
                self._thread.finished.disconnect(self._onThreadFinished)
                logger.warning("Terminating logs fetcher thread")
                self._thread = None

        if not force:
            return

        for thread in self._threads:
            thread.finished.disconnect(self._onThreadFinished)
            ApplicationBase.instance().terminateThread(thread)
        self._threads.clear()

    def isLoading(self):
        return self._thread is not None and \
            self._thread.isRunning()

    def _onLogsAvailable(self, logs: List[Commit]):
        worker = self.sender()
        if worker == self._worker:
            self.logsAvailable.emit(logs)
        else:
            logger.info("_onLogsAvailable but thread changed")

    def _onFetchFinished(self, exitCode):
        worker: LogsFetcherWorkerBase = self.sender()
        if not worker:
            return

        if worker == self._worker:
            report = worker.needReportSlowFetch()
            self._thread.quit()
            self._errorData = self._worker.errorData
            self._worker = None
            self.fetchFinished.emit(exitCode)
            if report:
                seconds = int(time.time() - self._beginTime)
                if seconds > 15:
                    self.fetchTooSlow.emit(seconds)
        else:
            logger.info("_onFetchFinished but thread changed")

    def _onLocalChangesAvailable(self, lccCommit: Commit, lucCommit: Commit):
        worker = self.sender()
        if worker == self._worker:
            self.localChangesAvailable.emit(lccCommit, lucCommit)
        else:
            logger.info("_onLocalChangesAvailable but thread changed")

    def _onThreadFinished(self):
        thread = self.sender()
        if thread in self._threads:
            self._threads.remove(thread)

    @property
    def errorData(self):
        return self._errorData
