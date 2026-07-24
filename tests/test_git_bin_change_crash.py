# -*- coding: utf-8 -*-
"""
Regression tests for the crash when switching git binaries in a large repo.

Root cause
----------
When the user switches the git binary in Preferences, Application.event()
handles GitBinChanged by calling _initGit() then reloadRepo().  Both of these
call QGitProcess.communicate(), which spins processEvents() while waiting for
the subprocess to finish.

In a large repository the LogsFetcher background thread is simultaneously
pushing logsAvailable signals.  Those signals are delivered during
processEvents() and ultimately call DiffView.showCommit(), which starts the
DiffFetcher and (for composite-mode commits) populates _commitList with
sub-commits.

A little later __updateBranches() calls diffView.clear() followed by
Git.branches() (again via QGitProcess / processEvents()).  Before the fix,
DiffView.clear() did NOT deactivate the DiffFetcher and did NOT empty _commitList.
So when DiffFetcher.fetchFinished fired during the next processEvents() window,
__onFetchFinished would pop stale sub-commits from _commitList and start yet
more fetches.  If any of those stale fetches failed, QMessageBox.critical()
was called, spawning a nested event loop that further amplified the re-entrancy,
eventually causing a crash.

Fixes applied
-------------
1. DiffView.clear() now calls self.fetcher.deactivate() (non-blocking) and
   resets _commitList=[].  deactivate() sets _active=False so onDataFinished
   returns early and never emits fetchFinished, stopping the sub-commit cascade
   without blocking the GUI thread.
2. MainWindow.cancel() now also calls logView.fetcher.cancel() so the
   LogsFetcher is stopped before processEvents() is re-entered.
3. Application.event(GitBinChanged) calls logWindow.cancel() before _initGit()
   so that fetchers are stopped at the earliest possible point.
"""

import sys
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget
from shiboken6 import delete

from qgitc.common import Commit
from qgitc.diffview import DiffView
from tests.base import TestBase


class TestDiffViewClearCancelsFetcher(TestBase):
    """DiffView.clear() must stop any active DiffFetcher and empty _commitList."""

    def doCreateRepo(self):
        # No real repo needed for these unit tests.
        pass

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _makeSubCommit(self, sha1="abc1234abc1234ab", repoDir="."):
        c = Commit()
        c.sha1 = sha1
        c.repoDir = repoDir
        c.subCommits = []
        return c

    # ------------------------------------------------------------------
    # tests
    # ------------------------------------------------------------------

    def test_clear_resets_commit_list(self):
        """_commitList must be [] after clear(), regardless of prior contents."""
        dv = DiffView()
        sub = self._makeSubCommit()
        dv._commitList = [sub, sub]

        dv.clear()

        self.assertEqual(dv._commitList, [],
                         "_commitList must be empty after clear()")
        delete(dv)

    def test_clear_deactivates_fetcher(self):
        """DiffView.clear() must call fetcher.deactivate() to stop cascade without blocking."""
        dv = DiffView()

        deactivate_calls = []
        original_deactivate = dv.fetcher.deactivate

        def _spy(*args, **kwargs):
            deactivate_calls.append(True)
            original_deactivate(*args, **kwargs)

        dv.fetcher.deactivate = _spy

        dv.clear()

        self.assertGreater(len(deactivate_calls), 0,
                           "fetcher.deactivate() must be called by DiffView.clear()")
        # _active must be False so onDataFinished won't emit fetchFinished
        self.assertFalse(dv.fetcher._active,
                         "fetcher._active must be False after clear()")
        delete(dv)

    def test_fetch_finished_after_clear_does_not_restart_fetch(self):
        """If __onFetchFinished fires after clear(), it must not pop from
        _commitList and start another fetch (which could show QMessageBox)."""
        dv = DiffView()
        sub = self._makeSubCommit()

        # Simulate the scenario: _commitList has stale sub-commits.
        dv._commitList = [sub]
        dv.fetcher._active = True

        # Now clear() — this is what __updateBranches() calls.
        dv.clear()

        # Simulate the stale fetchFinished signal arriving after clear().
        # We call the private slot directly to verify it is a no-op.
        fetch_calls = []
        original_fetch = dv.fetcher.fetch

        def _spy_fetch(*args, **kwargs):
            fetch_calls.append(args)
            # Don't actually start a QProcess in a unit test.

        dv.fetcher.fetch = _spy_fetch

        # Directly invoke the slot to simulate the queued signal delivery.
        dv._DiffView__onFetchFinished(0)  # exitCode=0

        self.assertEqual(fetch_calls, [],
                         "__onFetchFinished after clear() must not start a new fetch")
        delete(dv)

    def test_clear_is_idempotent(self):
        """Calling clear() multiple times must not crash."""
        dv = DiffView()
        dv._commitList = [self._makeSubCommit()]

        dv.clear()
        dv.clear()  # second call must be safe

        self.assertEqual(dv._commitList, [])
        delete(dv)


