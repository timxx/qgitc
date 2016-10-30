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
            return commit.comments.split("\n")[0]  # TODO: improve
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
            commit = Commit()
            commit.parseRawString(self.source[offset + i])
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

    # TODO: improve performance
    def findCommitIndex(self, sha1):
        i = -1
        index = QModelIndex()

        # find in loaded items
        for item in self.items:
            i += 1
            if item.sha1.startswith(sha1):
                index = self.index(i, 0)
                break

        # load the rest and find it
        while not index.isValid() and self.source:
            self.fetchMore(QModelIndex())
            new_items_count = len(self.items) - i - 1
            for j in range(new_items_count):
                commit = self.items[i + j]
                if commit.sha1.startswith(sha1):
                    index = self.index(i + j, 0)
                    break

        return index


class LogView(QListView):

    def __init__(self, parent=None):
        super(LogView, self).__init__(parent)

        model = LogListModel(self)
        self.setModel(model)

        self.sha1Color = "#FF0000"
        self.subjectColor = "#0000FF"

        self.menu = QMenu()
        self.menu.addAction(self.tr("&Copy commit summary"),
                            self.__onCopyCommitSummary)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)

    def setLogs(self, commits):
        model = self.model()
        model.setSource(commits)
        index = model.index(0, 0)
        if index.isValid():
            self.setCurrentIndex(index)
            self.clicked.emit(index)

    def clear(self):
        self.model().setSource(None)

    def switchToCommit(self, sha1):
        # ignore if sha1 same as current's
        index = self.currentIndex()
        if index.isValid():
            commit = self.model().data(index, Qt.UserRole)
            if commit and commit.sha1.startswith(sha1):
                return True

        index = self.model().findCommitIndex(sha1)
        if index.isValid():
            self.setCurrentIndex(index)
            self.clicked.emit(index)

        return index.isValid()

    def showContextMenu(self, pos):
        if self.currentIndex().isValid():
            globalPos = self.mapToGlobal(pos)
            self.menu.exec(globalPos)

    def __onCopyCommitSummary(self):
        index = self.currentIndex()
        if not index.isValid():
            return
        commit = self.model().data(index, Qt.UserRole)
        if not commit:
            return

        commit = getCommitSummary(commit.sha1)

        clipboard = QApplication.clipboard()

        htmlText = '<html>\n'
        htmlText += '<body>\n'
        htmlText += '<p style="font-size:10pt">'
        htmlText += self.__htmlColorText(self.sha1Color, commit["sha1"])
        htmlText += ' ("'
        htmlText += self.__htmlColorText(self.subjectColor, commit["subject"])
        htmlText += '", '
        htmlText += commit["date"]
        htmlText += ')</p>\n'
        htmlText += '</body>\n'
        htmlText += '</html>\n'

        mimeData = QMimeData()
        mimeData.setHtml(htmlText)
        mimeData.setText('{0} ("{1}"), {2}'.format(
            commit["sha1"],
            commit["subject"],
            commit["date"]))

        clipboard.setMimeData(mimeData)

    def __htmlColorText(self, color, text):
        return '<font color="{0}">{1}</font>'.format(
            color, htmlEscape(text))
