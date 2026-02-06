# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import QObject, Signal

from qgitc.resolver.enums import ResolveEventKind, ResolveOutcomeStatus
from qgitc.resolver.handlers.base import ResolveHandler
from qgitc.resolver.models import (
    ResolveContext,
    ResolveEvent,
    ResolveOutcome,
    ResolvePrompt,
)
from qgitc.resolver.services import ResolveServices


class ResolveManager(QObject):
    eventEmitted = Signal(object)  # ResolveEvent
    promptRequested = Signal(object)  # ResolvePrompt
    completed = Signal(object)  # ResolveOutcome

    def __init__(
        self,
        handlers: List[ResolveHandler],
        services: ResolveServices,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._handlers = handlers
        self._services = services
        self._ctx: Optional[ResolveContext] = None
        self._idx = -1
        self._pendingPrompt: Optional[ResolvePrompt] = None
        self._lastResolved: Optional[ResolveOutcome] = None
        self._done = False

        self._services.manager = self

        for h in self._handlers:
            h.finished.connect(self._onHandlerFinished)

    def start(self, ctx: ResolveContext):
        self._ctx = ctx
        self._idx = -1
        self._pendingPrompt = None
        self._lastResolved = None
        self._done = False
        self._emit(ResolveEvent(kind=ResolveEventKind.STARTED,
                                message=self.tr("Resolve started")))
        self._startNextHandler()

    def cancel(self):
        self._done = True
        if 0 <= self._idx < len(self._handlers):
            h = self._handlers[self._idx]
            h.cancel()

    def requestPrompt(self, prompt: ResolvePrompt):
        self._pendingPrompt = prompt
        self._emit(ResolveEvent(kind=ResolveEventKind.PROMPT,
                   prompt=prompt, message=prompt.text))
        self.promptRequested.emit(prompt)

    def replyPrompt(self, promptId: int, choice: Any):
        # Current implementation: manager only stores the latest prompt and forwards to active handler.
        if not self._pendingPrompt or self._pendingPrompt.promptId != promptId:
            return
        if 0 <= self._idx < len(self._handlers):
            h = self._handlers[self._idx]
            h.onPromptReply(promptId, choice)

    def emitEvent(self, event: ResolveEvent):
        self._emit(event)

    def _emit(self, event: ResolveEvent):
        self.eventEmitted.emit(event)

    def _startNextHandler(self):
        self._idx += 1
        if self._idx >= len(self._handlers):
            # End of pipeline.
            out = self._lastResolved
            if out is None:
                out = ResolveOutcome(
                    status=ResolveOutcomeStatus.FAILED,
                    message=self.tr("No resolver handler available"),
                )
            self._done = True
            self.completed.emit(out)
            self._emit(ResolveEvent(kind=ResolveEventKind.COMPLETED,
                       outcome=out, message=out.message or ""))
            return

        h = self._handlers[self._idx]
        h.start(self._ctx, self._services)

    def _onHandlerFinished(self, handled: bool, outcomeObj: object):
        if self._done:
            return

        if handled:
            outcome: ResolveOutcome = outcomeObj
            if outcome.status == ResolveOutcomeStatus.RESOLVED:
                self._lastResolved = outcome
                self._startNextHandler()
                return

            self._done = True
            self.completed.emit(outcome)
            self._emit(ResolveEvent(kind=ResolveEventKind.COMPLETED,
                       outcome=outcome, message=outcome.message or ""))
            return

        self._startNextHandler()
