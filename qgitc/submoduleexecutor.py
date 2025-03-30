# -*- coding: utf-8 -*-

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from typing import Callable
from PySide6.QtCore import QThread, QObject, Signal


class SubmoduleThread(QThread):

    def __init__(self, submodules, parent=None):
        super().__init__(parent)

        self._submodules = submodules
        self._actionHandler: Callable[[str], any] = None
        self._resultHandler: Callable[[any], any] = None

    def setActionHandler(self, action: Callable):
        """ Set the action to be performed on each submodule.
        The action should be a callable that takes a submodule path as an argument."""
        self._actionHandler = action

    def setResultHandler(self, resultHandler: Callable):
        """ Set the result handler to process the result of the action. """
        self._resultHandler = resultHandler

    def processSubmodule(self, submodule: str):
        """ Override this method or @setAction to do the work """
        if self._actionHandler:
            return self._actionHandler(submodule)
        return None

    def onResultAvailable(self, *args):
        """ Override this method to handle the result of the action """
        if self._resultHandler:
            self._resultHandler(*args)

    def run(self):
        if self.isInterruptionRequested():
            return

        submodules = self._submodules or [None]
        if len(submodules) == 1:
            result = self.processSubmodule(submodules[0])
            if not self.isInterruptionRequested():
                if isinstance(result, tuple):
                    self.onResultAvailable(*result)
                else:
                    self.onResultAvailable(result)
        else:
            max_workers = max(2, os.cpu_count() - 2)
            executor = ThreadPoolExecutor(max_workers=max_workers)
            tasks = [executor.submit(self.processSubmodule, submodule)
                     for submodule in submodules]

            for task in as_completed(tasks):
                if self.isInterruptionRequested():
                    return
                result = task.result()
                if isinstance(result, tuple):
                    self.onResultAvailable(*result)
                else:
                    self.onResultAvailable(result)


class SubmoduleExecutor(QObject):
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: SubmoduleThread = None

    def __del__(self):
        self.cancel()

    def submit(self, submodules, actionHandler: Callable, resultHandler: Callable = None):
        """ Submit a list of submodules and an action to be performed on each submodule.
         The action should be a callable that takes a submodule path as an argument.
         The result handler should be a callable that takes the result of the action."""

        self.cancel()
        self._thread = SubmoduleThread(submodules, self)
        self._thread.setActionHandler(actionHandler)
        self._thread.setResultHandler(resultHandler)
        self._thread.finished.connect(self.onFinished)
        self._thread.start()

    def cancel(self):
        if self._thread:
            self._thread.requestInterruption()
            self._thread.wait(50)
            self._thread = None

    def isRunning(self):
        return self._thread is not None and self._thread.isRunning()

    def onFinished(self):
        self._thread = None
        self.finished.emit()
