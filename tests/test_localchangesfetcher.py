import os

from PySide6.QtTest import QSignalSpy

from qgitc.gitutils import Git
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
        self.assertEqual(fetcher.untrackedFiles, [])

        # Ensure processes are cleaned up before fetcher is deleted
        fetcher.cancel()


class TestLocalChangesFetcherWithRepo(TestBase):
    """Tests that require a real git repository."""

    def testCleanRepo(self):
        """No local changes at all."""
        fetcher = LocalChangesFetcher(self.gitDir.name)
        spyFinished = QSignalSpy(fetcher.finished)
        fetcher.fetch()
        self.wait(1000, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)

        self.assertFalse(fetcher.hasLCC)
        self.assertFalse(fetcher.hasLUC)
        self.assertEqual(fetcher.untrackedFiles, [])

        fetcher.cancel()

    def testUnstagedChanges(self):
        """Modify a tracked file without staging."""
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Modified content")

        fetcher = LocalChangesFetcher(self.gitDir.name)
        spyFinished = QSignalSpy(fetcher.finished)
        fetcher.fetch()
        self.wait(1000, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)

        self.assertFalse(fetcher.hasLCC)
        self.assertTrue(fetcher.hasLUC)
        self.assertEqual(fetcher.untrackedFiles, [])

        fetcher.cancel()

    def testStagedChanges(self):
        """Stage a change."""
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Modified content")
        Git.addFiles(repoDir=self.gitDir.name, files=["README.md"])

        fetcher = LocalChangesFetcher(self.gitDir.name)
        spyFinished = QSignalSpy(fetcher.finished)
        fetcher.fetch()
        self.wait(1000, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)

        self.assertTrue(fetcher.hasLCC)
        self.assertFalse(fetcher.hasLUC)
        self.assertEqual(fetcher.untrackedFiles, [])

        fetcher.cancel()

    def testUntrackedFiles(self):
        """Create a new untracked file."""
        with open(os.path.join(self.gitDir.name, "new_file.py"), "w") as f:
            f.write("print('new')")

        fetcher = LocalChangesFetcher(self.gitDir.name)
        spyFinished = QSignalSpy(fetcher.finished)
        fetcher.fetch()
        self.wait(1000, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)

        self.assertFalse(fetcher.hasLCC)
        # Untracked files make hasLUC true
        self.assertTrue(fetcher.hasLUC)
        self.assertEqual(fetcher.untrackedFiles, ["new_file.py"])

        fetcher.cancel()

    def testUntrackedAndModified(self):
        """Both untracked file and modified tracked file."""
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Modified content")
        with open(os.path.join(self.gitDir.name, "new_file.py"), "w") as f:
            f.write("print('new')")

        fetcher = LocalChangesFetcher(self.gitDir.name)
        spyFinished = QSignalSpy(fetcher.finished)
        fetcher.fetch()
        self.wait(1000, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)

        self.assertFalse(fetcher.hasLCC)
        self.assertTrue(fetcher.hasLUC)
        self.assertIn("new_file.py", fetcher.untrackedFiles)

        fetcher.cancel()

    def testAllThree(self):
        """Staged, unstaged, and untracked simultaneously."""
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Staged change")
        Git.addFiles(repoDir=self.gitDir.name, files=["README.md"])

        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Unstaged change")

        with open(os.path.join(self.gitDir.name, "new_file.py"), "w") as f:
            f.write("print('new')")

        fetcher = LocalChangesFetcher(self.gitDir.name)
        spyFinished = QSignalSpy(fetcher.finished)
        fetcher.fetch()
        self.wait(1000, lambda: spyFinished.count() == 0)
        self.assertEqual(spyFinished.count(), 1)

        self.assertTrue(fetcher.hasLCC)
        self.assertTrue(fetcher.hasLUC)
        self.assertIn("new_file.py", fetcher.untrackedFiles)

        fetcher.cancel()
