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

    def test_loads_from_project_subdirs_only(self):
        with tempfile.TemporaryDirectory() as proj_td:
            proj = Path(proj_td)

            self._write_skill(proj / ".claude" / "skills", "sk1", "sk1", "Skill 1")
            self._write_skill(proj / ".agents" / "skills", "sk2", "sk2", "Skill 2")
            self._write_skill(proj / ".github" / "skills", "sk3", "sk3", "Skill 3")
            self._write_skill(proj / ".codex" / "skills", "sk4", "sk4", "Skill 4")
            self._write_skill(proj / ".cursor" / "skills", "sk5", "sk5", "Skill 5")

            registry = load_skill_registry(cwd=str(proj))
            names = {s.name for s in registry.list_skills()}
            self.assertIn("sk1", names)
            self.assertIn("sk2", names)
            self.assertIn("sk3", names)
            self.assertIn("sk4", names)
            self.assertIn("sk5", names)

    def test_home_directory_skills_are_not_loaded(self):
        with tempfile.TemporaryDirectory() as home_td, tempfile.TemporaryDirectory() as proj_td:
            home = Path(home_td)
            proj = Path(proj_td)
            # Put skills only in home directory locations
            self._write_skill(home / ".claude" / "skills", "home_sk", "home_sk")

            # load_skill_registry no longer accepts/uses home_directory
            registry = load_skill_registry(cwd=str(proj))
            names = {s.name for s in registry.list_skills()}
            self.assertNotIn("home_sk", names)
            self.assertNotIn("home_qgitc_sk", names)

    def test_project_skills_source_tag(self):
        with tempfile.TemporaryDirectory() as proj_td:
            proj = Path(proj_td)
            self._write_skill(proj / ".claude" / "skills", "proj_sk", "proj_sk")
            registry = load_skill_registry(cwd=str(proj))
            self.assertEqual(registry.get("proj_sk").source, "projectSettings")

    def test_project_skill_overrides_earlier_skill_same_name(self):
        # Two different project dirs with the same skill name; the later one wins
        with tempfile.TemporaryDirectory() as proj_td:
            proj = Path(proj_td)
            # .claude loaded before .github alphabetically by _SKILL_SUBDIRS order
            self._write_skill(proj / ".claude" / "skills", "review", "review", "Claude description")
            self._write_skill(proj / ".github" / "skills", "review", "review", "GitHub description")
            registry = load_skill_registry(cwd=str(proj))
            skill = registry.get("review")
            self.assertIsNotNone(skill)
            # .github comes after .claude in _SKILL_SUBDIRS so it overrides
            self.assertEqual(skill.description, "GitHub description")


if __name__ == "__main__":
    unittest.main()
