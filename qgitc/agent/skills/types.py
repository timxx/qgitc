# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class SkillDefinition:
    name: str
    description: str
    content: str

    aliases: List[str] = field(default_factory=list)
    source: str = "projectSettings"
    loaded_from: str = "skills"
    when_to_use: Optional[str] = None
    argument_hint: Optional[str] = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    context: Optional[str] = None
    agent: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    paths: Optional[List[str]] = None
    allowed_tools: List[str] = field(default_factory=list)
    hooks: Optional[dict] = None
    skill_root: Optional[str] = None

    @property
    def content_length(self) -> int:
        return len(self.content)
