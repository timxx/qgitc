# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal

from qgitc.resolver.models import ResolveContext
from qgitc.resolver.services import ResolveServices


class ResolveHandler(QObject):
    # handled:bool, outcome:ResolveOutcome|None
    finished = Signal(bool, object)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

    def start(self, ctx: ResolveContext, services: ResolveServices):
        raise NotImplementedError()

    def onPromptReply(self, promptId: int, choice: object):
        # Optional: handlers that request prompts can override.
        pass

    def cancel(self):
        pass
