# -*- coding: utf-8 -*-

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Union

from PySide6.QtCore import QObject, QThread, Signal

from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.common import logger


class SubmoduleThread(QThread):

    def __init__(self, submodules: Union[list, dict], parent=None):
        super().__init__(parent)

        self._submodules = submodules
        self._actionHandler: Callable[[str, any, CancelEvent], any] = None
        self._resultHandler: Callable[[any], any] = None
        self._cancellation = CancelEvent(self)

    def setActionHandler(self, action: Callable):
        """ Set the action to be performed on each submodule.
        The action should be a callable that takes a a submodule path as an argument,
        and optionally additional data.
        The action can be cancelled if the CancelEvent is set."""
        self._actionHandler = action

    def actionHandler(self):
        return self._actionHandler

    def setResultHandler(self, resultHandler: Callable):
        """ Set the result handler to process the result of the action. """
        self._resultHandler = resultHandler

    def processSubmodule(self, submodule: str, userData: any = None):
        """ Process a single submodule in background thread.
        The action handler is called with the submodule path as an argument.
        The result of the action is passed to the result handler."""
        if self.isInterruptionRequested():
            return None

        if self._actionHandler:
            return self._actionHandler(submodule, userData, self._cancellation)
        return None

    def onResultAvailable(self, *args):
        """ Override this method to handle the result of the action """
        if self._resultHandler:
            self._resultHandler(*args)

    def run(self):
        if self.isInterruptionRequested():
            return

        if isinstance(self._submodules, dict):
            submodules = list(self._submodules.keys())
            hasData = True
        else:
            submodules = self._submodules or [None]
            hasData = False

        if len(submodules) == 1:
            data = self._submodules[submodules[0]] if hasData else None
            result = self.processSubmodule(submodules[0], data)
            if not self.isInterruptionRequested():
                if isinstance(result, tuple):
                    self.onResultAvailable(*result)
                else:
                    self.onResultAvailable(result)
        else:
            max_workers = max(2, os.cpu_count() - 2)
            executor = ThreadPoolExecutor(max_workers=max_workers)
            tasks = [executor.submit(self.processSubmodule, submodule, self._submodules[submodule]
                                     if hasData else None) for submodule in submodules]

            while tasks and not self.isInterruptionRequested():
                try:
                    for task in as_completed(tasks, 0.01):
                        if self.isInterruptionRequested():
                            logger.debug("Submodule executor cancelled")
                            executor.shutdown(wait=False, cancel_futures=True)
                            return
                        tasks.remove(task)
                        result = task.result()
                        if isinstance(result, tuple):
                            self.onResultAvailable(*result)
                        else:
                            self.onResultAvailable(result)
                except Exception:
                    pass
            if self.isInterruptionRequested():
                logger.debug("Submodule executor cancelled")
                executor.shutdown(wait=False, cancel_futures=True)


class SubmoduleExecutor(QObject):
    started = Signal()
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: SubmoduleThread = None
        self._threads = []

    def submit(self, submodules: Union[list, dict], actionHandler: Callable, resultHandler: Callable = None):
        """ Submit a list of submodules and an action to be performed on each submodule.
        Submodules can be a list or a dictionary of submodule paths.
        The action should be a callable that takes a submodule path as an argument, and optionally additional data.
        The result handler is called with the result of the action."""

        self.cancel()
        self._thread = SubmoduleThread(submodules, self)
        self._thread.setActionHandler(actionHandler)
        self._thread.setResultHandler(resultHandler)
        self._thread.finished.connect(self.onFinished)
        self._thread.finished.connect(self._onThreadFinished)
        self._thread.started.connect(self.started)
        self._threads.append(self._thread)
        self._thread.start()

    def cancel(self, force=False):
        if self._thread and self._thread.isRunning():
            logger.info("cancelling submodule thread")
            self._thread.finished.disconnect(self.onFinished)
            self._thread.started.disconnect(self.started)
            self._thread.requestInterruption()

            if force:
                self._threads.remove(self._thread)
                self._thread.finished.disconnect(self._onThreadFinished)
                self._terminateThread(self._thread)
            self._thread = None

        if not force:
            return

        for thread in self._threads:
            thread.finished.disconnect(self._onThreadFinished)
            self._terminateThread(thread)
        self._threads.clear()

    def isRunning(self):
        return self._thread is not None and self._thread.isRunning()

    def onFinished(self):
        self._thread = None
        self.finished.emit()

    def _onThreadFinished(self):
        thread = self.sender()
        if thread in self._threads:
            self._threads.remove(thread)

    def _terminateThread(self, thread: SubmoduleThread):
        if ApplicationBase.instance().terminateThread(thread):
            handler = thread.actionHandler()
            handlerName = handler.__name__ if handler else "<None>"
            logger.warning("Terminated submodule thread (%s)", handlerName)
