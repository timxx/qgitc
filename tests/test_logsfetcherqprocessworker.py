import os
from typing import List

from PySide6.QtTest import QSignalSpy

from qgitc.common import Commit
from qgitc.gitutils import Git
from qgitc.logsfetcherqprocessworker import LogsFetcherQProcessWorker
from tests.base import TestBase


class TestLogsFetcherQProcessWorker(TestBase):

    def createSubRepo(self):
        return True

    def testFetch(self):
        submodules = [".", "subRepo"]
        worker = LogsFetcherQProcessWorker(
            submodules, self.gitDir.name, False, "main", None)
        spyFinished = QSignalSpy(worker.fetchFinished)
        spyLogsAvailable = QSignalSpy(worker.logsAvailable)
        spyLocalChangesAvailable = QSignalSpy(worker.localChangesAvailable)
        worker.run()

        self.wait(100, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)
        self.assertEqual(spyFinished.at(0)[0], 0)

        self.assertEqual(spyLogsAvailable.count(), 1)
        logs = spyLogsAvailable.at(0)[0]
        self.assertIsInstance(logs, list)
        self.assertEqual(len(logs), 3)

        self.assertEqual(spyLocalChangesAvailable.count(), 1)
        lccCommit: Commit = spyLocalChangesAvailable.at(0)[0]
        lucCommit: Commit = spyLocalChangesAvailable.at(0)[1]
        self.assertEqual(lccCommit.sha1, '')
        self.assertEqual(lucCommit.sha1, '')

    def testFetchWithLocalChanges(self):
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Test content")

        submodules = [".", "subRepo"]
        worker = LogsFetcherQProcessWorker(
            submodules, self.gitDir.name, False, "main", None)
        spyFinished = QSignalSpy(worker.fetchFinished)
        spyLogsAvailable = QSignalSpy(worker.logsAvailable)
        spyLocalChangesAvailable = QSignalSpy(worker.localChangesAvailable)
        worker.run()

        self.wait(100, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)
        self.assertEqual(spyFinished.at(0)[0], 0)

        self.assertEqual(spyLogsAvailable.count(), 1)
        logs = spyLogsAvailable.at(0)[0]
        self.assertIsInstance(logs, list)
        self.assertEqual(len(logs), 3)

        self.assertEqual(spyLocalChangesAvailable.count(), 1)
        lccCommit: Commit = spyLocalChangesAvailable.at(0)[0]
        lucCommit: Commit = spyLocalChangesAvailable.at(0)[1]
        self.assertEqual(lccCommit.sha1, '')
        self.assertEqual(lucCommit.sha1, Git.LUC_SHA1)

        with open(os.path.join(self.gitDir.name, "test.py"), "a+") as f:
            f.write("print('Test')")

        Git.addFiles(repoDir=self.gitDir.name, files=["test.py"])

        worker = LogsFetcherQProcessWorker(
            submodules, self.gitDir.name, False, "main", None)
        spyLocalChangesAvailable = QSignalSpy(worker.localChangesAvailable)
        worker.run()

        self.wait(100, lambda: spyLocalChangesAvailable.count() == 0)
        self.assertEqual(spyLocalChangesAvailable.count(), 1)

        lccCommit, lucCommit = spyLocalChangesAvailable.at(0)
        self.assertEqual(lccCommit.sha1, Git.LCC_SHA1)
        self.assertEqual(lucCommit.sha1, Git.LUC_SHA1)

    def testFetchMainOnly(self):
        worker = LogsFetcherQProcessWorker(
            None, self.gitDir.name, False, "main", None)
        spyFinished = QSignalSpy(worker.fetchFinished)
        spyLogsAvailable = QSignalSpy(worker.logsAvailable)
        spyLocalChangesAvailable = QSignalSpy(worker.localChangesAvailable)
        worker.run()

        self.wait(100, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)
        self.assertEqual(spyFinished.at(0)[0], 0)

        logs: List[Commit] = []
        for i in range(spyLogsAvailable.count()):
            logs.extend(spyLogsAvailable.at(i)[0])

        self.assertEqual(len(logs), 3)
        self.assertEqual(logs[0].comments, "Add .gitignore")

        self.assertGreaterEqual(spyLogsAvailable.count(), 1)

        self.assertEqual(spyLocalChangesAvailable.count(), 1)
        lccCommit: Commit = spyLocalChangesAvailable.at(0)[0]
        lucCommit: Commit = spyLocalChangesAvailable.at(0)[1]
        self.assertEqual(lccCommit.sha1, '')
        self.assertEqual(lucCommit.sha1, '')
