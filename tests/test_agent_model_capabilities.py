# -*- coding: utf-8 -*-

import unittest
from unittest.mock import patch

from qgitc.llm import AiParameters
from qgitc.models.githubcopilot import GithubCopilot
from qgitc.models.openaicompat import lookupModelCapabilities
from tests.base import TestBase


class TestModelCapabilities(unittest.TestCase):

    def test_lookup_known_prefix_llama31(self):
        self.assertEqual(lookupModelCapabilities("llama3.1:8b").context_window, 131072)

    def test_lookup_known_prefix_case_insensitive(self):
        self.assertEqual(lookupModelCapabilities("LLAMA3.1:8B").context_window, 131072)

    def test_overlap_safety_llama31_before_llama3(self):
        self.assertEqual(lookupModelCapabilities("llama3.1").context_window, 131072)
        self.assertIsNone(lookupModelCapabilities("llama3:instruct"))

    def test_lookup_unknown_prefix_returns_default(self):
        self.assertIsNone(lookupModelCapabilities("some-unknown-model"))

    def test_lookup_non_match_boundary_returns_default(self):
        self.assertIsNone(lookupModelCapabilities("llama3x"))


class TestGithubCopilotModelIdImmutability(TestBase):

    def doCreateRepo(self):
        pass  # No repo needed

    def test_queryAsync_does_not_mutate_modelId(self):
        model = GithubCopilot(model="default-model", parent=self.app)
        # Explicitly set to our sentinel to override any _ensureDefaultModel side-effect
        model.modelId = "default-model"

        params = AiParameters()
        params.model = "other-model"

        with patch.object(GithubCopilot, 'isTokenValid', return_value=True), \
             patch.object(model, '_updateModels'), \
             patch.object(model, '_waitForModelsReady'), \
             patch.object(model, '_doQuery'):
            model._token = "fake-token"
            model.queryAsync(params)

        self.assertEqual(model.modelId, "default-model")


if __name__ == "__main__":
    unittest.main()
