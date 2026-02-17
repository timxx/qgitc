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

    def testToolExecutionStrategy(self):
        # Test default strategy
        self.assertEqual(self.settings.toolExecutionStrategy(), 0)

        # Test setting to aggressive strategy (1)
        self.settings.setToolExecutionStrategy(1)
        self.assertEqual(self.settings.toolExecutionStrategy(), 1)

        # Test setting to safe strategy (2)
        self.settings.setToolExecutionStrategy(2)
        self.assertEqual(self.settings.toolExecutionStrategy(), 2)

        # Test setting to all auto strategy (3)
        self.settings.setToolExecutionStrategy(3)
        self.assertEqual(self.settings.toolExecutionStrategy(), 3)

        # Test setting back to default
        self.settings.setToolExecutionStrategy(0)
        self.assertEqual(self.settings.toolExecutionStrategy(), 0)
