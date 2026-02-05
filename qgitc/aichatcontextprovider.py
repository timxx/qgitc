# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime
import platform
from typing import List, NamedTuple, Optional, Tuple

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon

from qgitc.applicationbase import ApplicationBase
from qgitc.gitutils import Git


class AiContextDescriptor(NamedTuple):
    id: str
    label: str
    icon: Optional[QIcon] = None
    tooltip: Optional[str] = None


class AiChatContextProvider(QObject):
    """Provides available/default contexts for an AI chat embed location.

    The provider may change available contexts over time (e.g., commit selection changes).
    Emit contextsChanged when available/default contexts should be re-queried.
    """

    contextsChanged = Signal()

    def availableContexts(self) -> List[AiContextDescriptor]:
        return []

    def defaultContextIds(self) -> List[str]:
        return []

    def buildContextText(self, contextIds: List[str]) -> str:
        """Build LLM-ready context text for the given context ids.

        The returned string will be embedded into the user's prompt (e.g. wrapped
        in a <context>...</context> block).
        """
        return ""

    def agentSystemPrompt(self) -> Optional[str]:
        """Optional Agent-mode system prompt override.

        Return None to use the default AGENT_SYS_PROMPT.
        """
        return None

    def commonContext(self) -> List[str]:
        blocks = []
        today = datetime.date.today().isoformat()
        blocks.append(f"Current date: {today}")
        blocks.append(f"Current OS: {platform.system()}")
        blocks.append(f"Main repo dir: {Git.REPO_DIR}")
        blocks.append(
            f"UI language: {ApplicationBase.instance().uiLanguage()}")

        return blocks

    @staticmethod
    def formatBullets(lines: List[str]) -> str:
        lines = [l.strip() for l in lines if l.strip()]
        if not lines:
            return ""
        return "\n".join(f"- {l}" for l in lines)

    @staticmethod
    def formatCodeBlock(language: str, text: str) -> str:
        lang = language.strip()
        body = text.rstrip("\n")
        return f"```{lang}\n{body}\n```"

    @staticmethod
    def formatSection(title: str, body: str) -> str:
        t = title.strip()
        b = body.strip("\n")
        if not t or not b:
            return ""
        return f"### {t}\n{b}".rstrip()

    @staticmethod
    def addSection(sections: List[str], title: str, body: str):
        section = AiChatContextProvider.formatSection(title, body)
        if section:
            sections.append(section)

    @staticmethod
    def formatRepoFileBullets(repoFiles: List[Tuple[str, str]], *, limit: int = 100) -> str:
        if not repoFiles:
            return ""

        lines: List[str] = []
        for repoDir, filePath in (repoFiles or [])[:limit]:
            repo = AiChatContextProvider.normRepoDir(repoDir)
            path = filePath.replace("\\", "/")
            lines.append(f"Repo: {repo} | File: {path}")

        if len(repoFiles) > limit:
            lines.append(f"… (+{len(repoFiles) - limit} more)")

        return AiChatContextProvider.formatBullets(lines)

    @staticmethod
    def normRepoDir(repoDir: str) -> str:
        if not repoDir or repoDir == ".":
            return "."

        return repoDir.replace("\\", "/")
