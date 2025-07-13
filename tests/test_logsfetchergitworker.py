import os
import unittest

from PySide6.QtTest import QSignalSpy

from qgitc.logsfetchergitworker import LogsFetcherGitWorker, _fetchLogs
from tests.base import TestBase


class TestLogsFetcherGitWorker(unittest.TestCase):
    def test_isSupportFilterArgs_with_empty_list(self):
        self.assertTrue(LogsFetcherGitWorker.isSupportFilterArgs([]))
        self.assertTrue(LogsFetcherGitWorker.isSupportFilterArgs(None))

    def test_isSupportFilterArgs_with_supported_args(self):
        args = ["--since=1 week ago", "--author=John"]
        self.assertTrue(LogsFetcherGitWorker.isSupportFilterArgs(args))

    def test_isSupportFilterArgs_with_mixed_args(self):
        args = ["--since=2 days ago", "--max-count=10", "--author=Alice"]
        self.assertTrue(LogsFetcherGitWorker.isSupportFilterArgs(args))
        args.append("--grep=fix")
        self.assertFalse(LogsFetcherGitWorker.isSupportFilterArgs(args))

    def test_isSupportFilterArgs_with_all_unsupported(self):
        args = ["--grep=fix", "--max-count=5"]
        self.assertFalse(LogsFetcherGitWorker.isSupportFilterArgs(args))


class TestLogsFetcherGitWorkerFetch(TestBase):

    def createSubRepo(self):
        return True

    def testFetch(self):
        submodules = [".", "subRepo"]
        worker = LogsFetcherGitWorker(
            submodules, self.gitDir.name, False, "main", None)
        spyFinished = QSignalSpy(worker.fetchFinished)
        spyLogsAvailable = QSignalSpy(worker.logsAvailable)
        worker.run()

        self.wait(100, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)
        self.assertEqual(spyFinished.at(0)[0], 0)

        self.assertEqual(spyLogsAvailable.count(), 1)
        logs = spyLogsAvailable.at(0)[0]
        self.assertIsInstance(logs, list)
        self.assertEqual(len(logs), 3)

    def testFetchWithLocalChanges(self):
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Test content")

        submodule, logs, hasLCC, hasLUC, error = _fetchLogs(
            None, self.gitDir.name, ("main", None), checkLocalChanges=True)

        self.assertEqual(submodule, None)
        self.assertGreater(len(logs), 2)

        self.assertFalse(hasLCC)
        self.assertTrue(hasLUC)
        self.assertIsNone(error)
