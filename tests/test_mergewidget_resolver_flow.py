# -*- coding: utf-8 -*-

import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QStandardItem

from qgitc.mergewidget import STATE_CONFLICT, MergeWidget, StateRole
from qgitc.resolver.enums import ResolveOperation, ResolveOutcomeStatus
from qgitc.resolver.models import ResolveOutcome
from tests.base import TestBase


class _FakeResolveManager(QObject):
    eventEmitted = Signal(object)
    promptRequested = Signal(object)
    completed = Signal(object)

    def __init__(self, handlers, services, parent=None):
        super().__init__(parent)
        self.handlers = handlers
        self.services = services
        self.started_ctx = None
        self.services.manager = self

    last_ctx = None

    def start(self, ctx):
        self.started_ctx = ctx
        _FakeResolveManager.last_ctx = ctx
        self.completed.emit(ResolveOutcome(
            ResolveOutcomeStatus.RESOLVED, "ok"))


class TestMergeWidgetResolverFlow(TestBase):

    def doCreateRepo(self):
        pass

    def test_resolve_sets_operation_cherrypick_when_cherrypicking(self):
        w = MergeWidget()
        item = QStandardItem("a.txt")
        item.setData(STATE_CONFLICT, StateRole)
        w.model.appendRow(item)
        idx = w.proxyModel.index(0, 0)

        with patch("qgitc.mergewidget.ResolveManager", _FakeResolveManager), \
                patch("qgitc.mergewidget.Git.REPO_DIR", "."), \
                patch("qgitc.mergewidget.Git.isCherryPicking", return_value=True), \
                patch("qgitc.mergewidget.Git.cherryPickHeadSha1", return_value="deadbeef"), \
                patch("qgitc.mergewidget.Git.getConfigValue", return_value="kdiff3"), \
                patch("qgitc.mergewidget.ApplicationBase.instance") as mock_app, \
                patch("qgitc.mergewidget.QMessageBox.information") as mock_msgbox:

            mock_app.return_value.applicationName.return_value = "qgitc"
            mock_app.return_value.settings.return_value.mergeToolList.return_value = []
            mock_app.return_value.settings.return_value.mergeToolName.return_value = "kdiff3"

            w.resolve(idx)
            ctx = _FakeResolveManager.last_ctx
            self.assertEqual(ResolveOperation.CHERRY_PICK, ctx.operation)
            self.assertEqual("deadbeef", ctx.sha1)
            self.assertEqual("a.txt", ctx.path)
            mock_msgbox.assert_called_once()

    def test_resolve_warns_when_no_tool_and_no_ai(self):
        w = MergeWidget()
        item = QStandardItem("a.txt")
        item.setData(STATE_CONFLICT, StateRole)
        w.model.appendRow(item)
        idx = w.proxyModel.index(0, 0)

        w.cbAutoResolve.setChecked(False)

        with patch("qgitc.mergewidget.Git.REPO_DIR", "."), \
                patch("qgitc.mergewidget.Git.isCherryPicking", return_value=False), \
                patch("qgitc.mergewidget.Git.getConfigValue", return_value=""), \
                patch("qgitc.mergewidget.ApplicationBase.instance") as mock_app, \
                patch("qgitc.mergewidget.QMessageBox.warning") as mock_warn:

            mock_app.return_value.settings.return_value.mergeToolList.return_value = []
            mock_app.return_value.settings.return_value.mergeToolName.return_value = ""

            w.resolve(idx)
            self.assertTrue(mock_warn.called)
            self.assertIsNone(w._resolveManager)

    def test_ensure_log_writer_creates_parent_directory(self):
        w = MergeWidget()

        with TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "nested", "dir", "conflicts.xlsx")
            parent_dir = os.path.dirname(log_file)
            self.assertFalse(os.path.exists(parent_dir))

            w.cbAutoLog.setChecked(True)
            w.leLogFile.setText(log_file)

            # Private method (name-mangled): should create folder then copy template.
            w._MergeWidget__ensureLogWriter()

            self.assertTrue(os.path.isdir(parent_dir))
            self.assertTrue(os.path.isfile(log_file))

            # Ensure we release resources and flush the workbook.
            self.assertTrue(w.queryClose())
