# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from qgitc.preferences import Preferences
from tests.base import TestBase


class TestPreferences(TestBase):
    def setUp(self):
        super().setUp()
        self.preferences = Preferences(self.app.settings())

    def testCommitPage(self):
        self.preferences.ui.tabWidget.setCurrentWidget(
            self.preferences.ui.tabCommitMessage)

        QTimer.singleShot(0, self._testCommitPage)
        # avoid dialog not closing
        QTimer.singleShot(10000, self.preferences.reject)

        oldValue = self.preferences.ui.cbIgnoreComment.isChecked()
        ret = self.preferences.exec()
        self.assertEqual(ret, QDialog.Accepted)

        self.assertNotEqual(
            oldValue, self.preferences.ui.cbIgnoreComment.isChecked())
        self.assertEqual(self.preferences.ui.cbIgnoreComment.isChecked(),
                         self.app.settings().ignoreCommentLine())

    def _testCommitPage(self):
        self.assertEqual(self.preferences.ui.cbIgnoreComment.isChecked(),
                         self.app.settings().ignoreCommentLine())
        # not working
        # QTest.mouseClick(self.preferences.ui.cbIgnoreComment, Qt.LeftButton)
        self.preferences.ui.cbIgnoreComment.setChecked(
            not self.preferences.ui.cbIgnoreComment.isChecked())

        QTest.mouseClick(self.preferences.ui.buttonBox.button(
            QDialogButtonBox.Ok), Qt.LeftButton)
