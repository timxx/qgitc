# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List, NamedTuple, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon


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
