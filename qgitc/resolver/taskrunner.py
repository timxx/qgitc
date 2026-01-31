# -*- coding: utf-8 -*-

from __future__ import annotations

import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QTimer, Signal


class TaskResult(QObject):
    finished = Signal(bool, object, object)  # ok, result, error


class _Runnable(QRunnable):

    def __init__(self, resultObj: TaskResult, fn: Callable[[], Any]):
        super().__init__()
        self._resultObj = resultObj
        self._fn = fn

    def run(self):
        try:
            out = self._fn()
            self._emit(True, out, None)
        except Exception:
            err = traceback.format_exc()
            self._emit(False, None, err)

    def _emit(self, ok, out, err):
        QTimer.singleShot(0, self._resultObj,
                          lambda: self._resultObj.finished.emit(ok, out, err))


class TaskRunner(QObject):

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._pending: set[TaskResult] = set()

    def run(self, fn: Callable[[], Any]) -> TaskResult:
        resultObj = TaskResult()
        # Keep TaskResult alive until its finished signal is delivered.
        # Otherwise, the object can be garbage-collected and queued signals may be dropped.
        self._pending.add(resultObj)

        def _release(ok: bool, result: object, error: object, ro: TaskResult = resultObj):
            # Defer cleanup to the next turn of the event loop so any other queued
            # receivers (e.g. QSignalSpy) see the signal before we drop our last refs.
            QTimer.singleShot(0, ro, lambda: self._pending.discard(ro))

        resultObj.finished.connect(_release)
        self._pool.start(_Runnable(resultObj, fn))
        return resultObj
