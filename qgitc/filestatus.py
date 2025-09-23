# -*- coding: utf-8 -*-

from typing import List

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtGui import QFont

from qgitc.applicationbase import ApplicationBase
from qgitc.diffview import _makeTextIcon


class StatusFileInfo():

    def __init__(self, file: str, repoDir: str, statusCode: str, oldFile: str = None):
        self.file = file
        self.repoDir = repoDir
        self.statusCode = statusCode
        self.oldFile = oldFile


class StatusFileListModel(QAbstractListModel):

    StatusCodeRole = Qt.UserRole
    RepoDirRole = Qt.UserRole + 1
    OldFileRole = Qt.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fileList: List[StatusFileInfo] = []
        self._icons = {}

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0

        return len(self._fileList)

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def removeRows(self, row, count, parent=QModelIndex()):
        if row < 0 or (row + count) > self.rowCount(parent) or count < 1:
            return False

        self.beginRemoveRows(QModelIndex(), row, row + count - 1)
        del self._fileList[row: row + count]
        self.endRemoveRows()

        return True

    def data(self, index, role=Qt.DisplayRole):
        row = index.row()
        if row < 0 or row >= self.rowCount():
            return False

        if role == Qt.DisplayRole:
            return self._fileList[row].file
        elif role == StatusFileListModel.StatusCodeRole:
            return self._fileList[row].statusCode
        elif role == StatusFileListModel.RepoDirRole:
            return self._fileList[row].repoDir
        elif role == Qt.DecorationRole:
            return self._statusIcon(self._fileList[row].statusCode)
        elif role == Qt.ToolTipRole:
            oldFile = self._fileList[row].oldFile
            if oldFile:
                return self.tr("Renamed from: ") + oldFile
        elif role == StatusFileListModel.OldFileRole:
            return self._fileList[row].oldFile

        return None

    def addFile(self, file: str, repoDir: str, statusCode: str, oldFile: str = None):
        rowCount = self.rowCount()
        self.beginInsertRows(QModelIndex(), rowCount, rowCount)
        self._fileList.append(StatusFileInfo(
            file, repoDir, statusCode, oldFile))
        self.endInsertRows()

    def removeFile(self, file: str, repoDir: str):
        if not self._fileList:
            return None

        for i, fileInfo in enumerate(self._fileList):
            if fileInfo.file == file and fileInfo.repoDir == repoDir:
                break
        else:
            return None

        self.beginRemoveRows(QModelIndex(), i, i)
        info = self._fileList.pop(i)
        self.endRemoveRows()
        return info

    def clear(self):
        self.removeRows(0, self.rowCount())

    def _statusIcon(self, statusCode):
        icon = self._icons.get(statusCode)
        if not icon:
            font: QFont = ApplicationBase.instance().font()
            font.setBold(True)
            if statusCode == "A":
                color = ApplicationBase.instance().colorSchema().Adding
            elif statusCode == "M":
                color = ApplicationBase.instance().colorSchema().Modified
            elif statusCode == "D":
                color = ApplicationBase.instance().colorSchema().Deletion
            elif statusCode == "R":
                color = ApplicationBase.instance().colorSchema().Renamed
            elif statusCode == "?":
                color = ApplicationBase.instance().colorSchema().Untracked
            elif statusCode == "!":
                color = ApplicationBase.instance().colorSchema().Ignored
            else:
                color = ApplicationBase.instance().palette().windowText().color()
            icon = _makeTextIcon(statusCode, color, font)
            self._icons[statusCode] = icon
        return icon
