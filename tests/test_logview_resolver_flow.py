# -*- coding: utf-8 -*-

from unittest.mock import patch

from PySide6.QtCore import QObject, QTimer, Signal

from qgitc.logview import LogView
from qgitc.resolver.enums import ResolveOperation, ResolveOutcomeStatus
from qgitc.resolver.models import ResolveOutcome
from tests.base import TestBase


class _State:
    def __init__(self, conflicts):
        self.in_progress = True
        self.conflicts = list(conflicts)
        self.aborted = False


class _FakeResolveManager(QObject):
    eventEmitted = Signal(object)
    promptRequested = Signal(object)
    completed = Signal(object)

    def __init__(self, handlers, services, parent=None):
        super().__init__(parent)
        self._handlers = handlers
        self._services = services
        self._ctx = None
        self._services.manager = self

    _provider = None

    def start(self, ctx):
        self._ctx = ctx
        outcome_provider = _FakeResolveManager._provider
        if outcome_provider is None:
            QTimer.singleShot(0, lambda: self.completed.emit(
                ResolveOutcome(ResolveOutcomeStatus.RESOLVED, "ok")))
            return

        def _emit():
            out = outcome_provider(ctx)
            self.completed.emit(out)

        QTimer.singleShot(0, _emit)

    def requestPrompt(self, prompt):
        self.promptRequested.emit(prompt)

    def replyPrompt(self, promptId, choice):
        pass

    def emitEvent(self, event):
        self.eventEmitted.emit(event)


class _FakeMessageBox:
    # Minimal QMessageBox shim used by LogView._resolveInProgressOperation.
    Question = 0
    ActionRole = 0
    AcceptRole = 0
    Yes = object()
    Abort = object()

    _queue = []  # entries: "yes"|"resolved"|"abort"|"continue"

    @classmethod
    def push(cls, *choices):
        cls._queue.extend(list(choices))

    def __init__(self, *args, **kwargs):
        self._clicked = None
        self._yes = None
        self._abort = None
        self._resolved = None
        self._continue = None

    def setWindowTitle(self, *a, **k):
        pass

    def setText(self, *a, **k):
        pass

    def setIcon(self, *a, **k):
        pass

    def setDefaultButton(self, *a, **k):
        pass

    def addButton(self, *args):
        if len(args) == 1:
            spec = args[0]
            if spec is _FakeMessageBox.Yes:
                self._yes = object()
                return self._yes
            if spec is _FakeMessageBox.Abort:
                self._abort = object()
                return self._abort
        else:
            text = args[0]
            if "Already" in str(text):
                self._resolved = object()
                return self._resolved
            if "Continue" in str(text):
                self._continue = object()
                return self._continue
        b = object()
        return b

    def exec(self):
        choice = _FakeMessageBox._queue.pop(
            0) if _FakeMessageBox._queue else "abort"
        if choice == "yes":
            self._clicked = self._yes
        elif choice == "resolved":
            self._clicked = self._resolved
        elif choice == "continue":
            self._clicked = self._continue
        else:
            self._clicked = self._abort
        return 0

    def clickedButton(self):
        return self._clicked

    @staticmethod
    def warning(*a, **k):
        return 0

    @staticmethod
    def critical(*a, **k):
        return 0


class TestLogViewResolverFlow(TestBase):

    def doCreateRepo(self):
        pass

    def test_abort_at_initial_prompt_aborts_operation(self):
        view = LogView()
        state = _State(["a.txt"])

        _FakeResolveManager._provider = lambda ctx: ResolveOutcome(
            ResolveOutcomeStatus.RESOLVED, "ok")

        # initial prompt -> abort
        _FakeMessageBox.push("abort")

        with patch("qgitc.logview.ResolveManager", _FakeResolveManager), \
                patch("qgitc.logview.QMessageBox", _FakeMessageBox), \
                patch("qgitc.logview.Git.isCherryPicking", side_effect=lambda repoDir: state.in_progress), \
                patch("qgitc.logview.Git.conflictFiles", side_effect=lambda repoDir: list(state.conflicts)), \
                patch("qgitc.logview.Git.cherryPickAbort", side_effect=lambda repoDir: setattr(state, "in_progress", False)), \
                patch("qgitc.logview.ApplicationBase.instance") as mock_app:

            # merge tool available
            mock_app.return_value.settings.return_value.mergeToolName.return_value = "kdiff3"
            with patch("qgitc.logview.Git.getConfigValue", return_value="kdiff3"):
                ok = view._resolveInProgressOperation(
                    repoDir=".",
                    operation=ResolveOperation.CHERRY_PICK,
                    sha1="abc",
                    initialError="conflict",
                    chatWidget=None,
                )

        self.assertFalse(ok)
        self.assertFalse(state.in_progress)
        _FakeResolveManager._provider = None

    def test_continue_on_failed_file_resolve_moves_to_next(self):
        view = LogView()
        state = _State(["a.txt", "b.txt"])

        def outcome_provider(ctx):
            # Per-file failures/resolves.
            if ctx.path == "a.txt":
                return ResolveOutcome(ResolveOutcomeStatus.FAILED, "user_closed")
            if ctx.path == "b.txt":
                # mark resolved by removing from conflicts
                if "b.txt" in state.conflicts:
                    state.conflicts.remove("b.txt")
                return ResolveOutcome(ResolveOutcomeStatus.RESOLVED, "ok")
            # finalize
            state.in_progress = False
            return ResolveOutcome(ResolveOutcomeStatus.RESOLVED, "continued")

        _FakeResolveManager._provider = outcome_provider

        # initial prompt yes, then on fail: continue, then finalize succeeds
        _FakeMessageBox.push("yes", "continue")

        with patch("qgitc.logview.ResolveManager", _FakeResolveManager), \
                patch("qgitc.logview.QMessageBox", _FakeMessageBox), \
                patch("qgitc.logview.Git.isCherryPicking", side_effect=lambda repoDir: state.in_progress), \
                patch("qgitc.logview.Git.conflictFiles", side_effect=lambda repoDir: list(state.conflicts)), \
                patch("qgitc.logview.Git.cherryPickAbort", side_effect=lambda repoDir: setattr(state, "in_progress", False)), \
                patch("qgitc.logview.ApplicationBase.instance") as mock_app:

            mock_app.return_value.settings.return_value.mergeToolName.return_value = "kdiff3"
            with patch("qgitc.logview.Git.getConfigValue", return_value="kdiff3"):
                ok = view._resolveInProgressOperation(
                    repoDir=".",
                    operation=ResolveOperation.CHERRY_PICK,
                    sha1="abc",
                    initialError="conflict",
                    chatWidget=None,
                )

        self.assertTrue(ok)
        self.assertFalse(state.in_progress)

        _FakeResolveManager._provider = None
