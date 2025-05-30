# -*- coding: utf-8 -*-
from qgitc.gitutils import Git
from qgitc.settings import Settings
from tests.base import TestBase


class TestSettings(TestBase):
    def setUp(self):
        super().setUp()
        self.settings = Settings(testing=True)

    def tearDown(self):
        del self.settings
        super().tearDown()

    def doCreateRepo(self):
        pass

    def testSubmodules(self):
        submodules = self.settings.submodulesCache(Git.REPO_DIR)
        self.assertTrue(isinstance(submodules, list))

        self.settings.setSubmodulesCache(
            Git.REPO_DIR, ["submodule1", "submodule2"])
        submodules = self.settings.submodulesCache(Git.REPO_DIR)
        self.assertEqual(submodules, ["submodule1", "submodule2"])

    def testDefaultLlmModel(self):
        # avoid `GithubCopilot` named changed without knowing
        self.assertEqual(self.settings.defaultLlmModel(), "GithubCopilot")

        self.settings.setDefaultLlmModel("TestModel")
        self.assertEqual(self.settings.defaultLlmModel(), "TestModel")
