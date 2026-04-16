# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.skills.registry import SkillRegistry
from qgitc.agent.skills.types import SkillDefinition
from qgitc.agent.tool import ToolContext
from qgitc.agent.tools.skill import SkillTool


class TestSkillTool(unittest.TestCase):

    def setUp(self):
        self.registry = SkillRegistry()
        self.registry.register(SkillDefinition(
            name="review",
            description="Review",
            content="Use checklist\n$ARGUMENTS",
            allowed_tools=["read_file"],
        ))
        self.context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={"skill_registry": self.registry},
        )
        self.tool = SkillTool()

    def test_invoke_skill_returns_content(self):
        result = self.tool.execute(
            {"skill": "review", "args": "target.py"},
            self.context,
        )
        self.assertFalse(result.is_error)
        self.assertIn("Use checklist", result.content)
        self.assertIn("target.py", result.content)

    def test_sets_allowed_tools_in_context(self):
        result = self.tool.execute({"skill": "review"}, self.context)
        self.assertFalse(result.is_error)
        self.assertEqual(self.context.extra.get("tool_allowed_tools"), ["read_file"])

    def test_unknown_skill_returns_error(self):
        result = self.tool.execute({"skill": "missing"}, self.context)
        self.assertTrue(result.is_error)
        self.assertIn("Unknown skill", result.content)


if __name__ == "__main__":
    unittest.main()
