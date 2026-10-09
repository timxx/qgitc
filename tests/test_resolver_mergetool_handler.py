# -*- coding: utf-8 -*-

from unittest.mock import patch

from PySide6.QtCore import QProcess
from PySide6.QtTest import QSignalSpy

from qgitc.resolver.enums import (
    ResolveFailureReason,
    ResolveOperation,
    ResolveOutcomeStatus,
)
from qgitc.resolver.handlers.mergetool import (
    GitMergetoolHandler,
    isNoUsableMergetoolOutput,
)
from qgitc.resolver.models import ResolveContext
from qgitc.resolver.services import ResolveServices
from tests.base import TestBase


class _Bytes:

    def __init__(self, data: bytes):
        self._data = data

    def data(self) -> bytes:
        return self._data


class _FakeProcess:

    def __init__(self, stdout: bytes = b"", stderr: bytes = b""):
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False
        self.writes = []

    def bytesAvailable(self) -> bool:
        return bool(self._stdout)

    def readAllStandardOutput(self):
        data, self._stdout = self._stdout, b""
        return _Bytes(data)

    def readAllStandardError(self):
        return _Bytes(self._stderr)

    def write(self, data):
        self.writes.append(data)

    def kill(self):
        self.killed = True


class _FakeManager:

    def __init__(self):
        self.events = []

    def emitEvent(self, ev):
        self.events.append(ev)

    def requestPrompt(self, prompt):
        pass


class TestGitMergetoolHandler(TestBase):

    def doCreateRepo(self):
        pass

    def _start(self, mergetoolName="kdiff3"):
        handler = GitMergetoolHandler()
        services = ResolveServices(runner=None)
        services.manager = _FakeManager()
        ctx = ResolveContext(
            repoDir=".",
            operation=ResolveOperation.CHERRY_PICK,
            sha1="0" * 40,
            path="a.cpp",
            mergetoolName=mergetoolName,
        )
        return handler, ctx, services

    def test_recognizes_output_of_a_missing_merge_tool(self):
        for text in (
            "Hit return to start merge resolution tool (vimdiff): ",
            "This message is displayed because 'merge.tool' is not configured.",
            "git config option merge.tool set to unknown tool: foo",
            "The merge tool kdiff3 is not available as 'kdiff3.exe'",
            "No known mergetool is available.",
            "Unknown mergetool foo",
            "error: mergetool.nosuchtool.cmd not set for tool 'nosuchtool'",
        ):
            self.assertTrue(isNoUsableMergetoolOutput(text), text)

        for text in (
            "",
            "Normal merge conflict for 'a.cpp':",
            "merge of a.cpp failed",
            "Resolved a.cpp",
        ):
            self.assertFalse(isNoUsableMergetoolOutput(text), text)

    def test_launch_names_the_merge_tool(self):
        handler, ctx, services = self._start(mergetoolName="kdiff3")

        with patch("qgitc.resolver.handlers.mergetool.QProcess") as mockProcess:
            handler.start(ctx, services)
            mockProcess.return_value.start.assert_called_once()

        # The status line must say which tool the window is waiting for.
        messages = [ev.message for ev in services.manager.events]
        self.assertTrue(any("kdiff3" in m for m in messages), messages)

    def test_no_tool_name_fails_without_launching_mergetool(self):
        handler, ctx, services = self._start(mergetoolName=None)
        spy = QSignalSpy(handler.finished)

        with patch("qgitc.resolver.handlers.mergetool.QProcess") as mockProcess:
            handler.start(ctx, services)
            mockProcess.return_value.start.assert_not_called()

        self.assertEqual(1, spy.count())
        handled, outcome = spy.at(0)
        self.assertTrue(handled)
        self.assertEqual(ResolveOutcomeStatus.FAILED, outcome.status)
        self.assertEqual(ResolveFailureReason.NO_MERGETOOL,
                         (outcome.details or {}).get("reason"))

    def test_missing_tool_output_is_reported_as_unconfigured(self):
        handler, ctx, services = self._start()
        handler._process = _FakeProcess(
            stdout=b"Normal merge conflict for 'a.cpp':\n",
            stderr=b"The merge tool kdiff3 is not available as 'kdiff3.exe'\n",
        )
        spy = QSignalSpy(handler.finished)

        handler._onFinished(1, None)

        self.assertEqual(1, spy.count())
        handled, outcome = spy.at(0)
        self.assertTrue(handled)
        self.assertEqual(ResolveOutcomeStatus.FAILED, outcome.status)
        self.assertEqual(ResolveFailureReason.NO_MERGETOOL,
                         (outcome.details or {}).get("reason"))

    def test_guess_prompt_aborts_instead_of_hanging(self):
        handler, ctx, services = self._start()
        handler._process = _FakeProcess(
            stdout=b"Hit return to start merge resolution tool (vimdiff): ")
        spy = QSignalSpy(handler.finished)

        handler._onStdout()
        self.assertTrue(handler._process.killed)
        # Never answer the prompt: a guessed tool is not a configured one.
        self.assertEqual([], handler._process.writes)

        handler._onFinished(1, None)
        self.assertEqual(1, spy.count())
        handled, outcome = spy.at(0)
        self.assertEqual(ResolveFailureReason.NO_MERGETOOL,
                         (outcome.details or {}).get("reason"))

    def test_plain_failure_keeps_git_error_message(self):
        handler, ctx, services = self._start()
        handler._process = _FakeProcess(stderr=b"merge of a.cpp failed\n")
        spy = QSignalSpy(handler.finished)

        handler._onFinished(1, None)

        self.assertEqual(1, spy.count())
        handled, outcome = spy.at(0)
        self.assertTrue(handled)
        self.assertEqual(ResolveOutcomeStatus.FAILED, outcome.status)
        self.assertIn("merge of a.cpp failed", outcome.message)
        self.assertNotEqual(ResolveFailureReason.NO_MERGETOOL,
                            (outcome.details or {}).get("reason"))

    def test_failed_start_reports_failure(self):
        handler, ctx, services = self._start()
        spy = QSignalSpy(handler.finished)

        with patch("qgitc.resolver.handlers.mergetool.QProcess") as mockProcess:
            handler.start(ctx, services)
            mockProcess.return_value.start.assert_called_once()

        handler._onErrorOccurred(QProcess.ProcessError.FailedToStart)

        self.assertEqual(1, spy.count())
        handled, outcome = spy.at(0)
        self.assertTrue(handled)
        self.assertEqual(ResolveOutcomeStatus.FAILED, outcome.status)
