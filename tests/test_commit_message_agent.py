# -*- coding: utf-8 -*-

import unittest

from tests.base import TestBase


class TestCommitMessageSettings(TestBase):

    def doCreateRepo(self):
        pass

    def test_useSkillForCommitMessage_default_is_false(self):
        settings = self.app.settings()
        self.assertFalse(settings.useSkillForCommitMessage())

    def test_useSkillForCommitMessage_roundtrip(self):
        settings = self.app.settings()
        settings.setUseSkillForCommitMessage(True)
        self.assertTrue(settings.useSkillForCommitMessage())
        settings.setUseSkillForCommitMessage(False)
        self.assertFalse(settings.useSkillForCommitMessage())


class TestCommitMessageSkill(TestBase):

    def doCreateRepo(self):
        pass

    def test_builtin_skill_loads_from_data_dir(self):
        from qgitc.agent.skills.discovery import loadSkillRegistry
        from qgitc.common import dataDirPath

        registry = loadSkillRegistry(
            cwd="/nonexistent_path_that_has_no_skills",
            additional_directories=[dataDirPath() + "/skills"],
        )
        skill = registry.get("commit-message")
        self.assertIsNotNone(skill, "commit-message skill must be found in data/skills/")
        self.assertEqual(skill.name, "commit-message")

    def test_builtin_skill_contains_arguments_placeholder(self):
        from qgitc.agent.skills.discovery import loadSkillRegistry
        from qgitc.common import dataDirPath

        registry = loadSkillRegistry(
            cwd="/nonexistent_path_that_has_no_skills",
            additional_directories=[dataDirPath() + "/skills"],
        )
        skill = registry.get("commit-message")
        self.assertIsNotNone(skill)
        self.assertIn("$ARGUMENTS", skill.content)

    def test_project_skill_overrides_builtin(self):
        import os
        import tempfile

        from qgitc.agent.skills.discovery import loadSkillRegistry
        from qgitc.common import dataDirPath

        with tempfile.TemporaryDirectory() as tmpdir:
            skillDir = os.path.join(tmpdir, ".claude", "skills", "commit-message")
            os.makedirs(skillDir)
            with open(os.path.join(skillDir, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("---\nname: commit-message\ndescription: Custom skill\n---\nCustom body\n$ARGUMENTS")

            registry = loadSkillRegistry(
                cwd=tmpdir,
                additional_directories=[dataDirPath() + "/skills"],
            )
            skill = registry.get("commit-message")
            self.assertIsNotNone(skill)
            self.assertIn("Custom body", skill.content)

