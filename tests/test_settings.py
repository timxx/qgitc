# -*- coding: utf-8 -*-
from qgitc.gitutils import Git
from qgitc.settings import Settings
from tests.base import TestBase


class TestSettings(TestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.settings = Settings(testing=True)

    @classmethod
    def tearDownClass(cls):
        cls.settings.clear()
        del cls.settings
        super().tearDownClass()

    def testSubmodules(self):
        submodules = self.settings.submodulesCache(Git.REPO_DIR)
        self.assertTrue(isinstance(submodules, list))

        self.settings.setSubmodulesCache(Git.REPO_DIR, ["submodule1", "submodule2"])
        submodules = self.settings.submodulesCache(Git.REPO_DIR)
        self.assertEqual(submodules, ["submodule1", "submodule2"])
