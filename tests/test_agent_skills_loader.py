# -*- coding: utf-8 -*-

import tempfile
import unittest
from pathlib import Path

from qgitc.agent.skills.discovery import load_skill_registry
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


class TestLoadSkillRegistry(unittest.TestCase):

    def _write_skill(self, skills_dir, folder_name, skill_name, description="A skill"):
        d = skills_dir / folder_name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            "---\nname: {}\ndescription: {}\n---\nbody\n".format(skill_name, description),
            encoding="utf-8",
        )

    def test_loads_from_multiple_subdirs(self):
        with tempfile.TemporaryDirectory() as home_td, tempfile.TemporaryDirectory() as proj_td:
            home = Path(home_td)
            proj = Path(proj_td)

            # Put a skill in each location
            self._write_skill(home / ".qgitc" / "skills", "sk1", "sk1", "Skill 1")
            self._write_skill(home / ".claude" / "skills", "sk2", "sk2", "Skill 2")
            self._write_skill(proj / ".agents" / "skills", "sk3", "sk3", "Skill 3")
            self._write_skill(proj / ".github" / "skills", "sk4", "sk4", "Skill 4")
            self._write_skill(proj / ".codex" / "skills", "sk5", "sk5", "Skill 5")
            self._write_skill(proj / ".cursor" / "skills", "sk6", "sk6", "Skill 6")

            registry = load_skill_registry(
                cwd=str(proj), home_directory=str(home)
            )
            names = {s.name for s in registry.list_skills()}
            self.assertIn("sk1", names)
            self.assertIn("sk2", names)
            self.assertIn("sk3", names)
            self.assertIn("sk4", names)
            self.assertIn("sk5", names)
            self.assertIn("sk6", names)

    def test_user_skills_source_tag(self):
        with tempfile.TemporaryDirectory() as home_td, tempfile.TemporaryDirectory() as proj_td:
            home = Path(home_td)
            proj = Path(proj_td)
            self._write_skill(home / ".qgitc" / "skills", "user_sk", "user_sk")
            self._write_skill(proj / ".claude" / "skills", "proj_sk", "proj_sk")
            registry = load_skill_registry(cwd=str(proj), home_directory=str(home))
            self.assertEqual(registry.get("user_sk").source, "userSettings")
            self.assertEqual(registry.get("proj_sk").source, "projectSettings")


if __name__ == "__main__":
    unittest.main()
