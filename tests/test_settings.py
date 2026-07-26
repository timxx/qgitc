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

    def testSubmodulesCacheWithNoneRepoDir(self):
        """setSubmodulesCache should handle None repoDir gracefully."""
        # submodulesCache already handles None
        submodules = self.settings.submodulesCache(None)
        self.assertEqual(submodules, [])

        # setSubmodulesCache should also handle None without crashing
        self.settings.setSubmodulesCache(None, ["sub1", "sub2"])

        # verify it didn't break anything
        self.settings.setSubmodulesCache(
            Git.REPO_DIR, ["submodule1"])
        submodules = self.settings.submodulesCache(Git.REPO_DIR)
        self.assertEqual(submodules, ["submodule1"])

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

    def testLocalLlmProviders_DefaultEmpty(self):
        self.assertEqual(self.settings.localLlmProviders(), [])

    def testLocalLlmProviders_MigratesLegacySettings(self):
        self.settings.beginGroup("llm")
        self.settings.setValue("localServer", "http://127.0.0.1:11434/v1")
        self.settings.setValue("localAuth", "Bearer abc")
        self.settings.setValue("customHeaders", {"X-Test": "1"})
        self.settings.endGroup()

        providers = self.settings.localLlmProviders()
        self.assertEqual(len(providers), 1)
        provider = providers[0]
        self.assertEqual(provider.get("name"), "OpenAI Compatible")
        self.assertEqual(provider.get("url"), "http://127.0.0.1:11434/v1")
        self.assertEqual(provider.get("headers", {}).get("X-Test"), "1")
        self.assertEqual(
            provider.get("headers", {}).get("Authorization"), "Bearer abc")

        self.settings.beginGroup("llm")
        self.assertFalse(self.settings.contains("localServer"))
        self.assertFalse(self.settings.contains("localAuth"))
        self.assertFalse(self.settings.contains("customHeaders"))
        self.settings.endGroup()

    def testCompositeModePerRepoDefault(self):
        """Per-repo composite mode should be None by default (use global)"""
        repoName = "test/repo1"
        self.assertIsNone(self.settings.compositeModePerRepo(repoName))

    def testCompositeModePerRepoSet(self):
        """Should be able to set per-repo composite mode"""
        repoName = "test/repo1"
        
        # Set to True
        self.settings.setCompositeModePerRepo(repoName, True)
        self.assertTrue(self.settings.compositeModePerRepo(repoName))
        
        # Set to False
        self.settings.setCompositeModePerRepo(repoName, False)
        self.assertFalse(self.settings.compositeModePerRepo(repoName))

    def testCompositeModePerRepoClearOverride(self):
        """Setting per-repo to None should clear the override"""
        repoName = "test/repo1"
        
        # Set to True
        self.settings.setCompositeModePerRepo(repoName, True)
        self.assertTrue(self.settings.compositeModePerRepo(repoName))
        
        # Clear by setting to None
        self.settings.setCompositeModePerRepo(repoName, None)
        self.assertIsNone(self.settings.compositeModePerRepo(repoName))

    def testCompositeModeUsesPerRepoWhenSet(self):
        """isCompositeMode(repoName) should use per-repo value when set"""
        repoName = "test/repo1"
        
        # Set global to False
        self.settings.setCompositeMode(False)
        
        # Per-repo override to True
        self.settings.setCompositeModePerRepo(repoName, True)
        
        # Effective should be True (per-repo override)
        self.assertTrue(self.settings.isCompositeMode(repoName))

    def testCompositeModeUsesGlobalWhenNotSet(self):
        """isCompositeMode(repoName) should use global when per-repo not set"""
        repoName = "test/repo1"
        
        # Set global to True
        self.settings.setCompositeMode(True)
        
        # Per-repo override not set (None)
        self.assertIsNone(self.settings.compositeModePerRepo(repoName))
        
        # Effective should be True (global)
        self.assertTrue(self.settings.isCompositeMode(repoName))

    def testCompositeModePerRepoIndependent(self):
        """Different repos should have independent per-repo settings"""
        repo1 = "test/repo1"
        repo2 = "test/repo2"
        
        self.settings.setCompositeModePerRepo(repo1, True)
        self.settings.setCompositeModePerRepo(repo2, False)
        
        self.assertTrue(self.settings.compositeModePerRepo(repo1))
        self.assertFalse(self.settings.compositeModePerRepo(repo2))

    def testCompositeModePerRepoIgnoresEmpty(self):
        """Setting per-repo with empty repoName should be ignored"""
        # Should not crash with empty string
        self.settings.setCompositeModePerRepo("", True)
        self.assertIsNone(self.settings.compositeModePerRepo(""))
        
        # Should not crash with None
        self.settings.setCompositeModePerRepo(None, True)
        self.assertIsNone(self.settings.compositeModePerRepo(None))
