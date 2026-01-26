# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime
from typing import List, NamedTuple, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon

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
        blocks.append(f"The current date is {today}")
        blocks.append(f"Main repo dir: {Git.REPO_DIR}")

        return blocks
