# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import (
    QCoreApplication,
    QThread)

import traceback


def ExceptHandler(etype, value, tb):
    if QCoreApplication.instance().thread() == QThread.currentThread():
        msg = traceback.format_exception(etype, value, tb)
        QMessageBox.warning(None, "Exception occurred!",
                            "".join(msg), QMessageBox.Ok)
    else:
        traceback.print_exception(etype, value, tb)
