# -*- coding: utf-8 -*-

from unittest.mock import patch

from qgitc.resolver.enums import (
    ResolveFailureReason,
    ResolveOperation,
    ResolveOutcomeStatus,
)
from qgitc.resolver.models import ResolveOutcome
from qgitc.resolver.resolvepanel import ResolvePanel, _FileState
from tests.base import TestBase


class TestResolvePanel(TestBase):

    def doCreateRepo(self):
        pass

    def _panel(self, files=None):
        panel = ResolvePanel()
        panel.setContext(
            repoDir="/repo",
            operation=ResolveOperation.CHERRY_PICK,
            sha1="0" * 40,
        )
        if files:
            panel.setConflictFiles(files)
        return panel

    def test_failed_file_updates_status_text(self):
        p = ResolvePanel()
        # simulate internal state: as if a file was being resolved
        p._currentPath = "a.txt"
        p._fileStates = {"a.txt": 0}

        # behave as if the manager just completed with a failure
        p._onFileCompleted(
            "a.txt",
            ResolveOutcome(
                status=ResolveOutcomeStatus.FAILED,
                message="no merge tool configured",
            ),
        )

        self.assertIn("Failed to resolve", p._label.text())
        self.assertIn("a.txt", p._label.text())
        self.assertIn("no merge tool configured", p._label.text())

    def test_no_merge_tool_warns_user_and_marks_file_failed(self):
        p = self._panel(["a.txt"])
        outcomes = []
        p.fileOutcome.connect(lambda path, out: outcomes.append((path, out)))

        with patch("qgitc.resolver.resolvepanel.buildResolveHandlers",
                   return_value=([], None, False)), \
                patch("qgitc.resolver.resolvepanel.QMessageBox.warning") as warn:
            p.startResolveAll()

        self.assertTrue(warn.called)
        self.assertEqual(_FileState.FAILED, p._fileStates["a.txt"])
        self.assertEqual(1, len(outcomes))
        self.assertEqual(ResolveOutcomeStatus.FAILED, outcomes[0][1].status)

    def test_no_merge_tool_warns_only_once_per_pass(self):
        p = self._panel(["a.txt", "b.txt"])

        with patch("qgitc.resolver.resolvepanel.buildResolveHandlers",
                   return_value=([], None, False)), \
                patch("qgitc.resolver.resolvepanel.QMessageBox.warning") as warn:
            p.startResolveAll()

        self.assertEqual(1, warn.call_count)

    def test_no_tool_fails_every_file_with_a_single_warning(self):
        files = [f"f{i}.txt" for i in range(5)]
        p = self._panel(files)
        failed = []
        p.fileOutcome.connect(lambda path, out: failed.append(path))
        drained = []
        p.currentFileChanged.connect(lambda obj: drained.append(obj))

        with patch("qgitc.resolver.resolvepanel.buildResolveHandlers",
                   return_value=([], None, False)), \
                patch("qgitc.resolver.resolvepanel.QMessageBox.warning") as warn:
            p.startResolveAll()

        self.assertEqual(files, failed)
        self.assertEqual(1, warn.call_count)
        self.assertIn(None, drained)

    def test_failed_pass_drains_queue_so_caller_can_report(self):
        p = self._panel(["a.txt"])
        drained = []
        p.currentFileChanged.connect(lambda obj: drained.append(obj))

        with patch("qgitc.resolver.resolvepanel.buildResolveHandlers",
                   return_value=([], None, False)), \
                patch("qgitc.resolver.resolvepanel.QMessageBox.warning"):
            p.startResolveAll()

        # The cherry-pick session learns the pass ended from currentFileChanged(None);
        # without it the pick window keeps showing "resolving" forever.
        self.assertIn(None, drained)

    def test_missing_tool_file_outcome_warns_user(self):
        p = self._panel(["a.txt"])
        drained = []
        p.currentFileChanged.connect(lambda obj: drained.append(obj))

        with patch("qgitc.resolver.resolvepanel.QMessageBox.warning") as warn:
            p._onFileCompleted(
                "a.txt",
                ResolveOutcome(
                    status=ResolveOutcomeStatus.FAILED,
                    message="No merge tool is configured",
                    details={"reason": ResolveFailureReason.NO_MERGETOOL},
                ),
            )

        self.assertTrue(warn.called)
        self.assertIn(None, drained)

    def test_unrelated_failure_does_not_warn(self):
        p = self._panel(["a.txt"])

        with patch("qgitc.resolver.resolvepanel.QMessageBox.warning") as warn:
            p._onFileCompleted(
                "a.txt",
                ResolveOutcome(
                    status=ResolveOutcomeStatus.FAILED,
                    message="Resolve failed",
                ),
            )

        self.assertFalse(warn.called)

    def test_retry_warns_again(self):
        p = self._panel(["a.txt"])

        with patch("qgitc.resolver.resolvepanel.buildResolveHandlers",
                   return_value=([], None, False)), \
                patch("qgitc.resolver.resolvepanel.QMessageBox.warning") as warn:
            p.startResolveAll()
            self.assertEqual(1, warn.call_count)

            # The user configured a tool and retried: they deserve the hint again
            # when it still cannot be used.
            p._retryResolveForPath("a.txt")

        self.assertEqual(2, warn.call_count)
