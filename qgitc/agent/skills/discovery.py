# -*- coding: utf-8 -*-

from pathlib import Path

from qgitc.agent.skills.loader import load_skills_from_directory
from qgitc.agent.skills.registry import SkillRegistry

_SKILL_SUBDIRS = (
    ".qgitc/skills",
    ".claude/skills",
    ".agents/skills",
    ".github/skills",
    ".codex/skills",
    ".cursor/skills",
)


def load_skill_registry(cwd, home_directory=None, additional_directories=None):
    # type: (str, object, object) -> SkillRegistry
    if home_directory is None:
        home_directory = Path.home()

    registry = SkillRegistry()

    for subdir in _SKILL_SUBDIRS:
        user_skills_dir = Path(home_directory) / subdir
        for skill in load_skills_from_directory(str(user_skills_dir)):
            skill.source = "userSettings"
            registry.register(skill)

    for subdir in _SKILL_SUBDIRS:
        project_skills_dir = Path(cwd) / subdir
        for skill in load_skills_from_directory(str(project_skills_dir)):
            skill.source = "projectSettings"
            registry.register(skill)

    for extra_dir in additional_directories or []:
        for skill in load_skills_from_directory(str(extra_dir)):
            registry.register(skill)

    return registry
