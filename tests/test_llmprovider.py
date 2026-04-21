# -*- coding: utf-8 -*-

from qgitc.llmprovider import AiModelProvider
from tests.base import TestBase


class TestLlmProvider(TestBase):

    def doCreateRepo(self):
        pass

    def testModels_NoLocalProviderByDefault(self):
        models = AiModelProvider.models()
        keys = [m.modelKey for m in models]

        self.assertIn("GithubCopilot", keys)
        self.assertNotIn("LocalLLM", keys)

    def testModels_IncludeConfiguredLocalProviders(self):
        self.app.settings().setLocalLlmProviders([
            {
                "id": "provider-1",
                "name": "Ollama",
                "url": "http://127.0.0.1:11434/v1",
                "headers": {},
            },
            {
                "id": "provider-2",
                "name": "LM Studio",
                "url": "http://127.0.0.1:1234/v1",
                "headers": {"Authorization": "Bearer abc"},
            },
        ])

        models = AiModelProvider.models()
        localModels = [m for m in models if m.isLocal()]

        self.assertEqual(len(localModels), 2)
        self.assertEqual(localModels[0].displayName, "Ollama")
        self.assertEqual(localModels[1].displayName, "LM Studio")
        self.assertEqual(localModels[0].modelKey, "LocalLLM:provider-1")
        self.assertEqual(localModels[1].modelKey, "LocalLLM:provider-2")
