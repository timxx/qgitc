# -*- coding: utf-8 -*-

from typing import List

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from qgitc.applicationbase import ApplicationBase


class StatusFileInfo():

    def __init__(self, file: str, repoDir: str, statusCode: str, oldFile: str = None):
        self.file = file
        self.repoDir = repoDir
        self.statusCode = statusCode
        self.oldFile = oldFile


class StatusFileItemDelegate(QStyledItemDelegate):

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        option.features |= QStyleOptionViewItem.HasDecoration

        self._drawBackground(painter, option)
        self._drawDecoration(painter, option, index)
        self._drawText(painter, option, index)

    def _drawBackground(self, painter: QPainter, option: QStyleOptionViewItem):
        colorSchema = ApplicationBase.instance().colorSchema()

        borderRect = QRectF(option.rect)
        borderRect.adjust(0.5, 0.5, -0.5, -0.5)
        if option.state & QStyle.State_Selected:
            painter.fillRect(borderRect, colorSchema.SelectedItemBg)
            if option.state & QStyle.State_HasFocus:
                oldPen = painter.pen()
                pen = QPen(colorSchema.FocusItemBorder)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawRect(borderRect)
                painter.setPen(oldPen)
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(borderRect, colorSchema.HoverItemBg)

    def _drawDecoration(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        status = index.data(Qt.DecorationRole)
        assert isinstance(status, str)

        color = self._toStatusColor(status)
        iconRect = option.widget.style().subElementRect(
            QStyle.SE_ItemViewItemDecoration, option, option.widget)
        font = QFont(option.font)
        font.setBold(True)

        oldFont = painter.font()
        oldPen = painter.pen()
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(iconRect, Qt.AlignVCenter | Qt.AlignHCenter, status)
        painter.setFont(oldFont)
        painter.setPen(oldPen)

    def _drawText(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        text = index.data(Qt.DisplayRole)
        if not text:
            return

        textRect = option.widget.style().subElementRect(
            QStyle.SE_ItemViewItemText, option, option.widget)
        repoDir = index.data(StatusFileListModel.RepoDirRole)
        if repoDir and repoDir != ".":
            repoText = text[:len(repoDir)+1]
            text = text[len(repoDir)+1:]
            oldPen = painter.pen()
            painter.setPen(ApplicationBase.instance().colorSchema().RepoTagFg)
            br = painter.drawText(
                textRect, Qt.AlignVCenter | Qt.AlignLeft, repoText)
            painter.setPen(oldPen)
            textRect.setLeft(br.right())

        painter.drawText(textRect, Qt.AlignVCenter | Qt.AlignLeft, text)

    def _toStatusColor(self, statusCode):
        if statusCode == "A":
            return ApplicationBase.instance().colorSchema().Adding
        elif statusCode == "M":
            return ApplicationBase.instance().colorSchema().Modified
        elif statusCode == "D":
            return ApplicationBase.instance().colorSchema().Deletion
        elif statusCode == "R":
            return ApplicationBase.instance().colorSchema().Renamed
        elif statusCode == "?":
            return ApplicationBase.instance().colorSchema().Untracked
        elif statusCode == "!":
            return ApplicationBase.instance().colorSchema().Ignored

        return ApplicationBase.instance().palette().windowText().color()


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
            return self._fileList[row].statusCode
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
