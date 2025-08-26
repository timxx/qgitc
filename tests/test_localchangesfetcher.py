import os

from PySide6.QtTest import QSignalSpy

from qgitc.logsfetcherqprocessworker import LocalChangesFetcher
from tests.base import TestBase


class TestLocalChangesFetcher(TestBase):

    def doCreateRepo(self):
        pass

    def testNonExistsRepo(self):
        repoDir = "the_repo_should_not_exists"
        self.assertFalse(os.path.exists(repoDir))

        fetcher = LocalChangesFetcher(repoDir)
        spyFinished = QSignalSpy(fetcher.finished)
        fetcher.fetch()
        self.wait(1000, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)

        self.assertFalse(fetcher.hasLCC)
        self.assertFalse(fetcher.hasLUC)
