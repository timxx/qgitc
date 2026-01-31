# -*- coding: utf-8 -*-

from PySide6.QtTest import QSignalSpy

from qgitc.resolver.enums import (
    ResolveOperation,
    ResolveOutcomeStatus,
    ResolvePromptKind,
)
from qgitc.resolver.handlers.base import ResolveHandler
from qgitc.resolver.manager import ResolveManager
from qgitc.resolver.models import ResolveContext, ResolveOutcome, ResolvePrompt
from qgitc.resolver.services import ResolveServices
from qgitc.resolver.taskrunner import TaskRunner
from tests.base import TestBase


class _ImmediateHandler(ResolveHandler):
    def __init__(self, handled: bool, outcome: ResolveOutcome | None, parent=None):
        super().__init__(parent)
        self._handled = handled
        self._outcome = outcome

    def start(self, ctx: ResolveContext, services: ResolveServices):
        self.finished.emit(self._handled, self._outcome)


class _PromptingHandler(ResolveHandler):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._services: ResolveServices | None = None
        self._promptId = 42

    def start(self, ctx: ResolveContext, services: ResolveServices):
        self._services = services
        p = ResolvePrompt(
            promptId=self._promptId,
            kind=ResolvePromptKind.SYMLINK_CONFLICT_CHOICE,
            title="Prompt",
            text="Choose",
            options=["l", "r"],
        )
        services.manager.requestPrompt(p)

    def onPromptReply(self, promptId: int, choice: object):
        if promptId != self._promptId:
            return
        out = ResolveOutcome(
            status=ResolveOutcomeStatus.RESOLVED, message=str(choice))
        self.finished.emit(True, out)


class TestResolveManager(TestBase):

    def doCreateRepo(self):
        pass

    def test_no_handlers_fails(self):
        services = ResolveServices(runner=TaskRunner(self.app))
        manager = ResolveManager([], services, parent=self.app)
        spy = QSignalSpy(manager.completed)

        manager.start(ResolveContext(
            repoDir=".", operation=ResolveOperation.MERGE, sha1="", path=""))

        self.wait(500, lambda: spy.count() == 0)
        self.assertEqual(1, spy.count())
        outcome: ResolveOutcome = spy.at(0)[0]
        self.assertEqual(ResolveOutcomeStatus.FAILED, outcome.status)

    def test_pipeline_continues_after_resolved(self):
        services = ResolveServices(runner=TaskRunner(self.app))
        h1 = _ImmediateHandler(True, ResolveOutcome(
            ResolveOutcomeStatus.RESOLVED, "h1"), self.app)
        h2 = _ImmediateHandler(True, ResolveOutcome(
            ResolveOutcomeStatus.RESOLVED, "h2"), self.app)
        manager = ResolveManager([h1, h2], services, parent=self.app)
        spy = QSignalSpy(manager.completed)

        manager.start(ResolveContext(
            repoDir=".", operation=ResolveOperation.MERGE, sha1="", path="x"))

        self.wait(500, lambda: spy.count() == 0)
        self.assertEqual(1, spy.count())
        outcome: ResolveOutcome = spy.at(0)[0]
        # End-of-pipeline returns the last RESOLVED outcome.
        self.assertEqual(ResolveOutcomeStatus.RESOLVED, outcome.status)
        self.assertEqual("h2", outcome.message)

    def test_pipeline_skips_unhandled(self):
        services = ResolveServices(runner=TaskRunner(self.app))
        h1 = _ImmediateHandler(False, None, self.app)
        h2 = _ImmediateHandler(True, ResolveOutcome(
            ResolveOutcomeStatus.RESOLVED, "ok"), self.app)
        manager = ResolveManager([h1, h2], services, parent=self.app)
        spy = QSignalSpy(manager.completed)

        manager.start(ResolveContext(
            repoDir=".", operation=ResolveOperation.MERGE, sha1="", path="x"))

        self.wait(500, lambda: spy.count() == 0)
        outcome: ResolveOutcome = spy.at(0)[0]
        self.assertEqual(ResolveOutcomeStatus.RESOLVED, outcome.status)
        self.assertEqual("ok", outcome.message)

    def test_pipeline_stops_on_failed(self):
        services = ResolveServices(runner=TaskRunner(self.app))
        h1 = _ImmediateHandler(True, ResolveOutcome(
            ResolveOutcomeStatus.FAILED, "no"), self.app)
        h2 = _ImmediateHandler(True, ResolveOutcome(
            ResolveOutcomeStatus.RESOLVED, "should_not_run"), self.app)
        manager = ResolveManager([h1, h2], services, parent=self.app)
        spy = QSignalSpy(manager.completed)

        manager.start(ResolveContext(
            repoDir=".", operation=ResolveOperation.MERGE, sha1="", path="x"))

        self.wait(500, lambda: spy.count() == 0)
        outcome: ResolveOutcome = spy.at(0)[0]
        self.assertEqual(ResolveOutcomeStatus.FAILED, outcome.status)
        self.assertEqual("no", outcome.message)

    def test_prompt_roundtrip(self):
        services = ResolveServices(runner=TaskRunner(self.app))
        h = _PromptingHandler(self.app)
        manager = ResolveManager([h], services, parent=self.app)
        spyPrompt = QSignalSpy(manager.promptRequested)
        spyDone = QSignalSpy(manager.completed)

        def _onPrompt(prompt: ResolvePrompt):
            manager.replyPrompt(prompt.promptId, "l")

        manager.promptRequested.connect(_onPrompt)
        manager.start(ResolveContext(
            repoDir=".", operation=ResolveOperation.MERGE, sha1="", path="x"))

        self.wait(500, lambda: spyPrompt.count() == 0 or spyDone.count() == 0)
        self.assertEqual(1, spyPrompt.count())
        self.assertEqual(1, spyDone.count())
        outcome: ResolveOutcome = spyDone.at(0)[0]
        self.assertEqual(ResolveOutcomeStatus.RESOLVED, outcome.status)
        self.assertEqual("l", outcome.message)
