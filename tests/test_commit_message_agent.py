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


class TestCommitMessageAgent(TestBase):

    def doCreateRepo(self):
        pass

    def test_buildToolRegistry_all_tools_are_readonly(self):
        from qgitc.commitMessageAgent import CommitMessageAgent

        agent = CommitMessageAgent()
        registry = agent._buildToolRegistry()
        tools = registry.listTools()
        self.assertGreater(len(tools), 0)
        for tool in tools:
            self.assertTrue(
                tool.isReadOnly(),
                f"Tool '{tool.name}' must be read-only in CommitMessageAgent"
            )

    def test_buildToolRegistry_has_required_tools(self):
        from qgitc.commitMessageAgent import CommitMessageAgent

        agent = CommitMessageAgent()
        registry = agent._buildToolRegistry()
        self.assertIsNotNone(registry.get("git_diff_staged"))
        self.assertIsNotNone(registry.get("git_log"))
        self.assertIsNotNone(registry.get("git_status"))
        self.assertIsNotNone(registry.get("Skill"))

    def test_buildToolRegistry_excludes_write_tools(self):
        from qgitc.commitMessageAgent import CommitMessageAgent

        agent = CommitMessageAgent()
        registry = agent._buildToolRegistry()
        self.assertIsNone(registry.get("create_file"))
        self.assertIsNone(registry.get("apply_patch"))
        self.assertIsNone(registry.get("git_commit"))
        self.assertIsNone(registry.get("git_add"))
        self.assertIsNone(registry.get("run_command"))

    def test_cancel_when_not_running_is_safe(self):
        from qgitc.commitMessageAgent import CommitMessageAgent

        agent = CommitMessageAgent()
        agent.cancel()  # must not raise

    def test_buildPrompt_single_main_repo(self):
        from qgitc.commitMessageAgent import CommitMessageAgent

        agent = CommitMessageAgent()
        prompt = agent._buildPrompt({None: ["file.py"]}, None, False)
        self.assertIn(".", prompt)
        self.assertIn("Repos with staged changes", prompt)

    def test_buildPrompt_multiple_repos(self):
        from qgitc.commitMessageAgent import CommitMessageAgent

        agent = CommitMessageAgent()
        submoduleFiles = {None: ["a.py"], "libs/foo": ["b.py"]}
        prompt = agent._buildPrompt(submoduleFiles, None, False)
        self.assertIn(".", prompt)
        self.assertIn("libs/foo", prompt)

    def test_buildPrompt_includes_template_when_useTemplateOnly(self):
        from qgitc.commitMessageAgent import CommitMessageAgent

        agent = CommitMessageAgent()
        prompt = agent._buildPrompt(
            {None: ["file.py"]},
            template="feat: {description}",
            useTemplateOnly=True,
        )
        self.assertIn("feat: {description}", prompt)

    def test_buildPrompt_excludes_template_when_not_useTemplateOnly(self):
        from qgitc.commitMessageAgent import CommitMessageAgent

        agent = CommitMessageAgent()
        prompt = agent._buildPrompt(
            {None: ["file.py"]},
            template="feat: {description}",
            useTemplateOnly=False,
        )
        self.assertNotIn("feat: {description}", prompt)

