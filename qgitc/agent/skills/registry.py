# -*- coding: utf-8 -*-

from typing import Dict, List, Optional

from qgitc.agent.skills.types import SkillDefinition


class SkillRegistry:

    def __init__(self):
        self._skills = {}  # type: Dict[str, SkillDefinition]
        self._aliases = {}  # type: Dict[str, str]

    _SOURCE_PRIORITY = {
        "projectSettings": 10,
        "builtinSkills": 0,
    }

    def register(self, skill):
        # type: (SkillDefinition) -> None
        existing = self._skills.get(skill.name)
        if existing is not None:
            existingPriority = self._SOURCE_PRIORITY.get(existing.source, 5)
            newPriority = self._SOURCE_PRIORITY.get(skill.source, 5)
            if newPriority < existingPriority:
                return
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

    def listSkills(self):
        # type: () -> List[SkillDefinition]
        return list(self._skills.values())

    def getModelVisibleSkills(self):
        # type: () -> List[SkillDefinition]
        return [s for s in self._skills.values() if not s.disable_model_invocation]

    def clear(self):
        # type: () -> None
        self._skills.clear()
        self._aliases.clear()
