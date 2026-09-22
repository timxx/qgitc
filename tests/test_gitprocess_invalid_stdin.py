# -*- coding: utf-8 -*-

import os
import unittest
from unittest.mock import patch

from qgitc.gitutils import Git, GitProcess
from tests.base import TestBase


@unittest.skipUnless(os.name == "nt", "Windows-only handle semantics")
class TestGitProcessInvalidStdin(TestBase):

    def testPopenWithInvalidStdinHandle(self):
        """GitProcess must not depend on the parent's console stdin handle.

        When qgitc runs as a GUI process without a valid console, the
        inherited stdin handle is stale and subprocess.Popen(stdin=None)
        fails in _make_inheritable with WinError 6 (句柄无效).
        """
        import _winapi

        realGetStdHandle = _winapi.GetStdHandle

        def fakeGetStdHandle(stdHandleId):
            if stdHandleId == _winapi.STD_INPUT_HANDLE:
                # Simulate a stale/invalid stdin handle as seen in
                # console-less GUI processes: a non-NULL handle value
                # that is no longer valid (DuplicateHandle -> WinError 6).
                # Note: -1 (INVALID_HANDLE_VALUE) would NOT work here as it
                # is the current-process pseudo-handle and duplicates fine.
                return 0x0000CAFE
            return realGetStdHandle(stdHandleId)

        with patch("_winapi.GetStdHandle", fakeGetStdHandle):
            process = GitProcess(Git.REPO_DIR, ["version"])
            output, error = process.communicate()

        self.assertIsNotNone(output)
        self.assertIn(b"git version", output)
