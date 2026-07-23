# -*- coding: utf-8 -*-

import sys
from io import StringIO
from unittest.mock import MagicMock

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget
from shiboken6 import delete

from qgitc.applicationbase import ApplicationBase
from qgitc.mainwindowcontextprovider import MainWindowContextProvider
from tests.base import TestBase


class TestMainWindowContextProvider(TestBase):

    def doCreateRepo(self):
        pass

    def _makeMockMainWindow(self):
        """Build a minimal mock mainWindow that passes _installHooks."""
        mw = MagicMock()

        # Use real QObjects for Signal-based widgets so that .connect() works.
        logView = QObject()
        setattr(type(logView), "currentIndexChanged", Signal())

        cbBranch = QObject()
        setattr(type(cbBranch), "currentIndexChanged", Signal())

        # selModel: real QObject so selectionChanged.connect(self._scheduleChanged) works.
        self._mockSelModel = QObject()
        setattr(type(self._mockSelModel), "selectionChanged", Signal())

        fileListView = QObject()

        def _selModel():
            return self._mockSelModel
        fileListView.selectionModel = _selModel

        viewer = QObject()
        setattr(type(viewer), "selectionChanged", Signal())

        diffView = MagicMock()
        diffView.fileListView = fileListView
        diffView.viewer = viewer

        gitViewA = MagicMock()
        gitViewA.ui.logView = logView
        gitViewA.ui.cbBranch = cbBranch
        gitViewA.ui.diffView = diffView

        mw.ui.gitViewA = gitViewA

        cbSubmodule = QObject()
        setattr(type(cbSubmodule), "currentIndexChanged", Signal())
        mw.ui.cbSubmodule = cbSubmodule
        return mw

    def _assertNoSignalError(self, signalEmitter):
        """Emit a signal and assert no RuntimeError is written to stderr."""
        oldStderr = sys.stderr
        sys.stderr = captured = StringIO()
        try:
            signalEmitter()
        finally:
            sys.stderr = oldStderr

        stderrText = captured.getvalue()
        self.assertEqual(
            stderrText, "",
            f"RuntimeError occurred during signal dispatch:\n{stderrText}",
        )

    def testScheduleChangedAfterDeleteDoesNotCrash(self):
        """When the provider is deleted and submoduleAvailable fires afterward,
        _scheduleChanged must not crash trying to access the deleted _emitTimer."""
        parent = QWidget()
        provider = MainWindowContextProvider(
            self._makeMockMainWindow(), parent)

        self.assertIsNotNone(provider._emitTimer)
        self.assertIsInstance(provider._emitTimer, QTimer)

        delete(provider)

        self._assertNoSignalError(
            lambda: ApplicationBase.instance().submoduleAvailable.emit([], True))

        delete(parent)

    def testSelectionChangedAfterDeleteDoesNotCrash(self):
        """selectionChanged (selModel) also connects via real slot now;
        emitting after provider deletion must not crash."""

        parent = QWidget()
        provider = MainWindowContextProvider(
            self._makeMockMainWindow(), parent)

        self.assertIsNotNone(provider._emitTimer)
        self.assertIsInstance(provider._emitTimer, QTimer)

        delete(provider)

        self._assertNoSignalError(
            lambda: self._mockSelModel.selectionChanged.emit())

        delete(parent)
