# -*- coding: utf-8 -*-
import logging
from shiboken6 import delete
from qgitc.application import Application

import sys
import unittest


_log_inited = False


def _setup_logging():
    global _log_inited
    if _log_inited:
        return

    _log_inited = True
    rootLogger = logging.getLogger()
    rootLogger.setLevel(logging.WARNING)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(levelname)s][%(asctime)s]%(filename)s:%(lineno)d - %(message)s")
    handler.setFormatter(formatter)

    rootLogger.addHandler(handler)

    thirdLoggers = ["requests", "urllib3"]
    for name in thirdLoggers:
        logger = logging.getLogger(name)
        if logger:
            logger.setLevel(logging.WARNING)


_setup_logging()


class TestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Application(sys.argv, testing=True)

    @classmethod
    def tearDownClass(cls):
        cls.processEvents(cls)
        cls.app.quit()
        # FIXME: `RuntimeError: Please destroy the Application singleton before creating a new Application instance`
        delete(cls.app)
        del cls.app

    def processEvents(self):
        self.app.sendPostedEvents()
        self.app.processEvents()
