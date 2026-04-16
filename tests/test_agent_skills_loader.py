# -*- coding: utf-8 -*-

import tempfile
import unittest
from pathlib import Path

from qgitc.agent.skills.loader import load_skills_from_directory


class TestSkillLoader(unittest.TestCase):

    def test_load_skill_from_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill_dir = root / "review"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                """---\nname: review\ndescription: Review code\naliases: [rv]\nallowed-tools: [read_file]\n---\n# body\nDo review\n""",
                encoding="utf-8",
            )

            skills = load_skills_from_directory(str(root))
            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].name, "review")
            self.assertEqual(skills[0].aliases, ["rv"])
            self.assertEqual(skills[0].allowed_tools, ["read_file"])


if __name__ == "__main__":
    unittest.main()
