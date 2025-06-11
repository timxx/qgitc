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
