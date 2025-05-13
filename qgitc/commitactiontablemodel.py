# -*- coding: utf-8 -*-

from enum import Enum
from typing import List

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal


class ActionCondition(Enum):
    MainRepoOnly = 0
    EachRepo = 1
    AllCommitted = 2


class CommitAction:

    def __init__(self, command: str, args: str = None, condition=ActionCondition.EachRepo, enabled: bool = True):
        self.command = command
        self.args = args
        self.condition = condition
        self.enabled = enabled


class CommitActionTableModel(QAbstractTableModel):
    Col_Cmd = 0
    Col_Args = 1
    Col_Condition = 2
    Col_Status = 3
    Col_Count = 4

    suffixExists = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._data: List[CommitAction] = []

        self._conditions = {
            ActionCondition.MainRepoOnly: self.tr("Main Repo Only"),
            ActionCondition.EachRepo: self.tr("Each Repo"),
            ActionCondition.AllCommitted: self.tr("All Committed")
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
        if section == self.Col_Condition:
            return self.tr("Condition")
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
            if col == self.Col_Condition and role == Qt.DisplayRole:
                return self._conditions[action.condition]
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
            elif col == self.Col_Condition:
                action.condition = list(self._conditions.keys())[
                    list(self._conditions.values()).index(value)]
            elif col == self.Col_Status:
                action.enabled = list(self._status.keys())[
                    list(self._status.values()).index(value)]
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

    def getConditionNames(self):
        return list(self._conditions.values())

    def getStatusNames(self):
        return list(self._status.values())
