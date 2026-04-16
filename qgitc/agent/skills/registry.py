# -*- coding: utf-8 -*-

from typing import Dict, List, Optional

from qgitc.agent.skills.types import SkillDefinition


class SkillRegistry:

    def __init__(self):
        self._skills = {}  # type: Dict[str, SkillDefinition]
        self._aliases = {}  # type: Dict[str, str]

    def register(self, skill):
        # type: (SkillDefinition) -> None
        self._skills[skill.name] = skill
        for alias in skill.aliases:
            self._aliases[alias] = skill.name

    def get(self, name):
        # type: (str) -> Optional[SkillDefinition]
        skill = self._skills.get(name)
        if skill is not None:
            return skill
        canonical = self._aliases.get(name)
        if canonical is not None:
            return self._skills.get(canonical)
        return None

    def list_skills(self):
        # type: () -> List[SkillDefinition]
        return list(self._skills.values())

    def get_model_visible_skills(self):
        # type: () -> List[SkillDefinition]
        return [s for s in self._skills.values() if not s.disable_model_invocation]

    def clear(self):
        # type: () -> None
        self._skills.clear()
        self._aliases.clear()
