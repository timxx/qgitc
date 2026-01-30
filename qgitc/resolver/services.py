# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:
    from qgitc.resolver.manager import ResolveManager
    from qgitc.resolver.taskrunner import TaskRunner


class ResolveConflictJobProto(Protocol):
    finished: object  # Signal(bool, str|None)


class AiConflictResolverProto(Protocol):
    def resolveFileAsync(
        self,
        repoDir: str,
        sha1: str,
        path: str,
        conflictText: str,
        extraContext: str = None,
    ) -> ResolveConflictJobProto: ...


@dataclass(slots=True)
class ResolveServices:
    runner: "TaskRunner"
    ai: Optional[AiConflictResolverProto] = None
    manager: Optional["ResolveManager"] = None
