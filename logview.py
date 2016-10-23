# --*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from common import *


class LogListModel(QAbstractListModel):

    def __init__(self, parent=None):
        super(LogListModel, self).__init__(parent)

        self.items = []
        self.source = None

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self.items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if index.row() >= len(self.items):
            return None

        commit = self.items[index.row()]
        if role == Qt.DisplayRole:
            return commit.subject
        elif role == Qt.ToolTipRole:
            return '{0} ("{1}", {2} <{3}>, {4})'.format(
                commit.sha1, commit.subject,
                commit.author, commit.email,
                commit.date)
        elif role == Qt.UserRole:
            return commit
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        if index.row() < len(self.items):
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled
        return Qt.NoItemFlags

    def canFetchMore(self, parent):
        if not self.source:
            return False

        return len(self.items) < len(self.source)

    def fetchMore(self, parent):
        offset = len(self.items)
        total = len(self.source)
        limit = min(total - offset, 50)

        self.beginInsertRows(parent, offset, offset + limit)

        for i in range(limit):
            parts = self.source[offset + i].split("\x01")
            commit = Commit(parts[0], parts[1],
                            parts[2], parts[3],
                            parts[4], parts[5].split(" "))
            self.items.append(commit)

        self.endInsertRows()
        # free the source
        if len(self.items) == total:
            self.source = None

    def refreshModel(self):
        self.beginResetModel()
        self.endResetModel()

    def setSource(self, source):
        self.source = source
        self.items.clear()

        self.refreshModel()

        if self.source:
            self.fetchMore(QModelIndex())


class LogView(QListView):

    def __init__(self, parent=None):
        super(LogView, self).__init__(parent)

        model = LogListModel(self)
        self.setModel(model)

    def setLogs(self, commits):
        model = self.model()
        model.setSource(commits)
        index = model.index(0, 0)
        if index.isValid():
            self.setCurrentIndex(index)
            self.clicked.emit(index)

    def clear(self):
        self.model().setSource(None)
