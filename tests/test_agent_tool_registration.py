# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.tool_registration import register_builtin_tools
from qgitc.agent.tool_registry import ToolRegistry


class TestToolRegistration(unittest.TestCase):

    def test_register_builtin_tools(self):
        registry = ToolRegistry()
        register_builtin_tools(registry)
        tools = registry.list_tools()
        self.assertGreater(len(tools), 0)

    def test_known_tools_registered(self):
        registry = ToolRegistry()
        register_builtin_tools(registry)
        expected_names = [
            "git_status", "git_log", "git_diff", "git_diff_range",
            "git_diff_staged", "git_diff_unstaged",
            "git_show", "git_show_file", "git_show_index_file",
            "git_blame", "git_current_branch", "git_branch",
            "git_checkout", "git_cherry_pick", "git_commit", "git_add",
            "grep_search", "read_file", "read_external_file",
            "create_file", "apply_patch", "run_command",
        ]
        for name in expected_names:
            tool = registry.get(name)
            self.assertIsNotNone(tool, f"Tool '{name}' not registered")

    def test_schemas_generated(self):
        registry = ToolRegistry()
        register_builtin_tools(registry)
        schemas = registry.get_tool_schemas()
        self.assertEqual(len(schemas), len(registry.list_tools()))
        for schema in schemas:
            self.assertIn("function", schema)
            self.assertIn("name", schema["function"])


if __name__ == "__main__":
    unittest.main()