class TestMainWindowCancelCancelsFetchers(TestBase):
    """MainWindow.cancel() must stop the LogsFetcher(s) in addition to the
    delay timer, so that processEvents() calls in reloadRepo() don't deliver
    stale signals."""

    def doCreateRepo(self):
        pass

    def _makeMockMainWindow(self):
        """Build a minimal mock MainWindow for cancel() testing."""
        from qgitc.logsfetcher import LogsFetcher

        mw = MagicMock()

        # Build a real LogsFetcher so we can check cancel() was called.
        self._fetcherA = LogsFetcher()
        cancel_calls = []

        original_cancel = self._fetcherA.cancel

        def _track_cancel(force=False):
            cancel_calls.append(force)
            original_cancel(force)

        self._fetcherA.cancel = _track_cancel
        self._cancelCalls = cancel_calls

        logViewA = MagicMock()
        logViewA.fetcher = self._fetcherA

        gitViewA = MagicMock()
        gitViewA.logView = logViewA

        mw.ui.gitViewA = gitViewA
        mw.gitViewB = None
        return mw

    def test_cancel_calls_log_fetcher_cancel(self):
        """MainWindow.cancel() must propagate to gitViewA.logView.fetcher.cancel()."""
        from qgitc.mainwindow import MainWindow

        mw = self._makeMockMainWindow()

        # Patch _delayTimer to avoid needing a real QTimer.
        mw._delayTimer = MagicMock()

        # Call MainWindow.cancel as an unbound method, passing the mock as self.
        MainWindow.cancel(mw, force=False)

        self.assertGreater(len(self._cancelCalls), 0,
                           "cancel() must have been called on the LogsFetcher")

        delete(self._fetcherA)


class TestApplicationEventCancelsBeforeInitGit(TestBase):
    """Application.event(GitBinChanged) must call logWindow.cancel() before
    _initGit() so that no processEvents() loops run with live fetchers."""

    def doCreateRepo(self):
        pass

    def test_cancel_called_before_init_git(self):
        """cancel() must be called before _initGit() on GitBinChanged."""
        from qgitc.application import Application
        from qgitc.events import GitBinChanged

        app = self.app

        cancel_order = []

        mockWindow = MagicMock()

        def _mock_cancel(force=False):
            cancel_order.append("cancel")

        mockWindow.cancel = _mock_cancel

        original_initGit = app._initGit

        def _mock_initGit(gitBin):
            cancel_order.append("_initGit")
            # Don't actually run git in a unit test.

        app._logWindow = mockWindow

        with patch.object(app, "_initGit", side_effect=_mock_initGit):
            with patch.object(app, "_logWindow", mockWindow):
                with patch.object(mockWindow, "reloadRepo"):
                    app.event(GitBinChanged())

        # cancel() must appear before _initGit() in the call order.
        self.assertIn("cancel", cancel_order,
                      "cancel() must be called during GitBinChanged handling")
        self.assertIn("_initGit", cancel_order,
                      "_initGit() must be called during GitBinChanged handling")
        cancel_idx = cancel_order.index("cancel")
        init_idx = cancel_order.index("_initGit")
        self.assertLess(cancel_idx, init_idx,
                        "cancel() must be called before _initGit()")

        app._logWindow = None
