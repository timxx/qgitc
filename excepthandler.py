# -*- coding: utf-8 -*-

from PyQt4.QtGui import QMessageBox, qApp

import traceback


def ExceptHandler(etype, value, tb):
    msg = traceback.format_exception(etype, value, tb)
    parent = qApp.activeWindow() if qApp else None
    QMessageBox.warning(parent, "Exception occurred!",
                        "".join(msg), QMessageBox.Ok)
