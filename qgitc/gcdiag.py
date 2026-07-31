# -*- coding: utf-8 -*-

"""Opt-in detector for QObjects destroyed outside the GUI thread.

CPython's cyclic collector runs in whichever thread crosses an allocation
threshold, so a fetch worker can end up running ``~QObject`` for an object that
belongs to the GUI thread. Qt refuses to unregister that object's timers from a
foreign thread, the GUI event dispatcher keeps a timer whose receiver has been
freed, and the process dies on the next tick without any warning.

Setting ``QGITC_GC_DIAG=1`` turns on ``gc.DEBUG_SAVEALL``, which keeps every
cycle alive instead of freeing it: nothing is destroyed on the wrong thread, so
instead of crashing the offending objects are named in the log. Anything
reported here needs a parent or a deterministic deletion on the GUI thread.
"""

import gc
import os
import threading
import traceback

from PySide6.QtCore import QObject, QThread
from shiboken6 import Shiboken

from qgitc.common import logger

_installed = False
_garbageMark = 0


def install():
    global _installed
    if _installed or os.environ.get("QGITC_GC_DIAG") != "1":
        return

    _installed = True
    gc.set_debug(gc.DEBUG_SAVEALL)
    gc.callbacks.append(_onGcPhase)
    logger.warning(
        "GC diagnostics enabled: cyclic garbage is retained instead of being "
        "freed, cross-thread destruction is reported instead of crashing")


def _describe(obj: QObject):
    cls = type(obj)
    details = []

    try:
        objectName = obj.objectName()
        if objectName:
            details.append("objectName=%r" % objectName)
    except Exception:
        pass
    try:
        objThread = obj.thread()
        details.append("thread=%r" % (objThread.objectName() or objThread))
    except Exception:
        pass

    return "%s.%s(%s)" % (cls.__module__, cls.__qualname__, ", ".join(details))


def _isOwnedByPython(obj: QObject):
    try:
        return Shiboken.ownedByPython(obj)
    except Exception:
        return False


def _livesElsewhere(obj: QObject, currentThread: QThread):
    try:
        objThread = obj.thread()
    except Exception:
        return False
    return objThread is not None and objThread != currentThread


def _onGcPhase(phase: str, info: dict):
    global _garbageMark

    if phase == "start":
        _garbageMark = len(gc.garbage)
        return

    if threading.current_thread() is threading.main_thread():
        return

    collected = gc.garbage[_garbageMark:]
    qObjects = [o for o in collected if isinstance(o, QObject)]
    if not qObjects:
        return

    currentThread = QThread.currentThread()
    # Only objects Python owns are really destroyed by the collector; the rest
    # go down with their C++ parent, so the owned ones are the roots to fix.
    roots = [o for o in qObjects
             if _isOwnedByPython(o) and _livesElsewhere(o, currentThread)]
    if not roots:
        return

    histogram = {}
    for o in qObjects:
        key = type(o).__name__
        histogram[key] = histogram.get(key, 0) + 1

    logger.error(
        "Cross-thread destruction on thread %s: the cyclic GC reclaimed %d "
        "objects (%d QObject) and these Python-owned roots belong to another "
        "thread:\n%s\nWhole reclaimed tree: %s\nCollecting thread stack:\n%s",
        threading.current_thread().name, len(collected), len(qObjects),
        "\n".join("  " + _describe(o) for o in roots),
        histogram,
        "".join(traceback.format_stack()))
