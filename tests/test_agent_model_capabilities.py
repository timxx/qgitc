# -*- coding: utf-8 -*-

import unittest

from qgitc.models.openaicompat import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_OUTPUT_TOKENS,
    lookup_context_window,
)


class TestModelCapabilities(unittest.TestCase):

    def test_lookup_known_prefix_llama31(self):
        self.assertEqual(lookup_context_window("llama3.1:8b"), 131072)

    def test_lookup_known_prefix_case_insensitive(self):
        self.assertEqual(lookup_context_window("LLAMA3.1:8B"), 131072)

    def test_overlap_safety_llama31_before_llama3(self):
        self.assertEqual(lookup_context_window("llama3.1"), 131072)
        self.assertEqual(lookup_context_window("llama3:instruct"), 8192)

    def test_lookup_unknown_prefix_returns_default(self):
        self.assertEqual(lookup_context_window("some-unknown-model"), DEFAULT_CONTEXT_WINDOW)

    def test_lookup_non_match_boundary_returns_default(self):
        self.assertEqual(lookup_context_window("llama3x"), DEFAULT_CONTEXT_WINDOW)

    def test_default_max_output_tokens(self):
        self.assertEqual(DEFAULT_MAX_OUTPUT_TOKENS, 4096)


if __name__ == "__main__":
    unittest.main()
