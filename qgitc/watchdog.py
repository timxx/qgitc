# -*- coding: utf-8 -*-

import sys
import threading
import traceback

from PySide6.QtCore import QEvent, QObject, QThread, QTimer

from qgitc.applicationbase import ApplicationBase
from qgitc.common import logger


class CheckMainAliveEvent(QEvent):

    Type = QEvent.User + 1

    def __init__(self):
        super().__init__(QEvent.Type(CheckMainAliveEvent.Type))


class WatchdogWorker(QObject):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._isMainThreadAlive = True
        self._timer: QTimer = None
        self._report = False
        self._lock = threading.Lock()
        self._requestStop = False

    def start(self):
        with self._lock:
            if self._requestStop:
                return
            self._requestStop = False
            self._timer = QTimer(self)
            self._timer.setInterval(6000)
            self._timer.timeout.connect(self._checkMainThreadAlive)
            self._timer.start()

    def stop(self):
        with self._lock:
            self._requestStop = True
            if not self._timer:
                return
            self._timer.deleteLater()
            self._timer = None

    def notifyMainThreadAlive(self):
        self._isMainThreadAlive = True
        self._report = False

    def _checkMainThreadAlive(self):
        if self._isMainThreadAlive:
            self._isMainThreadAlive = False
            return

        if self._report:
            return

        self._report = True
        main_thread = threading.main_thread()
        frames = sys._current_frames()
        main_frame = frames.get(main_thread.ident)
        if main_frame:
            stack = traceback.format_stack(main_frame)
            logger.error(
                f"Main thread hanging stack trace:\n{''.join(stack)}")
        else:
            logger.error("Main thread is not responding!")

    def event(self, event: QEvent) -> bool:
        if event.type() == CheckMainAliveEvent.Type:
            self.notifyMainThreadAlive()
            return True
        return super().event(event)


class Watchdog(QObject):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._uiTimer: QTimer = None
        self._worker: WatchdogWorker = None
        self._thread: QThread = None

    def start(self):
        if self._worker:
            return

        self._thread = QThread()

        self._worker = WatchdogWorker()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.start)
        self._thread.start()

        self._uiTimer = QTimer(self)
        self._uiTimer.setInterval(5000)
        self._uiTimer.timeout.connect(self.notifyMainThreadAlive)
        self._uiTimer.start()

    def stop(self):
        if self._worker:
            self._worker.stop()
            self._worker.deleteLater()

        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None

        self._worker = None

        if self._uiTimer:
            self._uiTimer.stop()
            self._uiTimer = None

    def notifyMainThreadAlive(self):
        if not self._worker:
            return
        ApplicationBase.instance().postEvent(
            self._worker, CheckMainAliveEvent())
