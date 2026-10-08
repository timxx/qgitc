# -*- coding: utf-8 -*-

import os
import unittest
from typing import List

from PySide6.QtTest import QSignalSpy

from qgitc.common import Commit
from qgitc.gitutils import Git
from qgitc.logsfetcherimpl import LogsFetcherImpl
from qgitc.logsfetcherqprocessworker import LogsFetcherQProcessWorker
from tests.base import TestBase, createRepo


class TestMakeGitArgsBranchConflict(unittest.TestCase):
    """The revision must be separated from the paths by "--".

    Without the separator git cannot tell whether an argument that is both a
    revision and a path is meant as a revision, and `git log` dies with
    "fatal: ambiguous argument '<branch>': both revision and filename".
    """

    def testBranchNotFollowedByPath(self):
        args, branch = LogsFetcherImpl.makeGitArgs(("crbot", None))

        self.assertEqual(branch, b"crbot")
        self.assertIn("crbot", args)
        self.assertEqual(args[-1], "--",
                         "the revision list must be terminated explicitly")
        self.assertLess(args.index("crbot"), args.index("--"))

    def testBranchWithBoundaryStillSeparated(self):
        args, _ = LogsFetcherImpl.makeGitArgs(("crbot", None))

        self.assertLess(args.index("--boundary"), args.index("--"),
                        "--boundary is an option and must stay before --")

    def testBranchWithFilterPathSeparated(self):
        args, _ = LogsFetcherImpl.makeGitArgs(("crbot", ["--author=foo", "src"]))

        index = args.index("--author=foo")
        self.assertEqual(args[index - 1], "crbot")
        self.assertEqual(args[index + 1], "--")
        self.assertEqual(args[-1], "src")

    def testPathArgsKeepSingleSeparator(self):
        args, _ = LogsFetcherImpl.makeGitArgs((None, ["--follow", "--", "f.py"]))

        self.assertEqual(args.count("--"), 1)
        self.assertEqual(args[-1], "f.py")

    def testRevisionRangeNotTreatedAsPath(self):
        args, _ = LogsFetcherImpl.makeGitArgs((None, ["main..crbot"]))

        self.assertEqual(args[-2], "main..crbot")
        self.assertEqual(args[-1], "--")


class TestLogsFetcherBranchConflict(TestBase):
    """Regression test: a branch sharing its name with a repository directory.

    QGitc displays nested repositories (and submodules) by their directory
    name, so a "project" directory named like the current branch is common.
    Because the branch name then also names a path in the repository, every
    log fetch of that branch used to fail with::

        fatal: ambiguous argument 'crbot': both revision and filename

    and the main window popped up an error dialog on open.
    """

    PROJECT_NAME = "crbot"

    def doCreateRepo(self):
        super().doCreateRepo()

        Git.checkOutput(["branch", "-m", self.PROJECT_NAME],
                        repoDir=self.gitDir.name)

        # the nested repository (project) shares its name with the branch
        projectDir = os.path.join(self.gitDir.name, self.PROJECT_NAME)
        createRepo(projectDir, "https://foo.com/bar/{0}.git".format(
            self.PROJECT_NAME))

    def collectLogs(self, spyLogsAvailable):
        logs: List[Commit] = []
        for i in range(spyLogsAvailable.count()):
            payload = spyLogsAvailable.at(i)[0]
            if isinstance(payload, tuple):
                allLogs, _ = payload
                logs.extend(allLogs)
            else:
                logs.extend(payload)
        return logs

    def assertFetchedWithoutError(self, submodules):
        worker = LogsFetcherQProcessWorker(
            submodules, self.gitDir.name, False, self.PROJECT_NAME, None)
        spyFinished = QSignalSpy(worker.fetchFinished)
        spyLogsAvailable = QSignalSpy(worker.logsAvailable)
        worker.run()

        self.wait(1000, lambda: spyFinished.count() == 0)
        self.assertNotIn(b"ambiguous argument", worker.errorData)

        self.assertEqual(spyFinished.count(), 1)
        self.assertEqual(spyFinished.at(0)[0], 0)
        self.assertEqual(worker.errorData, b'')

        logs = self.collectLogs(spyLogsAvailable)
        self.assertGreaterEqual(len(logs), 2)
        return logs

    def testFetchSingleRepo(self):
        logs = self.assertFetchedWithoutError(None)

        self.assertEqual(logs[-1].comments, "Initial commit")

    def testFetchCompositeRepo(self):
        logs = self.assertFetchedWithoutError(["."])

        self.assertEqual(logs[-1].comments, "Initial commit")
