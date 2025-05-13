# -*- coding: utf-8 -*-
import os
import tempfile
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from qgitc.findsubmodules import FindSubmoduleThread
from qgitc.gitutils import Git
from tests.base import TestBase, addSubmoduleRepo, createRepo


class TestFindSubmodule(TestBase):

    def testSingleRepo(self):
        thread = FindSubmoduleThread(Git.REPO_DIR)
        thread.start()
        self.wait(10000, lambda: not thread.isFinished())

        self.assertTrue(thread.isFinished())
        self.assertEqual(thread.submodules, [])

    def testSubmoduleRepo(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as dir:
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
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as dir:
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
