# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.tool import ToolContext
from qgitc.agent.tool_registration import register_builtin_tools
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.tools.resolve_result import ResolveResultTool


class _FakeResolveContext(object):
    def __init__(self):
        self._result = None

    def setResult(self, status, reason):
        self._result = {
            "status": status,
            "reason": reason,
        }

    def result(self):
        return self._result


class TestResolveResultTool(unittest.TestCase):

    def test_records_terminal_status_in_resolve_context(self):
        resolveContext = _FakeResolveContext()
        tool = ResolveResultTool(resolveContext)

        result = tool.execute(
            {"status": "ok", "reason": "kept ours, reapplied theirs"},
            ToolContext(working_directory=".", abort_requested=lambda: False),
        )

        self.assertFalse(result.is_error)
        self.assertEqual(
            resolveContext.result(),
            {
                "status": "ok",
                "reason": "kept ours, reapplied theirs",
            },
        )

    def test_reports_as_read_only_tool(self):
        tool = ResolveResultTool(_FakeResolveContext())

        self.assertTrue(tool.is_read_only())

    def test_rejects_unknown_status(self):
        tool = ResolveResultTool(_FakeResolveContext())
        result = tool.execute(
            {"status": "maybe"},
            ToolContext(working_directory=".", abort_requested=lambda: False),
        )

        self.assertTrue(result.is_error)
        self.assertIn("status", result.content)

    def test_context_result_is_updated(self):
        resolveContext = _FakeResolveContext()

        resolveContext.setResult("failed", "stop")

        self.assertEqual(
            resolveContext.result(),
            {"status": "failed", "reason": "stop"},
        )

    def test_not_registered_as_builtin_tool(self):
        registry = ToolRegistry()
        register_builtin_tools(registry)

        self.assertIsNone(registry.get("resolve_result"))


if __name__ == "__main__":
    unittest.main()
