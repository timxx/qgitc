# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List, Optional, Tuple

from qgitc.applicationbase import ApplicationBase
from qgitc.gitutils import Git
from qgitc.resolver.handlers.ai import AiResolveHandler
from qgitc.resolver.handlers.base import ResolveHandler
from qgitc.resolver.handlers.mergetool import GitMergetoolHandler


def select_mergetool_name_for_path(path: str) -> Optional[str]:
    """Select merge tool command name for a given file path.

    Preference order:
    1) Suffix-specific merge tool from Preferences > Tools
    2) Global merge tool from Preferences
    3) None (caller may still rely on git's merge.tool)
    """

    settings = ApplicationBase.instance().settings()
    tools = settings.mergeToolList()

    lowercasePath = (path or "").lower()
    for tool in tools:
        try:
            if tool.canMerge() and tool.isValid():
                suffix = (tool.suffix or "").lower()
                if suffix and lowercasePath.endswith(suffix):
                    return tool.command
        except Exception:
            continue

    return settings.mergeToolName() or None


def build_resolve_handlers(
    *,
    parent,
    path: str,
    aiEnabled: bool,
    chatWidget,
) -> Tuple[List[ResolveHandler], Optional[str], bool]:
    """Build the resolver handler chain for a single file.

    Returns (handlers, mergetoolName, hasGitDefaultTool).
    """

    mergeToolName = select_mergetool_name_for_path(path)
    hasGitDefaultTool = bool(Git.getConfigValue("merge.tool", False))

    handlers: List[ResolveHandler] = []

    if aiEnabled and chatWidget is not None:
        handlers.append(AiResolveHandler(parent))

    if mergeToolName or hasGitDefaultTool:
        handlers.append(GitMergetoolHandler(parent))

    return handlers, mergeToolName, hasGitDefaultTool
