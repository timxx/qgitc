# -*- coding: utf-8 -*-

from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QWidget
from shiboken6 import Shiboken

from qgitc.llmproviderdialog import LlmProviderDialog
from tests.base import TestBase


class TestLlmProviderDialog(TestBase):

    def doCreateRepo(self):
        pass

    def testExecDestroysDialogInGuiThread(self):
        # exec() leaves the dialog owned by Python even when it has a parent,
        # so anything left to the cyclic collector is destroyed by whichever
        # thread happens to run the collection.
        parent = QWidget()
        dialog = LlmProviderDialog([], parent)

        QTimer.singleShot(0, dialog.reject)
        dialog.exec()
        # processEvents() never delivers deferred deletions
        self.app.sendPostedEvents(None, QEvent.DeferredDelete)

        self.assertFalse(Shiboken.isValid(dialog))
