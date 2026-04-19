# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.skills.registry import SkillRegistry
from qgitc.agent.skills.types import SkillDefinition


class TestSkillRegistry(unittest.TestCase):

    def test_lookup_by_name_and_alias(self):
        reg = SkillRegistry()
        reg.register(SkillDefinition(
            name="review",
            description="Review code",
            content="Body",
            aliases=["rv"],
        ))
        self.assertIsNotNone(reg.get("review"))
        self.assertIsNotNone(reg.get("rv"))

    def test_model_visible_filters_disabled(self):
        reg = SkillRegistry()
        reg.register(SkillDefinition(
            name="a",
            description="A",
            content="A body",
        ))
        reg.register(SkillDefinition(
            name="b",
            description="B",
            content="B body",
            disable_model_invocation=True,
        ))
        names = [s.name for s in reg.getModelVisibleSkills()]
        self.assertEqual(names, ["a"])


if __name__ == "__main__":
    unittest.main()
