# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSortFilterProxyModel, Qt

from qgitc.aichathistory import AiChatHistory
from qgitc.applicationbase import qtVersion


class AiChatHistoryModel(QAbstractListModel):
    """Model for chat histories.

    This is intentionally UI-agnostic (Qt model only) so it can be shared across
    multiple views/panels within the application.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._histories: List[AiChatHistory] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._histories)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._histories):
            return None

        history = self._histories[index.row()]

        if role == Qt.DisplayRole:
            return history.title or self.tr("New Conversation")
        if role == Qt.UserRole:
            return history
        if role == Qt.ToolTipRole:
            modelStr = self.tr("Model: ")
            createdStr = self.tr("Created: ")
            return f"{modelStr}{history.modelId}\n{createdStr}{history.timestamp[:19]}"

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if index.isValid() and role == Qt.UserRole:
            self._histories[index.row()] = value
            self.dataChanged.emit(index, index)
            return True
        return False

    def histories(self) -> List[AiChatHistory]:
        return self._histories.copy()

    def insertHistory(self, row: int, history: AiChatHistory):
        self.beginInsertRows(QModelIndex(), row, row)
        self._histories.insert(row, history)
        self.endInsertRows()

    def removeHistory(self, row: int):
        if 0 <= row < len(self._histories):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._histories[row]
            self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self._histories.clear()
        self.endResetModel()

    def setHistories(self, histories: List[AiChatHistory]):
        self.beginResetModel()
        self._histories = histories.copy()
        self.endResetModel()

    def getHistory(self, row: int) -> Optional[AiChatHistory]:
        if 0 <= row < len(self._histories):
            return self._histories[row]
        return None

    def getHistoryById(self, historyId: str) -> Optional[AiChatHistory]:
        row = self.findHistoryRow(historyId)
        if row < 0:
            return None
        return self._histories[row]

    def findHistoryRow(self, historyId: str) -> int:
        for i, history in enumerate(self._histories):
            if history.historyId == historyId:
                return i
        return -1

    def moveToTop(self, row: int) -> int:
        if row > 0:
            newRow = 0
            # Keep "New Conversation" placeholder at top when present.
            if len(self._histories) > 1:
                firstHistory = self._histories[0]
                if not firstHistory.messages and firstHistory.title in ["", self.tr("New Conversation")]:
                    newRow = 1

            if newRow != row:
                self.beginMoveRows(QModelIndex(), row, row,
                                   QModelIndex(), newRow)
                history = self._histories.pop(row)
                self._histories.insert(newRow, history)
                self.endMoveRows()
                return newRow
        return row


class AiChatHistoryFilterModel(QSortFilterProxyModel):
    """Filter model for searching chat histories."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._searchText = ""
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def setSearchText(self, text: str):
        self._searchText = text.strip().lower()
        if qtVersion() >= (6, 10, 0):
            self.beginFilterChange()
            self.endFilterChange()
        else:
            self.invalidateFilter()

    def filterAcceptsRow(self, sourceRow, sourceParent):
        if not self._searchText:
            return True

        model = self.sourceModel()
        index = model.index(sourceRow, 0, sourceParent)
        history: AiChatHistory = model.data(index, Qt.UserRole)
        if not history:
            return False

        title = history.title or ""
        if self._searchText in title.lower():
            return True

        for message in history.messages:
            content: str = message.get("content", "")
            if self._searchText in content.lower():
                return True

        return False
