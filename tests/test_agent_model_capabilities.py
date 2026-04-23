# -*- coding: utf-8 -*-

import unittest

from qgitc.models.openaicompat import lookupModelCapabilities


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

if __name__ == "__main__":
    unittest.main()
