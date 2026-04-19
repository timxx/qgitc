# -*- coding: utf-8 -*-

from typing import List

from qgitc.agent.skills.types import SkillDefinition


def renderSkillsReminder(skills):
    # type: (List[SkillDefinition]) -> str
    if not skills:
        return ""

    lines = ["Available skills:"]
    for skill in skills:
        line = "- {}: {}".format(skill.name, skill.description)
        if skill.when_to_use:
            line += " (when: {})".format(skill.when_to_use)
        lines.append(line)

    return "\n".join(lines)
