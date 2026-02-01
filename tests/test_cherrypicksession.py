# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import patch

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtTest import QSignalSpy

from qgitc.cherrypicksession import (
    CherryPickItem,
    CherryPickItemStatus,
    CherryPickSession,
)
from qgitc.gitutils import Git
from qgitc.resolver.enums import ResolveOperation, ResolveOutcomeStatus
from qgitc.resolver.models import ResolveOutcome
from tests.base import TestBase


class _FakeTask(QObject):
    finished = Signal(bool, object, object)

    def __init__(self, emitFn: Callable[[], Tuple[bool, object, object]], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._emitFn = emitFn
        QTimer.singleShot(0, self._emit)

    def _emit(self):
        ok, result, error = self._emitFn()
        self.finished.emit(ok, result, error)


class _FakeRunner(QObject):
    def run(self, fn: Callable[[], Any]):
        def _call():
            try:
                return True, fn(), None
            except Exception as e:
                return False, None, str(e)

        return _FakeTask(_call)


class _FakeResolvePanel(QObject):
    currentFileChanged = Signal(object)
    fileOutcome = Signal(str, object)
    finalizeOutcome = Signal(object)
    abortSafePointReached = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._runner = _FakeRunner()

        self.clearCalls = 0
        self.setContextCalls: List[Dict[str, object]] = []
        self.setConflictFilesCalls: List[List[str]] = []
        self.startResolveAllCalls = 0
        self.startFinalizeCalls = 0
        self.requestAbortSafelyCalls = 0

    def clear(self):
        self.clearCalls += 1

    def setContext(self, **kwargs):
        self.setContextCalls.append(dict(kwargs))

    def setConflictFiles(self, files: List[str]):
        self.setConflictFilesCalls.append(list(files or []))

    def startResolveAll(self):
        self.startResolveAllCalls += 1

    def startFinalize(self):
        self.startFinalizeCalls += 1

    def requestAbortSafely(self):
        self.requestAbortSafelyCalls += 1


class TestCherryPickSession(TestBase):

    def doCreateRepo(self):
        pass

    def _waitForSpy(self, spy: QSignalSpy, count: int = 1, timeout: int = 2000):
        self.wait(timeout, lambda: spy.count() < count)
        self.assertGreaterEqual(spy.count(), count)

    def test_empty_items_finishes_ok(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)
        spyFinished = QSignalSpy(session.finished)

        session.start(
            items=[],
            targetBaseRepoDir=".",
            sourceBaseRepoDir=".",
            recordOrigin=True,
        )

        self._waitForSpy(spyFinished)
        ok, aborted, needReload, message = spyFinished.at(0)
        self.assertTrue(ok)
        self.assertFalse(aborted)
        self.assertFalse(needReload)
        self.assertTrue(message)

    def test_local_changes_without_callback_fails(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        spyItemStatus = QSignalSpy(session.itemStatusChanged)
        spyFinished = QSignalSpy(session.finished)

        session.start(
            items=[CherryPickItem(sha1=Git.LUC_SHA1)],
            targetBaseRepoDir=".",
            sourceBaseRepoDir=".",
            recordOrigin=True,
            applyLocalChangesFn=None,
        )

        self._waitForSpy(spyItemStatus)
        self._waitForSpy(spyFinished)

        idx, status, msg = spyItemStatus.at(0)
        self.assertEqual(0, int(idx))
        self.assertEqual(CherryPickItemStatus.FAILED, status)
        self.assertTrue(msg)

        ok, aborted, _, message = spyFinished.at(0)
        self.assertFalse(ok)
        self.assertFalse(aborted)
        self.assertTrue(message)

    def test_local_changes_success_marks_and_continues(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        marks: List[Tuple[str, bool]] = []
        session.setMarkCallback(lambda sha1, ok: marks.append((sha1, ok)))

        spyItemStatus = QSignalSpy(session.itemStatusChanged)
        spyFinished = QSignalSpy(session.finished)

        def applyLocal(repoDir: str, sha1: str, sourceRepoDir: str) -> bool:
            return True

        session.start(
            items=[CherryPickItem(sha1=Git.LCC_SHA1)],
            targetBaseRepoDir=".",
            sourceBaseRepoDir=".",
            recordOrigin=True,
            applyLocalChangesFn=applyLocal,
        )

        self._waitForSpy(spyItemStatus)
        self._waitForSpy(spyFinished)

        self.assertEqual([(Git.LCC_SHA1, True)], marks)
        self.assertEqual(CherryPickItemStatus.PICKED, spyItemStatus.at(0)[1])
        self.assertEqual("", spyItemStatus.at(0)[2])

        ok, aborted, needReload, _ = spyFinished.at(0)
        self.assertTrue(ok)
        self.assertFalse(aborted)
        self.assertTrue(needReload)

    def test_cherrypick_success_marks_picked_and_finishes(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        marks: List[Tuple[str, bool]] = []
        session.setMarkCallback(lambda sha1, ok: marks.append((sha1, ok)))

        sha1 = "0123456789abcdef"

        with patch("qgitc.cherrypicksession.Git.cherryPick", return_value=(0, "", "")):
            spyItemStatus = QSignalSpy(session.itemStatusChanged)
            spyFinished = QSignalSpy(session.finished)

            session.start(
                items=[CherryPickItem(sha1=sha1)],
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
            )

            self._waitForSpy(spyItemStatus)
            self._waitForSpy(spyFinished)

        self.assertEqual([(sha1, True)], marks)
        self.assertEqual(CherryPickItemStatus.PICKED, spyItemStatus.at(0)[1])

        ok, aborted, needReload, _ = spyFinished.at(0)
        self.assertTrue(ok)
        self.assertFalse(aborted)
        self.assertTrue(needReload)

    def test_cherrypick_failure_finishes_failed(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        sha1 = "deadbeefdeadbeef"

        with patch("qgitc.cherrypicksession.Git.cherryPick", return_value=(2, "boom", "")), patch(
            "qgitc.cherrypicksession.Git.isCherryPicking", return_value=False
        ):
            spyItemStatus = QSignalSpy(session.itemStatusChanged)
            spyFinished = QSignalSpy(session.finished)

            session.start(
                items=[CherryPickItem(sha1=sha1)],
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
            )

            self._waitForSpy(spyItemStatus)
            self._waitForSpy(spyFinished)

        self.assertEqual(CherryPickItemStatus.FAILED, spyItemStatus.at(0)[1])
        self.assertIn("boom", spyItemStatus.at(0)[2])

        ok, aborted, _, message = spyFinished.at(0)
        self.assertFalse(ok)
        self.assertFalse(aborted)
        self.assertTrue(message)

    def test_bad_object_triggers_patch_pick_success(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        sha1 = "0123456789abcdef"

        with patch("qgitc.cherrypicksession.Git.cherryPick", return_value=(1, "fatal: bad object", "")), patch(
            "qgitc.cherrypicksession.Git.isCherryPicking", return_value=False
        ), patch.object(CherryPickSession, "_pickFromAnotherRepo", return_value=(0, None, None)) as pickFn:
            spyFinished = QSignalSpy(session.finished)
            spyItemStatus = QSignalSpy(session.itemStatusChanged)

            session.start(
                items=[CherryPickItem(sha1=sha1, repoDir=".")],
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
                allowPatchPick=True,
            )

            self._waitForSpy(spyItemStatus)
            self._waitForSpy(spyFinished)

        pickFn.assert_called()
        self.assertEqual(CherryPickItemStatus.PICKED, spyItemStatus.at(0)[1])

    def test_conflict_sets_needs_resolution_and_starts_resolve(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        sha1 = "0123456789abcdef"

        with patch("qgitc.cherrypicksession.Git.cherryPick", return_value=(1, "conflicts", "")), patch(
            "qgitc.cherrypicksession.Git.isCherryPicking", return_value=True
        ), patch("qgitc.cherrypicksession.Git.conflictFiles", return_value=["a.txt", "b.txt"]):
            spyItemStatus = QSignalSpy(session.itemStatusChanged)
            spyConflicts = QSignalSpy(session.conflictsDetected)

            session.start(
                items=[CherryPickItem(sha1=sha1)],
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
            )

            self._waitForSpy(spyItemStatus)
            self._waitForSpy(spyConflicts)

        self.assertEqual(CherryPickItemStatus.NEEDS_RESOLUTION,
                         spyItemStatus.at(0)[1])
        self.assertEqual("", spyItemStatus.at(0)[2])
        self.assertEqual(1, panel.clearCalls)
        self.assertEqual(ResolveOperation.CHERRY_PICK, spyConflicts.at(0)[0])
        self.assertEqual(["a.txt", "b.txt"], list(spyConflicts.at(0)[1]))
        self.assertEqual(1, panel.startResolveAllCalls)

        ctx = panel.setContextCalls[-1]
        self.assertEqual(ResolveOperation.CHERRY_PICK, ctx["operation"])
        self.assertEqual(sha1, ctx["sha1"])

    def test_resolve_failure_allows_retry_then_finalize(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        sha1 = "0123456789abcdef"

        with patch("qgitc.cherrypicksession.Git.cherryPick", return_value=(1, "conflicts", "")), patch(
            "qgitc.cherrypicksession.Git.isCherryPicking", return_value=True
        ), patch("qgitc.cherrypicksession.Git.conflictFiles", return_value=["a.txt"]):
            spyItemStatus = QSignalSpy(session.itemStatusChanged)

            session.start(
                items=[CherryPickItem(sha1=sha1)],
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
            )

            self._waitForSpy(spyItemStatus)

        # First attempt fails on a file.
        panel.fileOutcome.emit(
            "a.txt", ResolveOutcome(
                status=ResolveOutcomeStatus.FAILED, message="nope")
        )
        panel.currentFileChanged.emit(None)  # queue finished

        self.wait(500)
        # Should emit a needs-resolution update WITH message, but not finalize.
        self.assertGreaterEqual(spyItemStatus.count(), 2)
        last = spyItemStatus.at(spyItemStatus.count() - 1)
        self.assertEqual(CherryPickItemStatus.NEEDS_RESOLUTION, last[1])
        self.assertIn("nope", last[2])
        self.assertEqual(0, panel.startFinalizeCalls)

        # User retries: a new current file starts, which clears the failure latch.
        panel.currentFileChanged.emit("a.txt")
        panel.currentFileChanged.emit(None)

        self.wait(500)
        self.assertEqual(1, panel.startFinalizeCalls)

    def test_finalize_resolved_marks_picked_and_finishes(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        sha1 = "0123456789abcdef"

        with patch("qgitc.cherrypicksession.Git.cherryPick", return_value=(1, "conflicts", "")), patch(
            "qgitc.cherrypicksession.Git.isCherryPicking", return_value=True
        ), patch("qgitc.cherrypicksession.Git.conflictFiles", return_value=["a.txt"]):
            spyFinished = QSignalSpy(session.finished)
            spyItemStatus = QSignalSpy(session.itemStatusChanged)

            session.start(
                items=[CherryPickItem(sha1=sha1)],
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
            )

            self._waitForSpy(spyItemStatus)  # needs-resolution

        with patch("qgitc.cherrypicksession.Git.isCherryPicking", return_value=False), patch(
            "qgitc.cherrypicksession.Git.conflictFiles", return_value=[]
        ):
            # queue finished; triggers finalize
            panel.currentFileChanged.emit(None)
            self.wait(500)
            panel.finalizeOutcome.emit(ResolveOutcome(
                status=ResolveOutcomeStatus.RESOLVED))

            self._waitForSpy(spyFinished)

        # After finalize resolved, item should become picked.
        self.assertGreaterEqual(spyItemStatus.count(), 2)
        self.assertEqual(
            CherryPickItemStatus.PICKED,
            spyItemStatus.at(spyItemStatus.count() - 1)[1],
        )

        ok, aborted, needReload, _ = spyFinished.at(0)
        self.assertTrue(ok)
        self.assertFalse(aborted)
        self.assertTrue(needReload)

    def test_finalize_resolved_loops_if_conflicts_remain(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        sha1 = "0123456789abcdef"

        with patch("qgitc.cherrypicksession.Git.cherryPick", return_value=(1, "conflicts", "")), patch(
            "qgitc.cherrypicksession.Git.isCherryPicking", return_value=True
        ), patch("qgitc.cherrypicksession.Git.conflictFiles", return_value=["a.txt"]):
            spyItemStatus = QSignalSpy(session.itemStatusChanged)
            session.start(
                items=[CherryPickItem(sha1=sha1)],
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
            )
            self._waitForSpy(spyItemStatus)

        # Finalize succeeds, but git still reports conflicts remaining.
        with patch("qgitc.cherrypicksession.Git.isCherryPicking", return_value=True), patch(
            "qgitc.cherrypicksession.Git.conflictFiles", return_value=["b.txt"]
        ):
            panel.finalizeOutcome.emit(ResolveOutcome(
                status=ResolveOutcomeStatus.RESOLVED))

        self.wait(500)
        self.assertEqual(["b.txt"], panel.setConflictFilesCalls[-1])
        self.assertEqual(2, panel.startResolveAllCalls)

    def test_abort_during_conflict_resolution_aborts_operation(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        sha1 = "0123456789abcdef"

        with patch("qgitc.cherrypicksession.Git.cherryPick", return_value=(1, "conflicts", "")), patch(
            "qgitc.cherrypicksession.Git.isCherryPicking", return_value=True
        ), patch("qgitc.cherrypicksession.Git.conflictFiles", return_value=["a.txt"]), patch(
            "qgitc.cherrypicksession.Git.cherryPickAbort", return_value=(0, "", "")
        ):
            spyFinished = QSignalSpy(session.finished)
            session.start(
                items=[CherryPickItem(sha1=sha1)],
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
            )

            # Wait until we're in the conflict-resolution phase.
            self.wait(1000, lambda: panel.startResolveAllCalls == 0)
            self.assertGreaterEqual(panel.startResolveAllCalls, 1)

            # Now abort safely, while in conflict resolution.
            session.requestAbortSafely()
            self.assertEqual(1, panel.requestAbortSafelyCalls)

            panel.abortSafePointReached.emit()
            self._waitForSpy(spyFinished)

        ok, aborted, _, message = spyFinished.at(0)
        self.assertFalse(ok)
        self.assertTrue(aborted)
        self.assertTrue(message)

    def test_patch_pick_conflict_starts_am_resolution(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        sha1 = "0123456789abcdef"

        with patch("qgitc.cherrypicksession.Git.cherryPick", return_value=(1, "fatal: bad object", "")), patch(
            "qgitc.cherrypicksession.Git.isCherryPicking", return_value=False
        ), patch.object(CherryPickSession, "_pickFromAnotherRepo", return_value=(1, "am conflict", None)), patch(
            "qgitc.cherrypicksession.Git.isApplying", return_value=True
        ), patch("qgitc.cherrypicksession.Git.conflictFiles", return_value=["p.txt"]):
            spyConflicts = QSignalSpy(session.conflictsDetected)
            spyItemStatus = QSignalSpy(session.itemStatusChanged)

            session.start(
                items=[CherryPickItem(sha1=sha1)],
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
                allowPatchPick=True,
            )

            self._waitForSpy(spyItemStatus)
            self._waitForSpy(spyConflicts)

        self.assertEqual(CherryPickItemStatus.NEEDS_RESOLUTION,
                         spyItemStatus.at(0)[1])
        self.assertEqual(ResolveOperation.AM, spyConflicts.at(0)[0])
        self.assertEqual(["p.txt"], list(spyConflicts.at(0)[1]))
        self.assertEqual(1, panel.startResolveAllCalls)

    def test_abort_while_cherrypick_in_progress_aborts(self):
        panel = _FakeResolvePanel(self.app)
        session = CherryPickSession(resolvePanel=panel, parent=self.app)

        sha1 = "0123456789abcdef"

        with patch("qgitc.cherrypicksession.Git.cherryPick", return_value=(1, "conflicts", "")), patch(
            "qgitc.cherrypicksession.Git.isCherryPicking", return_value=True
        ), patch("qgitc.cherrypicksession.Git.cherryPickAbort", return_value=(0, "", "")):
            spyFinished = QSignalSpy(session.finished)

            session.start(
                items=[CherryPickItem(sha1=sha1)],
                targetBaseRepoDir=".",
                sourceBaseRepoDir=".",
                recordOrigin=True,
            )
            # Abort quickly before the task delivers its finished signal.
            session.requestAbortSafely()

            self._waitForSpy(spyFinished)

        ok, aborted, _, _ = spyFinished.at(0)
        self.assertFalse(ok)
        self.assertTrue(aborted)
