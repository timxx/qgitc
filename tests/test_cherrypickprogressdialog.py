# -*- coding: utf-8 -*-

from __future__ import annotations

from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QWidget

from qgitc.cherrypickprogressdialog import CherryPickProgressDialog
from qgitc.cherrypicksession import CherryPickItem, CherryPickItemStatus
from qgitc.resolver.enums import ResolveOperation
from tests.base import TestBase


class _DummyAiChatWidget(QWidget):
    def __init__(self, parent=None, embedded=False):
        super().__init__(parent)
        self.embedded = embedded
        self._provider = None

    def setContextProvider(self, provider):
        self._provider = provider


class TestCherryPickProgressDialog(TestBase):

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.dialog = CherryPickProgressDialog()

    def tearDown(self):
        self.dialog.close()
        self.processEvents()
        super().tearDown()

    def test_startSession_populates_list_and_calls_session_start(self):
        items = [CherryPickItem(sha1="1111111abcdef"),
                 CherryPickItem(sha1="2222222abcdef")]

        with patch.object(self.dialog, "exec", return_value=QDialog.Accepted) as execFn, patch.object(
            self.dialog._session, "start"
        ) as startFn:
            ret = self.dialog.startSession(
                items=items,
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
                allowPatchPick=False,
                aiEnabled=False,
            )

        self.assertEqual(QDialog.Accepted, ret)
        execFn.assert_called_once()
        startFn.assert_called_once()

        self.assertEqual(2, self.dialog._list.count())
        self.assertEqual("1111111", self.dialog._list.item(0).text())
        self.assertEqual("2222222", self.dialog._list.item(1).text())
        self.assertEqual(CherryPickItemStatus.PENDING,
                         self.dialog._list.item(0).data(Qt.UserRole))

    def test_ai_toggle_shows_and_hides_ai_container(self):
        with patch("qgitc.cherrypickprogressdialog.AiChatWidget", _DummyAiChatWidget):
            self.dialog.show()
            self.processEvents()

            self.dialog._onAiAutoResolveToggled(True)
            self.processEvents()
            self.assertIsNotNone(self.dialog._aiChatWidget)
            self.assertTrue(self.dialog._aiContainer.isVisible())

            self.dialog._onAiAutoResolveToggled(False)
            self.processEvents()
            self.assertFalse(self.dialog._aiContainer.isVisible())

    def test_item_status_rendering(self):
        items = [CherryPickItem(sha1="abcdef012345")]

        with patch.object(self.dialog, "exec", return_value=QDialog.Rejected), patch.object(
            self.dialog._session, "start"
        ):
            self.dialog.startSession(
                items=items,
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
                aiEnabled=False,
            )

        self.dialog._onItemStatusChanged(
            0, CherryPickItemStatus.NEEDS_RESOLUTION, "")
        self.assertIn("Needs resolution", self.dialog._list.item(0).text())

        self.dialog._onItemStatusChanged(0, CherryPickItemStatus.FAILED, "x")
        self.assertIn("Failed", self.dialog._list.item(0).text())
        self.assertNotIn("x", self.dialog._list.item(0).text())

        self.dialog._onItemStatusChanged(0, CherryPickItemStatus.PICKED, "")
        self.assertIn("Picked", self.dialog._list.item(0).text())

        self.dialog._onItemStatusChanged(0, CherryPickItemStatus.ABORTED, "")
        self.assertIn("Aborted", self.dialog._list.item(0).text())

    def test_conflictsDetected_updates_status_text(self):
        self.dialog._onConflictsDetected(
            ResolveOperation.CHERRY_PICK, ["a.txt"])
        self.assertIn("Conflicts detected", self.dialog._status.text())

        self.dialog._onConflictsDetected(ResolveOperation.AM, ["a.txt"])
        self.assertIn("Patch conflicts", self.dialog._status.text())

    def test_finished_enables_close_and_calls_reload(self):
        reloadFn = Mock()
        self.dialog.setReloadCallback(reloadFn)

        # needReload True triggers reload unless aborted
        self.dialog._onFinished(ok=True, aborted=False,
                                needReload=True, message="")
        reloadFn.assert_called_once()
        self.assertFalse(self.dialog._abortBtn.isEnabled())
        self.assertTrue(self.dialog._closeBtn.isEnabled())
        self.assertIn("Completed", self.dialog._status.text())

        reloadFn.reset_mock()
        self.dialog._onFinished(ok=False, aborted=True,
                                needReload=True, message="")
        reloadFn.assert_not_called()
        self.assertIn("Aborted", self.dialog._status.text())

    def test_itemStarted_calls_ensureVisible_callback(self):
        ensureFn = Mock()
        self.dialog.setEnsureVisibleCallback(ensureFn)

        item = CherryPickItem(sha1="abcdef012345", sourceIndex=7)
        self.dialog._onItemStarted(0, item)
        ensureFn.assert_called_once_with(7)

    def test_ai_context_provider_receives_current_item_and_file(self):
        # Avoid constructing the real chat widget; we only care about provider calls.
        provider = Mock()
        self.dialog._aiContextProvider = provider

        item = CherryPickItem(sha1="abcdef012345", repoDir=".")
        self.dialog._onItemStarted(0, item)
        provider.setCurrentItem.assert_called_once()

        self.dialog._onResolveCurrentFileChanged("x.txt")
        provider.setCurrentFile.assert_called_once_with("x.txt")
