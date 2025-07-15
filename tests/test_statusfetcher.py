
import os
from unittest.mock import MagicMock

from qgitc.gitutils import Git
from qgitc.statusfetcher import _fetchStatusGit, _fetchStatusGit2
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

    def testGit2Status(self):
        submodule, status = _fetchStatusGit2(
            ".", (True, False), None)

        self.assertEqual(submodule, ".")
        self.assertEqual(len(status), 0)

        submodule, status = _fetchStatusGit2(
            "subRepo", (True, False), None)
        self.assertEqual(submodule, "subRepo")
        self.assertEqual(len(status), 0)

    def testGitStatus2Modified(self):
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Test content")

        submodule, status = _fetchStatusGit2('.', (True, False), None)

        self.assertEqual(submodule, '.')
        self.assertIsInstance(status, list)
        self.assertEqual(len(status), 1)

        flags, file, oldFile = status[0]
        self.assertEqual(flags, " M")
        self.assertEqual(file, "README.md")
        self.assertIsNone(oldFile)

        Git.addFiles(None, ["README.md"])
        with open(os.path.join(self.gitDir.name, "README.md"), "a+") as f:
            f.write("Test 2")

        submodule, status = _fetchStatusGit2(None, (True, False), None)

        self.assertIsNone(submodule)
        self.assertEqual(len(status), 1)

        flags, file, oldFile = status[0]
        self.assertEqual(flags, "MM")
        self.assertEqual(file, "README.md")
        self.assertIsNone(oldFile)

        with open(os.path.join(self.gitDir.name, "subRepo", "test.py"), "a+") as f:
            f.write("# Test")

        submodule, status = _fetchStatusGit2("subRepo", (True, False), None)
        self.assertEqual(submodule, "subRepo")
        self.assertEqual(len(status), 1)

        flags, file, oldFile = status[0]
        self.assertEqual(flags, " M")
        self.assertEqual(file, f"subRepo{os.sep}test.py")
        self.assertIsNone(oldFile)

    def testGit2StatusRenamed(self):
        os.rename(os.path.join(self.gitDir.name, "README.md"),
                  os.path.join(self.gitDir.name, "new.md"))

        submodule, status = _fetchStatusGit2(".", (True, False), None)

        self.assertEqual(submodule, ".")
        # we are not add yet
        self.assertEqual(len(status), 2)

        def _checkDelete():
            self.assertIsNone(oldFile)
            if flags == " D":
                self.assertEqual(file, "README.md")
            elif flags == "??":
                self.assertEqual(file, "new.md")
            else:
                self.fail(f"Unexpected status: {flags} for file {file}")

        flags, file, oldFile = status[0]
        _checkDelete()

        flags, file, oldFile = status[1]
        _checkDelete()

        Git.addFiles(None, ["new.md"])
        submodule, status = _fetchStatusGit2(".", (True, False), None)

        def _checkAdd():
            self.assertIsNone(oldFile)
            if flags == " D":
                self.assertEqual(file, "README.md")
            elif flags == "A ":
                self.assertEqual(file, "new.md")
            else:
                self.fail(f"Unexpected status: {flags} for file {file}")

        self.assertEqual(len(status), 2)
        flags, file, oldFile = status[0]
        _checkAdd()

        flags, file, oldFile = status[1]
        _checkAdd()

        Git.addFiles(None, ["README.md"])
        submodule, status = _fetchStatusGit2(".", (True, False), None)
        # TODO: support renamed
        self.assertEqual(len(status), 2)
        flags, file, oldFile = status[0]
        # self.assertEqual(flags, "R ")
        # self.assertEqual(file, "new.md")
        # self.assertEqual(oldFile, "README.md")
