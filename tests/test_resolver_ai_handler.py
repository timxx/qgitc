# -*- coding: utf-8 -*-

from unittest.mock import patch

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtTest import QSignalSpy

from qgitc.resolver.enums import ResolveOperation, ResolveOutcomeStatus
from qgitc.resolver.handlers.ai import AiResolveHandler
from qgitc.resolver.models import ResolveContext
from qgitc.resolver.services import ResolveServices
from tests.base import TestBase


class _InlineTask(QObject):
    finished = Signal(bool, object, object)


class _InlineRunner:
    def run(self, fn):
        t = _InlineTask()

        def _go():
            try:
                out = fn()
                t.finished.emit(True, out, None)
            except Exception as e:
                t.finished.emit(False, None, str(e))

        QTimer.singleShot(0, _go)
        return t


class _DummyManager:
    def emitEvent(self, event):
        pass


class _FakeJob(QObject):
    finished = Signal(bool, object)


class _FakeAi:
    def __init__(self, ok=True):
        self._ok = ok

    def resolveFileAsync(self, repoDir, sha1, path, conflictText, extraContext=None):
        job = _FakeJob()
        QTimer.singleShot(0, lambda: job.finished.emit(self._ok, None))
        return job


class TestAiResolveHandler(TestBase):

    def doCreateRepo(self):
        pass

    def _services(self, ai):
        s = ResolveServices(runner=_InlineRunner(), ai=ai)
        s.manager = _DummyManager()
        return s

    def test_skips_when_no_ai(self):
        h = AiResolveHandler(self.app)
        spy = QSignalSpy(h.finished)

        ctx = ResolveContext(
            repoDir=".", operation=ResolveOperation.MERGE, sha1="", path="a.txt")
        h.start(ctx, self._services(ai=None))

        self.wait(500, lambda: spy.count() == 0)
        handled, outcome = spy.at(0)
        self.assertFalse(handled)
        self.assertIsNone(outcome)

    @patch("qgitc.resolver.handlers.ai.Git.addFiles", autospec=True)
    @patch("qgitc.resolver.handlers.ai.Git.resolveBy", autospec=True)
    @patch("qgitc.resolver.handlers.ai.Git.getConflictFileBlobIds", autospec=True)
    def test_trivial_take_ours(self, mock_blobids, mock_resolveBy, mock_addFiles):
        mock_blobids.return_value = {1: "base", 2: "same", 3: "same"}
        mock_resolveBy.return_value = True
        mock_addFiles.return_value = ""  # treated as success

        h = AiResolveHandler(self.app)
        spy = QSignalSpy(h.finished)
        ctx = ResolveContext(
            repoDir=".", operation=ResolveOperation.MERGE, sha1="", path="a.txt")
        h.start(ctx, self._services(ai=_FakeAi(ok=True)))

        self.wait(2000, lambda: spy.count() == 0)
        handled, outcome = spy.at(0)
        self.assertTrue(handled)
        self.assertEqual(ResolveOutcomeStatus.RESOLVED, outcome.status)

    @patch("qgitc.resolver.handlers.ai.buildConflictExcerpt", autospec=True)
    @patch("qgitc.resolver.handlers.ai.Git.addFiles", autospec=True)
    @patch("qgitc.resolver.handlers.ai.Git.getConflictFileBlobIds", autospec=True)
    def test_non_trivial_uses_ai(self, mock_blobids, mock_addFiles, mock_excerpt):
        mock_blobids.return_value = {1: "base", 2: "ours", 3: "theirs"}
        mock_excerpt.return_value = "<<<<<<<<<\nconflict\n>>>>>>>"
        mock_addFiles.return_value = ""

        h = AiResolveHandler(self.app)
        spy = QSignalSpy(h.finished)
        ctx = ResolveContext(
            repoDir=".", operation=ResolveOperation.MERGE, sha1="abc", path="a.txt")
        h.start(ctx, self._services(ai=_FakeAi(ok=True)))

        self.wait(2000, lambda: spy.count() == 0)
        handled, outcome = spy.at(0)
        self.assertTrue(handled)
        self.assertEqual(ResolveOutcomeStatus.RESOLVED, outcome.status)
