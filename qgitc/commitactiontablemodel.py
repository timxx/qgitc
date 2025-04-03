# -*- coding: utf-8 -*-

from typing import List
from PySide6.QtCore import (
    QAbstractTableModel,
    Signal,
    QModelIndex,
    Qt)


class CommitAction:

    def __init__(self, command: str, args: str = None, mainRepoOnly: bool = False, enabled: bool = True):
        self.command = command
        self.args = args
        self.mainRepoOnly = mainRepoOnly
        self.enabled = enabled


class CommitActionTableModel(QAbstractTableModel):
    Col_Cmd = 0
    Col_Args = 1
    Col_Repos = 2
    Col_Status = 3
    Col_Count = 4

    suffixExists = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._data: List[CommitAction] = []

        self._repos = {
            True: self.tr("Main repo only"),
            False: self.tr("All repos")
        }

        self._status = {
            True: self.tr("Enabled"),
            False: self.tr("Disabled")
        }

    def columnCount(self, parent=QModelIndex()):
        return self.Col_Count

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        if role != Qt.DisplayRole:
            return None

        if section == self.Col_Cmd:
            return self.tr("Command")
        if section == self.Col_Args:
            return self.tr("Arguments")
        if section == self.Col_Repos:
            return self.tr("Run on")
        if section == self.Col_Status:
            return self.tr("Status")

        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        f |= Qt.ItemIsEditable

        return f

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        action: CommitAction = self._data[index.row()]
        col = index.column()
        if role == Qt.DisplayRole or role == Qt.EditRole:
            if col == self.Col_Cmd:
                return action.command
            if col == self.Col_Args:
                return action.args
            if col == self.Col_Repos and role == Qt.DisplayRole:
                return self._repos[action.mainRepoOnly]
            if col == self.Col_Status and role == Qt.DisplayRole:
                return self._status[action.enabled]

        return None

    def setData(self, index: QModelIndex, value, role=Qt.EditRole):
        row = index.row()
        col = index.column()
        action: CommitAction = self._data[row]

        if role == Qt.EditRole:
            value = value.strip()
            if not value:
                return False
            if col == self.Col_Cmd:
                action.command = value
            elif col == self.Col_Args:
                action.args = value
            elif col == self.Col_Repos:
                action.mainRepoOnly = value == self.tr("Main repo only")
            elif col == self.Col_Status:
                action.enabled = value == self.tr("Enabled")
        else:
            return False

        self._data[row] = action
        return True

    def insertRows(self, row, count, parent=QModelIndex()):
        self.beginInsertRows(parent, row, row + count - 1)

        for i in range(count):
            self._data.insert(row, CommitAction(""))

        self.endInsertRows()

        return True

    def removeRows(self, row, count, parent=QModelIndex()):
        if row >= len(self._data):
            return False

        self.beginRemoveRows(parent, row, row + count - 1)

        for i in range(count - 1 + row, row - 1, -1):
            if i < len(self._data):
                del self._data[i]

        self.endRemoveRows()

        return True

    def rawData(self):
        return self._data

    def setRawData(self, data):
        parent = QModelIndex()

        if self._data:
            self.beginRemoveRows(parent, 0, len(self._data) - 1)
            self._data = []
            self.endRemoveRows()

        if data:
            self.beginInsertRows(parent, 0, len(data) - 1)
            self._data = data
            self.endInsertRows()

    def getRepos(self):
        return list(self._repos.values())

    def getStatusNames(self):
        return list(self._status.values())
