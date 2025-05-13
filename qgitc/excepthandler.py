# -*- coding: utf-8 -*-

import logging
import traceback

from PySide6.QtCore import QCoreApplication, QThread
from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


def ExceptHandler(etype, value, tb):
    if QCoreApplication.instance().thread() == QThread.currentThread():
        msg = traceback.format_exception(etype, value, tb)
        QMessageBox.warning(None, "Exception occurred!",
                            "".join(msg), QMessageBox.Ok)
    else:
        traceback.print_exception(etype, value, tb)

    logger.exception("exception occurred", exc_info=(etype, value, tb))
