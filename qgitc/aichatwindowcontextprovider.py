# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List

from qgitc.aichatcontextprovider import AiChatContextProvider


class AiChatWindowContextProvider(AiChatContextProvider):
    """Context provider for the standalone AI chat window.

    This window is not tied to a specific Git UI surface (commit list, diff view,
    etc.), so it only provides a basic environment context.
    """

    def canAddContext(self) -> bool:
        return False

    def defaultContextIds(self) -> List[str]:
        return []

    def buildContextText(self, contextIds: List[str]) -> str:
        sections: List[str] = []

        self.addSection(
            sections,
            "Environment",
            self.formatBullets(self.commonContext()),
        )

        return "\n\n".join(sections).strip()
