# -*- coding: utf-8 -*-

from PySide6.QtCore import QThread


class CancelEvent:

    def __init__(self, thread: QThread):
        self._thread = thread

    def isSet(self):
        return self._thread.isInterruptionRequested()
