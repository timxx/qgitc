import os

from qgitc.gitutils import Git
from tests.base import TestBase


class TestGitUtils(TestBase):

    def createSubRepo(self):
        return True

    def testRestoreRepoFiles(self):
        # first renamed it to avoid `found` in subrepo
        process = Git.run(["mv", "README.md", "foo.md"])
        process.communicate()
        self.assertEqual(process.returncode, 0)

        Git.commit("Renamed README.md to foo.md")

        process = Git.run(["rm", "foo.md"])
        process.communicate()
        self.assertEqual(process.returncode, 0)

        os.chdir(os.path.join(self.gitDir.name, "subRepo"))

        repoFiles = {".": ["foo.md"]}
        error = Git.restoreRepoFiles(repoFiles, staged=True)
        self.assertIsNone(error)

    def testRawDiff(self):
        with open("test.dot", "w", encoding="utf-8") as f:
            pass
        with open("README.md", "a", encoding="utf-8") as f:
            f.write("# test")
        files = ["test.dot", "README.md"]
        self.assertIsNone(Git.addFiles(None, files))
        # git dosen't support *.dot, but we can still get the diff for README.md
        diff = Git.commitRawDiff(Git.LCC_SHA1, files)
        self.assertIsNotNone(diff)

        lines = diff.decode("utf-8").splitlines()
        self.assertIn("diff --git a/README.md b/README.md", lines)
        self.assertIn("+# test", lines)
        self.assertIn("diff --git a/test.dot b/test.dot", lines)
