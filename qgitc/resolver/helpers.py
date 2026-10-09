# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List, Optional, Tuple

from qgitc.applicationbase import ApplicationBase
from qgitc.gitutils import Git
from qgitc.resolver.handlers.ai import AiResolveHandler
from qgitc.resolver.handlers.base import ResolveHandler
from qgitc.resolver.handlers.mergetool import GitMergetoolHandler


def selectMergetoolNameForPath(path: str) -> Optional[str]:
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


def gitMergetoolName(repoDir: Optional[str] = None) -> str:
    """Return the merge tool name git resolves for @repoDir ("" if none).

    The probe runs inside the conflicted repository so the answer matches what
    ``git mergetool`` itself sees there: a globally configured tool and a
    repository-local one can differ.
    """

    try:
        name = Git.getConfigValue("merge.tool", False, repoDir=repoDir)
    except Exception:
        return ""

    return (name or "").strip()


def buildResolveHandlers(
    *,
    parent,
    path: str,
    repoDir: Optional[str] = None,
    aiEnabled: bool,
    chatWidget,
) -> Tuple[List[ResolveHandler], Optional[str], bool]:
    """Build the resolver handler chain for a single file.

    Returns (handlers, mergetoolName, hasGitDefaultTool).
    """

    mergeToolName = selectMergetoolNameForPath(path)

    gitToolName = gitMergetoolName(repoDir)
    hasGitDefaultTool = bool(gitToolName)

    if not mergeToolName:
        # Hand git's configured tool to the handler so that the merge tool is
        # always launched with an explicit --tool: without one, git mergetool
        # guesses a tool and then waits on stdin for an answer, which shows up
        # as a pick window that never finishes.
        mergeToolName = gitToolName or None

    handlers: List[ResolveHandler] = []

    if aiEnabled and chatWidget is not None:
        handlers.append(AiResolveHandler(parent))

    if mergeToolName:
        handlers.append(GitMergetoolHandler(parent))

    return handlers, mergeToolName, hasGitDefaultTool
