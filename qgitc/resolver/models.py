# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass, field
import sys
from typing import Any, Dict, List, Optional

from qgitc.resolver.enums import (
    ResolveEventKind,
    ResolveMethod,
    ResolveOperation,
    ResolveOutcomeStatus,
    ResolvePromptKind,
)
_DATACLASS_KWARGS = {"slots": True} if sys.version_info >= (3, 10) else {}


@dataclass(**_DATACLASS_KWARGS)
class ResolveContext:
    repoDir: str
    operation: ResolveOperation
    sha1: str = ""
    path: str = ""
    extraContext: Optional[str] = None
    initialError: Optional[str] = None
    mergetoolName: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass(**_DATACLASS_KWARGS)
class ResolvePrompt:
    promptId: int
    kind: ResolvePromptKind
    title: str
    text: str
    options: List[str]
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass(**_DATACLASS_KWARGS)
class ResolveOutcome:
    status: ResolveOutcomeStatus
    message: Optional[str] = None
    remainingConflicts: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(**_DATACLASS_KWARGS)
class ResolveEvent:
    kind: ResolveEventKind
    message: str = ""
    prompt: Optional[ResolvePrompt] = None
    method: Optional[ResolveMethod] = None
    path: Optional[str] = None
    outcome: Optional[ResolveOutcome] = None
    data: Dict[str, Any] = field(default_factory=dict)
