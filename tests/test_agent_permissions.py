# -*- coding: utf-8 -*-

import unittest

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.permissions import (
    PermissionAllow,
    PermissionAsk,
    PermissionBehavior,
    PermissionDeny,
    PermissionEngine,
    PermissionRule,
    PermissionUpdate,
)


# ---------------------------------------------------------------------------
# Stub tools
# ---------------------------------------------------------------------------

class StubReadOnlyTool(Tool):
    name = "git_status"
    description = "A read-only tool"

    def is_read_only(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="ok")

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class StubWriteTool(Tool):
    name = "git_commit"
    description = "A write tool"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="ok")

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class StubDestructiveTool(Tool):
    name = "run_command"
    description = "A destructive tool"

    def is_destructive(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="ok")

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPermissionEngineDefaults(unittest.TestCase):
    """Tests for default behaviour with no explicit rules."""

    def setUp(self):
        self.engine = PermissionEngine()

    def test_read_only_tool_allowed_by_default(self):
        tool = StubReadOnlyTool()
        result = self.engine.check(tool, {})
        self.assertIsInstance(result, PermissionAllow)

    def test_write_tool_asks_by_default(self):
        tool = StubWriteTool()
        result = self.engine.check(tool, {})
        self.assertIsInstance(result, PermissionAsk)

    def test_destructive_tool_asks_by_default(self):
        tool = StubDestructiveTool()
        result = self.engine.check(tool, {})
        self.assertIsInstance(result, PermissionAsk)


class TestDenyRules(unittest.TestCase):
    """Tests for deny rules."""

    def test_deny_rule_blocks_specific_tool(self):
        engine = PermissionEngine(deny_rules=[
            PermissionRule(tool_name="run_command", behavior=PermissionBehavior.DENY),
        ])
        result = engine.check(StubDestructiveTool(), {})
        self.assertIsInstance(result, PermissionDeny)

    def test_deny_wildcard_blocks_all_tools(self):
        engine = PermissionEngine(deny_rules=[
            PermissionRule(tool_name="*", behavior=PermissionBehavior.DENY),
        ])
        self.assertIsInstance(engine.check(StubReadOnlyTool(), {}), PermissionDeny)
        self.assertIsInstance(engine.check(StubWriteTool(), {}), PermissionDeny)
        self.assertIsInstance(engine.check(StubDestructiveTool(), {}), PermissionDeny)

    def test_deny_takes_precedence_over_allow(self):
        engine = PermissionEngine(
            allow_rules=[
                PermissionRule(tool_name="git_commit", behavior=PermissionBehavior.ALLOW),
            ],
            deny_rules=[
                PermissionRule(tool_name="git_commit", behavior=PermissionBehavior.DENY),
            ],
        )
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionDeny)

    def test_deny_with_matching_pattern_blocks(self):
        engine = PermissionEngine(deny_rules=[
            PermissionRule(
                tool_name="run_command",
                behavior=PermissionBehavior.DENY,
                pattern="rm -rf",
            ),
        ])
        result = engine.check(StubDestructiveTool(), {"command": "rm -rf /"})
        self.assertIsInstance(result, PermissionDeny)

    def test_deny_with_non_matching_pattern_falls_through(self):
        engine = PermissionEngine(deny_rules=[
            PermissionRule(
                tool_name="run_command",
                behavior=PermissionBehavior.DENY,
                pattern="rm -rf",
            ),
        ])
        result = engine.check(StubDestructiveTool(), {"command": "ls -la"})
        self.assertIsInstance(result, PermissionAsk)


class TestAllowRules(unittest.TestCase):
    """Tests for allow rules."""

    def test_allow_rule_permits_write_tool(self):
        engine = PermissionEngine(allow_rules=[
            PermissionRule(tool_name="git_commit", behavior=PermissionBehavior.ALLOW),
        ])
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAllow)

    def test_allow_wildcard_permits_all(self):
        engine = PermissionEngine(allow_rules=[
            PermissionRule(tool_name="*", behavior=PermissionBehavior.ALLOW),
        ])
        self.assertIsInstance(engine.check(StubReadOnlyTool(), {}), PermissionAllow)
        self.assertIsInstance(engine.check(StubWriteTool(), {}), PermissionAllow)
        self.assertIsInstance(engine.check(StubDestructiveTool(), {}), PermissionAllow)


class TestApplyUpdate(unittest.TestCase):
    """Tests for apply_update method."""

    def test_add_allow_rule(self):
        engine = PermissionEngine()
        rule = PermissionRule(tool_name="git_commit", behavior=PermissionBehavior.ALLOW)
        engine.apply_update(PermissionUpdate(action="add", rule=rule))
        self.assertIn(rule, engine.allow_rules)
        # Verify the rule actually takes effect
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAllow)

    def test_add_deny_rule(self):
        engine = PermissionEngine()
        rule = PermissionRule(tool_name="git_status", behavior=PermissionBehavior.DENY)
        engine.apply_update(PermissionUpdate(action="add", rule=rule))
        self.assertIn(rule, engine.deny_rules)
        # Verify the rule actually takes effect
        result = engine.check(StubReadOnlyTool(), {})
        self.assertIsInstance(result, PermissionDeny)

    def test_remove_rule(self):
        rule = PermissionRule(tool_name="git_commit", behavior=PermissionBehavior.ALLOW)
        engine = PermissionEngine(allow_rules=[rule])
        engine.apply_update(PermissionUpdate(action="remove", rule=rule))
        self.assertNotIn(rule, engine.allow_rules)
        # Write tool should now ask again
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAsk)

    def test_remove_nonexistent_rule_does_not_raise(self):
        engine = PermissionEngine()
        rule = PermissionRule(tool_name="git_commit", behavior=PermissionBehavior.ALLOW)
        # Should not raise
        engine.apply_update(PermissionUpdate(action="remove", rule=rule))


class TestAskMessage(unittest.TestCase):
    """Tests that ask results include the tool name."""

    def test_ask_message_includes_tool_name(self):
        engine = PermissionEngine()
        result = engine.check(StubWriteTool(), {})
        self.assertIsInstance(result, PermissionAsk)
        self.assertIn("git_commit", result.message)


if __name__ == "__main__":
    unittest.main()
