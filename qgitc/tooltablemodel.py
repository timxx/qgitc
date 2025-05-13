# -*- coding: utf-8 -*-

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal

from qgitc.mergetool import MergeTool


class ToolTableModel(QAbstractTableModel):
    Col_Scenes = 0
    Col_Suffix = 1
    Col_Tool = 2

    suffixExists = Signal(str)

    def __init__(self, parent=None):
        super(ToolTableModel, self).__init__(parent)

        self._data = []
        self._scenes = {MergeTool.Nothing: self.tr("Disabled"),
                        MergeTool.CanDiff: self.tr("Diff"),
                        MergeTool.CanMerge: self.tr("Merge"),
                        MergeTool.Both: self.tr("Both")}

    def _checkSuffix(self, row, suffix):
        for i in range(len(self._data)):
            if i == row:
                continue
            tool = self._data[i]
            if tool.suffix == suffix:
                return False

        return True

    def columnCount(self, parent=QModelIndex()):
        return 3

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        if role != Qt.DisplayRole:
            return None

        if section == self.Col_Scenes:
            return self.tr("Scenes")
        if section == self.Col_Suffix:
            return self.tr("Suffix")
        if section == self.Col_Tool:
            return self.tr("Tool")

        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        f |= Qt.ItemIsEditable

        return f

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        tool = self._data[index.row()]
        col = index.column()
        if role == Qt.DisplayRole or role == Qt.EditRole:
            if col == self.Col_Suffix:
                return tool.suffix
            if col == self.Col_Tool:
                return tool.command
            if col == self.Col_Scenes and role == Qt.DisplayRole:
                return self._scenes[tool.capabilities]

        return None

    def setData(self, index, value, role=Qt.EditRole):
        row = index.row()
        col = index.column()
        tool = self._data[row]

        if role == Qt.EditRole:
            value = value.strip()
            if not value:
                return False
            if col == self.Col_Suffix:
                if not self._checkSuffix(row, value):
                    self.suffixExists.emit(value)
                    return False
                tool.suffix = value
            elif col == self.Col_Tool:
                tool.command = value
            elif col == self.Col_Scenes:
                idx = list(self._scenes.values()).index(value)
                tool.capabilities = list(self._scenes.keys())[idx]
        else:
            return False

        self._data[row] = tool
        return True

    def insertRows(self, row, count, parent=QModelIndex()):
        self.beginInsertRows(parent, row, row + count - 1)

        for i in range(count):
            self._data.insert(row, MergeTool(MergeTool.Both))

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

    def getSceneNames(self):
        return self._scenes.values()
