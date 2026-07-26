
import os
from unittest.mock import MagicMock, patch

from qgitc.gitutils import Git
from qgitc.statusfetcher import _fetchStatusGit
from tests.base import TestBase


class TestStatusFetcher(TestBase):

    def createSubRepo(self):
        return True

    def testGitStatus(self):
        cancelEvent = MagicMock()
        cancelEvent.isSet.return_value = False

        submodule, status = _fetchStatusGit(".", cancelEvent)
        self.assertIsNone(submodule)
        self.assertIsNone(status)

        submodule, status = _fetchStatusGit("subRepo", cancelEvent)
        self.assertIsNone(submodule)
        self.assertIsNone(status)

    def testGitStatusModified(self):
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Test content")

        cancelEvent = MagicMock()
        cancelEvent.isSet.return_value = False

        submodule, status = _fetchStatusGit(".", cancelEvent)

        self.assertEqual(submodule, ".")
        self.assertIsInstance(status, list)
        self.assertEqual(len(status), 1)

        flags, file, oldFile = status[0]
        self.assertEqual(flags, " M")
        self.assertEqual(file, "README.md")
        self.assertIsNone(oldFile)

        Git.addFiles(None, ["README.md"])
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Test 2")

        submodule, status = _fetchStatusGit(None, cancelEvent)
        self.assertIsNone(submodule)
        self.assertEqual(len(status), 1)

        flags, file, oldFile = status[0]
        self.assertEqual(flags, "MM")
        self.assertEqual(file, "README.md")
        self.assertIsNone(oldFile)

        with open(os.path.join(self.gitDir.name, "subRepo", "test.py"), "a+") as f:
            f.write("# Test")

        submodule, status = _fetchStatusGit("subRepo", cancelEvent)
        self.assertEqual(submodule, "subRepo")
        self.assertEqual(len(status), 1)

        flags, file, oldFile = status[0]
        self.assertEqual(flags, " M")
        self.assertEqual(file, f"subRepo{os.sep}test.py")
        self.assertIsNone(oldFile)

    def testGitStatusRenamed(self):
        cancelEvent = MagicMock()
        cancelEvent.isSet.return_value = False

        os.rename(os.path.join(self.gitDir.name, "README.md"),
                  os.path.join(self.gitDir.name, "new.md"))

        submodule, status = _fetchStatusGit(".", cancelEvent)

        self.assertEqual(submodule, ".")
        # we are not add yet
        self.assertEqual(len(status), 2)

        flags, file, oldFile = status[0]
        self.assertEqual(flags, " D")
        self.assertEqual(file, "README.md")
        self.assertIsNone(oldFile)

        flags, file, oldFile = status[1]
        self.assertEqual(flags, "??")
        self.assertEqual(file, "new.md")
        self.assertIsNone(oldFile)

        Git.addFiles(None, ["new.md"])
        submodule, status = _fetchStatusGit(None, cancelEvent)

        self.assertEqual(len(status), 2)
        flags, file, oldFile = status[0]
        self.assertEqual(flags, " D")
        self.assertEqual(file, "README.md")
        self.assertIsNone(oldFile)

        flags, file, oldFile = status[1]
        self.assertEqual(flags, "A ")
        self.assertEqual(file, "new.md")
        self.assertIsNone(oldFile)

        Git.addFiles(None, ["README.md"])
        submodule, status = _fetchStatusGit(None, cancelEvent)
        self.assertEqual(len(status), 1)
        flags, file, oldFile = status[0]
        self.assertEqual(flags, "R ")
        self.assertEqual(file, "new.md")
        self.assertEqual(oldFile, "README.md")

    def testGitStatusInvalidSubmoduleNoFallback(self):
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Test content")

        fakeSubmodule = os.path.join("Release", "sdk_header")
        os.makedirs(os.path.join(self.gitDir.name, fakeSubmodule, ".git"), exist_ok=True)

        cancelEvent = MagicMock()
        cancelEvent.isSet.return_value = False

        submodule, status = _fetchStatusGit(fakeSubmodule, cancelEvent)
        self.assertIsNone(submodule)
        self.assertIsNone(status)

