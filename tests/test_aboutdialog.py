# -*- coding: utf-8 -*-
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog
from qgitc.aboutdialog import AboutDialog
from tests.base import TestBase


class TestAboutDialog(TestBase):
    def setUp(self):
        super().setUp()
        self.dialog = AboutDialog()

    def doCreateRepo(self):
        pass

    def testRun(self):
        QTimer.singleShot(0, self.dialog.reject)
        ret = self.dialog.exec()
        self.assertEqual(ret, QDialog.Rejected)
