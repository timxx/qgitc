# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from qgitc.aichathistory import AiChatHistory
from qgitc.aichathistorymodel import AiChatHistoryModel
from qgitc.applicationbase import ApplicationBase
from qgitc.llm import AiModelBase, AiModelFactory
from qgitc.settings import Settings


class AiChatHistoryStore(QObject):
    """Shared, non-UI chat history store.

    Owns a single in-memory list/model of histories and persists them to Settings.
    Multiple panels can share the same model instance to avoid duplicated loads
    and manual synchronization.
    """

    historiesLoaded = Signal()
    historyAdded = Signal(AiChatHistory)
    historyUpdated = Signal(AiChatHistory)
    historyRemoved = Signal(str)  # historyId
    historiesCleared = Signal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._model = AiChatHistoryModel(self)
        self._loaded = False

        # Debounced persistence to avoid hammering QSettings when multiple
        # windows/widgets update history frequently.
        self._pendingSaves: Dict[str, dict] = {}
        self._saveTimer = QTimer(self)
        self._saveTimer.setSingleShot(True)
        self._saveTimer.timeout.connect(self._flushPendingSaves)
        self._saveDebounceMs = 500

        app = ApplicationBase.instance()
        app.aboutToQuit.connect(self.flush)

    def model(self) -> AiChatHistoryModel:
        return self._model

    def isLoaded(self) -> bool:
        return self._loaded

    def ensureLoaded(self):
        if self._loaded:
            return

        existing = self._model.histories()

        histories = []
        newHistories = self._settings.chatHistories()
        for historyData in newHistories:
            if isinstance(historyData, dict):
                histories.append(AiChatHistory.fromDict(historyData))

        byId: Dict[str, AiChatHistory] = {h.historyId: h for h in histories}
        for h in existing:
            if h and h.historyId not in byId:
                histories.append(h)

        histories.sort(key=lambda h: h.timestamp, reverse=True)
        self._model.setHistories(histories)

        self._loaded = True
        self.historiesLoaded.emit()

    def get(self, historyId: str) -> Optional[AiChatHistory]:
        return self._model.getHistoryById(historyId)

    def insertHistoryAtTop(self, history: AiChatHistory):
        self.ensureLoaded()
        self._model.insertHistory(0, history)
        self.historyAdded.emit(history)

    def setSaveDebounceMs(self, debounceMs: int):
        self._saveDebounceMs = max(0, int(debounceMs))

    def _scheduleSave(self, historyId: str, historyData: dict):
        self._pendingSaves[historyId] = historyData
        if self._saveDebounceMs <= 0:
            self._flushPendingSaves()
            return
        self._saveTimer.start(self._saveDebounceMs)

    def _flushPendingSaves(self):
        if not self._pendingSaves:
            return
        pending = self._pendingSaves
        self._pendingSaves = {}
        for historyId, data in pending.items():
            self._settings.saveChatHistory(historyId, data)

    def flush(self):
        """Force any pending debounced saves to be written."""
        if self._saveTimer.isActive():
            self._saveTimer.stop()
        self._flushPendingSaves()

    def updateTitle(self, historyId: str, newTitle: str) -> Optional[AiChatHistory]:
        self.ensureLoaded()
        row = self._model.findHistoryRow(historyId)
        if row < 0:
            return None

        idx = self._model.index(row, 0)
        history: AiChatHistory = self._model.data(idx, Qt.UserRole)
        if not history:
            return None

        if history.title != newTitle:
            history.title = newTitle
            self._model.setData(idx, history, Qt.UserRole)
            self._scheduleSave(historyId, history.toDict())
            self.historyUpdated.emit(history)

        return history

    def updateCurrentModelId(self, historyId: str, modelId: str) -> Optional[AiChatHistory]:
        self.ensureLoaded()
        row = self._model.findHistoryRow(historyId)
        if row < 0:
            return None

        idx = self._model.index(row, 0)
        history: AiChatHistory = self._model.data(idx, Qt.UserRole)
        if not history:
            return None

        if history.modelId != modelId:
            history.modelId = modelId
            self._model.setData(idx, history, Qt.UserRole)
            self._scheduleSave(historyId, history.toDict())
            self.historyUpdated.emit(history)

        return history

    def updateFromModel(self, historyId: str, model: AiModelBase) -> Optional[AiChatHistory]:
        """Update a history item from an AiModelBase instance and persist it."""
        self.ensureLoaded()
        row = self._model.findHistoryRow(historyId)
        if row < 0:
            return None

        idx = self._model.index(row, 0)
        history: AiChatHistory = self._model.data(idx, Qt.UserRole)
        if not history:
            return None

        messages = []
        for message in model.history:
            messages.append({
                "role": message.role.name.lower(),
                "content": message.message,
                "reasoning": message.reasoning,
                "description": message.description,
                "tool_calls": message.toolCalls,
            })

        history.messages = messages
        history.modelKey = AiModelFactory.modelKey(model)
        history.modelId = model.modelId or model.name
        history.timestamp = datetime.now().isoformat()

        self._model.setData(idx, history, Qt.UserRole)

        # Keep most-recently-used history near the top.
        newRow = self._model.moveToTop(row)
        if newRow != row:
            # Recompute idx for save signal semantics.
            idx = self._model.index(newRow, 0)

        self._scheduleSave(historyId, history.toDict())
        self.historyUpdated.emit(history)
        return history

    def remove(self, historyId: str) -> bool:
        self.ensureLoaded()
        row = self._model.findHistoryRow(historyId)
        if row < 0:
            return False

        self._pendingSaves.pop(historyId, None)
        self._model.removeHistory(row)
        self._settings.removeChatHistory(historyId)
        self.historyRemoved.emit(historyId)
        return True

    def removeMany(self, historyIds: List[str]):
        self.ensureLoaded()
        # Remove by row descending to keep indices stable.
        rows = []
        for hid in historyIds:
            row = self._model.findHistoryRow(hid)
            if row >= 0:
                rows.append((row, hid))
        rows.sort(key=lambda x: x[0], reverse=True)

        for row, hid in rows:
            self._pendingSaves.pop(hid, None)
            self._model.removeHistory(row)
            self._settings.removeChatHistory(hid)
            self.historyRemoved.emit(hid)

    def clearAll(self):
        self.ensureLoaded()
        ids = [h.historyId for h in self._model.histories() if h]
        self._model.clear()
        for hid in ids:
            self._pendingSaves.pop(hid, None)
        for hid in ids:
            self._settings.removeChatHistory(hid)
            self.historyRemoved.emit(hid)
        self.historiesCleared.emit()
