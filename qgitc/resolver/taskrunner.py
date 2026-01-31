# -*- coding: utf-8 -*-

from __future__ import annotations

import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QTimer, Signal


class TaskResult(QObject):
    _deliver = Signal(bool, object, object)
    finished = Signal(bool, object, object)  # ok, result, error

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        # Ensure results are delivered on this object's thread.
        # Emitting `finished` directly from a worker thread can be flaky on some
        # PySide6/Python combos; routing through a queued connection is reliable.
        self._deliver.connect(self.finished)


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
        self._resultObj._deliver.emit(ok, out, err)


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
            self._pending.discard(ro)

        resultObj.finished.connect(_release, Qt.QueuedConnection)
        self._pool.start(_Runnable(resultObj, fn))
        return resultObj
