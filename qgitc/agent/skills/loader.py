# -*- coding: utf-8 -*-

import logging
import os
import re
from typing import Any, Dict, List, Tuple

import yaml

from qgitc.agent.skills.types import SkillDefinition

logger = logging.getLogger(__name__)


def parseSkillFrontmatter(content):
    # type: (str) -> Tuple[Dict[str, Any], str]
    match = re.match(r"\A---\s*\n(.*?)\n?---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        return {}, content

    frontmatter_text = match.group(1)
    body = match.group(2)

    try:
        metadata = yaml.safe_load(frontmatter_text)
        if not isinstance(metadata, dict):
            return {}, body
        return metadata, body
    except yaml.YAMLError:
        logger.warning("Failed to parse skill frontmatter")
        return {}, content


def _parse_boolean(value):
    # type: (Any) -> bool
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _parse_list_field(value):
    # type: (Any) -> List[str]
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _parse_tools_list(value):
    # type: (Any) -> List[str]
    return _parse_list_field(value)


def _get_string_field(frontmatter, *keys):
    # type: (Dict[str, Any], str) -> Any
    for key in keys:
        value = frontmatter.get(key)
        if value is not None:
            return str(value)
    return None


def _extract_description(body):
    # type: (str) -> str
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            if len(stripped) > 200:
                return stripped[:197] + "..."
            return stripped
    return "Skill command"


def createSkillDefinition(frontmatter, body, file_path):
    # type: (Dict[str, Any], str, str) -> SkillDefinition
    skill_dir = os.path.dirname(file_path)
    inferred_name = os.path.basename(skill_dir)

    name = str(frontmatter.get("name", inferred_name))
    raw_desc = frontmatter.get("description")
    description = str(raw_desc) if raw_desc is not None else _extract_description(body)

    user_invocable = True
    if "user-invocable" in frontmatter or "user_invocable" in frontmatter:
        user_invocable = _parse_boolean(
            frontmatter.get("user-invocable", frontmatter.get("user_invocable"))
        )

    disable_model_invocation = False
    if "disable-model-invocation" in frontmatter or "disable_model_invocation" in frontmatter:
        disable_model_invocation = _parse_boolean(
            frontmatter.get(
                "disable-model-invocation",
                frontmatter.get("disable_model_invocation"),
            )
        )

    raw_paths = frontmatter.get("paths")
    paths = None  # type: Any
    if raw_paths:
        if isinstance(raw_paths, list):
            paths = [str(p).strip() for p in raw_paths if p]
        elif isinstance(raw_paths, str):
            paths = [p.strip() for p in raw_paths.split(",") if p.strip()]
        if paths:
            paths = [p for p in paths if p and p != "**"]
            if not paths:
                paths = None

    return SkillDefinition(
        name=name,
        description=description,
        content=body,
        aliases=_parse_list_field(frontmatter.get("aliases")),
        source="projectSettings",
        loaded_from="skills",
        when_to_use=_get_string_field(frontmatter, "when_to_use", "when-to-use"),
        argument_hint=_get_string_field(frontmatter, "argument_hint", "argument-hint"),
        user_invocable=user_invocable,
        disable_model_invocation=disable_model_invocation,
        context=("fork" if frontmatter.get("context") == "fork" else None),
        agent=_get_string_field(frontmatter, "agent"),
        model=_get_string_field(frontmatter, "model"),
        effort=_get_string_field(frontmatter, "effort"),
        paths=paths,
        allowed_tools=_parse_tools_list(
            frontmatter.get("allowed-tools", frontmatter.get("allowed_tools"))
        ),
        hooks=frontmatter.get("hooks"),
        skill_root=skill_dir,
    )


def loadSkillsFromDirectory(directory):
    # type: (str) -> List[SkillDefinition]
    skills = []  # type: List[SkillDefinition]
    if not os.path.isdir(directory):
        return skills

    try:
        entries = os.listdir(directory)
    except OSError as e:
        logger.warning("Failed to read skills directory %s: %s", directory, e)
        return skills

    for entry_name in sorted(entries):
        entry_path = os.path.join(directory, entry_name)
        if not os.path.isdir(entry_path):
            continue

        skill_file = os.path.join(entry_path, "SKILL.md")
        if not os.path.isfile(skill_file):
            continue

        try:
            with open(skill_file, encoding="utf-8") as f:
                content = f.read()
            frontmatter, body = parseSkillFrontmatter(content)
            skills.append(createSkillDefinition(frontmatter, body, skill_file))
        except OSError as e:
            logger.warning("Failed to read skill file %s: %s", skill_file, e)

    return skills
