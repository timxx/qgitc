# -*- coding: utf-8 -*-
import os
import tempfile
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from qgitc.findsubmodules import FindSubmoduleThread
from qgitc.gitutils import Git
from tests.base import TemporaryDirectory, TestBase, addSubmoduleRepo, createRepo


class TestFindSubmodule(TestBase):

    def testSingleRepo(self):
        thread = FindSubmoduleThread(Git.REPO_DIR)
        thread.start()
        self.wait(10000, lambda: not thread.isFinished())

        self.assertTrue(thread.isFinished())
        self.assertEqual(thread.submodules, [])

    def testSubmoduleRepo(self):
        with TemporaryDirectory() as dir:
            mainRepo = os.path.join(dir, "mainRepo")
            createRepo(mainRepo)

            submoduleDir = os.path.join(dir, "submodule1")
            createRepo(submoduleDir)
            addSubmoduleRepo(mainRepo, submoduleDir, "submodule1")

            submoduleDir2 = os.path.join(dir, "submodule2")
            createRepo(submoduleDir2)
            addSubmoduleRepo(mainRepo, submoduleDir2, "hello/submodule2")

            with patch("os.walk") as mock_walk:
                thread = FindSubmoduleThread(mainRepo)
                thread.start()
                self.wait(10000, lambda: not thread.isFinished())

                self.assertTrue(thread.isFinished())
                self.assertSetEqual(set(thread.submodules), {
                    ".", "submodule1", "hello/submodule2"})

                mock_walk.assert_not_called()

    def testSubRepo(self):
        with TemporaryDirectory() as dir:
            createRepo(dir)
            createRepo(os.path.join(dir, "subrepo"))
            createRepo(os.path.join(dir, "dir1", "dir2", "dir3", "subrepo2"))

            thread = FindSubmoduleThread(dir)
            thread.start()
            self.wait(10000, lambda: not thread.isFinished())

            self.assertTrue(thread.isFinished())
            subrepo2 = os.path.join("dir1", "dir2", "dir3", "subrepo2")
            self.assertSetEqual(set(thread.submodules), {
                                ".", "subrepo", subrepo2})

    def testIgnoreFakeGitDirectory(self):
        with TemporaryDirectory() as dir:
            createRepo(dir)

            fakeRepoDir = os.path.join(dir, "Release", "sdk_header")
            os.makedirs(os.path.join(fakeRepoDir, ".git"), exist_ok=True)

            thread = FindSubmoduleThread(dir)
            thread.start()
            self.wait(10000, lambda: not thread.isFinished())

            self.assertTrue(thread.isFinished())
            self.assertEqual(thread.submodules, [])

    def testIgnoreDirectoryFromGitignoreDuringScan(self):
        with TemporaryDirectory() as dir:
            createRepo(dir)

            with open(os.path.join(dir, ".gitignore"), "w") as f:
                f.write("/release/\n")
            Git.addFiles(repoDir=dir, files=[".gitignore"])
            Git.commit("Ignore release", repoDir=dir)

            createRepo(os.path.join(dir, "release", "nestedRepo"))
            createRepo(os.path.join(dir, "visibleRepo"))

            thread = FindSubmoduleThread(dir)
            thread.start()
            self.wait(3000, lambda: not thread.isFinished())

            self.assertTrue(thread.isFinished())
            self.assertSetEqual(set(thread.submodules), {".", "visibleRepo"})

    def testKeepIgnoredNonBuildRepoDuringScan(self):
        with TemporaryDirectory() as dir:
            createRepo(dir)

            with open(os.path.join(dir, ".gitignore"), "w") as f:
                f.write("/vendorRepo/\n")
            Git.addFiles(repoDir=dir, files=[".gitignore"])
            Git.commit("Ignore vendorRepo", repoDir=dir)

            createRepo(os.path.join(dir, "vendorRepo"))
            createRepo(os.path.join(dir, "visibleRepo"))

            thread = FindSubmoduleThread(dir)
            thread.start()
            self.wait(3000, lambda: not thread.isFinished())

            self.assertTrue(thread.isFinished())
            self.assertSetEqual(set(thread.submodules),
                                {".", "vendorRepo", "visibleRepo"})

    def testIgnoreBuildLikeDirectoryNameByPrefixOrSuffix(self):
        with TemporaryDirectory() as dir:
            createRepo(dir)

            with open(os.path.join(dir, ".gitignore"), "w") as f:
                f.write("/release-candidate/\n")
                f.write("/hotfix-build/\n")
                f.write("/debug64/\n")
            Git.addFiles(repoDir=dir, files=[".gitignore"])
            Git.commit("Ignore build-like dirs", repoDir=dir)

            createRepo(os.path.join(dir, "release-candidate", "nestedRepo1"))
            createRepo(os.path.join(dir, "hotfix-build", "nestedRepo2"))
            createRepo(os.path.join(dir, "debug64", "nestedRepo3"))
            createRepo(os.path.join(dir, "visibleRepo"))

            thread = FindSubmoduleThread(dir)
            thread.start()
            self.wait(3000, lambda: not thread.isFinished())

            self.assertTrue(thread.isFinished())
            self.assertSetEqual(set(thread.submodules), {".", "visibleRepo"})
