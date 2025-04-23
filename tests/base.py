# -*- coding: utf-8 -*-
from shiboken6 import delete
from qgitc.application import Application

import sys
import unittest


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
