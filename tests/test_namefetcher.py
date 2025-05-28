# -*- coding: utf-8 -*-

from qgitc.gitutils import Git
from qgitc.namefetcher import NameFetcher
from tests.base import TestBase


class TestNameFetcher(TestBase):

    def doCreateRepo(self):
        super().doCreateRepo()

        Git.checkOutput(["mv", "test.py", "foo.py"], repoDir=self.gitDir.name)
        Git.commit("Renamed test.py to foo.py", repoDir=self.gitDir.name)

    def testFetch(self):
        sha1Names = {}

        def _updateNames(data):
            for sha1, name in data:
                sha1Names[sha1] = name

        fetcher = NameFetcher()
        fetcher.dataAvailable.connect(_updateNames)
        fetcher.fetch("foo.py")
        self.wait(1000, lambda: fetcher._process is not None)

        self.assertEqual(len(sha1Names), 2)

        names = set(sha1Names.values())
        self.assertSetEqual(names, {"test.py", "foo.py"})
