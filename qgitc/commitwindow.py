# -*- coding: utf-8 -*-

from typing import List, Tuple
from PySide6.QtCore import (
    QTimer,
    QAbstractListModel,
    Qt,
    QModelIndex,
    QSortFilterProxyModel
)
from PySide6.QtGui import QFont

from .diffview import _makeTextIcon
from .findsubmodules import FindSubmoduleThread
from .gitutils import Git
from .statewindow import StateWindow
from .statusfetcher import StatusFetcher
from .ui_commitwindow import Ui_CommitWindow


class StatusFileInfo():

    def __init__(self, file: str, repoDir: str, statusCode: str):
        self.file = file
        self.repoDir = repoDir
        self.statusCode = statusCode


class StatusFileListModel(QAbstractListModel):

    StatusCodeRole = Qt.UserRole
    RepoDirRole = Qt.UserRole + 1

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

        return None

    def addFile(self, file: str, repoDir: str, statusCode: str):
        rowCount = self.rowCount()
        self.beginInsertRows(QModelIndex(), rowCount, rowCount)
        self._fileList.append(StatusFileInfo(file, repoDir, statusCode))
        self.endInsertRows()

    def clear(self):
        self.removeRows(0, self.rowCount())

    def _statusIcon(self, statusCode):
        icon = self._icons.get(statusCode)
        if not icon:
            font: QFont = qApp.font()
            font.setBold(True)
            if statusCode == "A":
                color = qApp.colorSchema().Adding
            elif statusCode == "M":
                color = qApp.colorSchema().Modified
            elif statusCode == "D":
                color = qApp.colorSchema().Deletion
            elif statusCode == "R":
                color = qApp.colorSchema().Renamed
            else:
                color = qApp.palette().windowText().color()
            icon = _makeTextIcon(statusCode, color, font)
            self._icons[statusCode] = icon
        return icon


class CommitWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_CommitWindow()
        self.ui.setupUi(self)

        width = self.ui.splitterMain.sizeHint().width()
        sizes = [width * 2 / 5, width * 3 / 5]
        self.ui.splitterMain.setSizes(sizes)

        height = self.ui.splitterRight.sizeHint().height()
        sizes = [height * 3 / 5, height * 2 / 5]
        self.ui.splitterRight.setSizes(sizes)

        self.setWindowTitle(self.tr("QGitc Commit"))

        self._fetcher = StatusFetcher(self)
        self._fetcher.resultAvailable.connect(self._onStatusAvailable)
        self._fetcher.finished.connect(self._onFetchFinished)

        self._filesModel = StatusFileListModel(self)
        filesProxyModel = QSortFilterProxyModel(self)
        filesProxyModel.setSourceModel(self._filesModel)
        self.ui.lvFiles.setModel(filesProxyModel)

        self._stagedModel = StatusFileListModel(self)
        stagedProxyModel = QSortFilterProxyModel(self)
        stagedProxyModel.setSourceModel(self._stagedModel)
        self.ui.lvStaged.setModel(stagedProxyModel)

        QTimer.singleShot(0, self._loadLocalChanges)

        self._findSubmoduleThread = FindSubmoduleThread(Git.REPO_DIR, self)
        self._findSubmoduleThread.finished.connect(
            self._onFindSubmoduleFinished)
        self._findSubmoduleThread.start()

    def _loadLocalChanges(self):
        submodules = qApp.settings().submodulesCache(Git.REPO_DIR)
        self._fetcher.fetch(submodules)

    def clear(self):
        self._filesModel.clear()
        self._stagedModel.clear()

    def _onFindSubmoduleFinished(self):
        submodules = self._findSubmoduleThread.submodules
        if not submodules:
            return

        # TODO: only fetch newly added submodules
        self.clear()
        self._fetcher.fetch(submodules)

    def _onStatusAvailable(self, repoDir: str, fileList: List[Tuple[str, str]]):
        for status, file in fileList:
            if status[0] != " " and status[0] != "?":
                self._stagedModel.addFile(file, repoDir, status[0])
            if status[1] != " ":
                self._filesModel.addFile(file, repoDir, status[1])

    def _onFetchFinished(self):
        print("Fetch finished")
