# -*- coding: utf-8 -*-

from enum import Enum
import os
from typing import List, Tuple
from PySide6.QtCore import (
    QTimer,
    QAbstractListModel,
    Qt,
    QModelIndex,
    QSortFilterProxyModel
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView
)

from .difffetcher import DiffFetcher
from .diffview import _makeTextIcon
from .findsubmodules import FindSubmoduleThread
from .gitutils import Git
from .statewindow import StateWindow
from .statusfetcher import StatusFetcher
from .ui_commitwindow import Ui_CommitWindow


class FileStatus(Enum):

    Untracked = 0
    Unstaged = 1
    Staged = 2


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
        sizes = [height * 4 / 5, height * 1 / 5]
        self.ui.splitterRight.setSizes(sizes)

        self.setWindowTitle(self.tr("QGitc Commit"))

        self._statusFetcher = StatusFetcher(self)
        self._statusFetcher.resultAvailable.connect(self._onStatusAvailable)
        self._statusFetcher.finished.connect(self._onStatusFetchFinished)

        self._diffFetcher = DiffFetcher(self)
        self._diffFetcher.diffAvailable.connect(
            self._onDiffAvailable)
        self._diffFetcher.fetchFinished.connect(
            self._onDiffFetchFinished)

        self._filesModel = StatusFileListModel(self)
        filesProxyModel = QSortFilterProxyModel(self)
        filesProxyModel.setSourceModel(self._filesModel)
        self.ui.lvFiles.setModel(filesProxyModel)
        self.ui.lvFiles.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ui.lvFiles.selectionModel().currentRowChanged.connect(
            self._onSelectFileChanged)
        self.ui.lvFiles.clicked.connect(
            self._onFileClicked)

        self._stagedModel = StatusFileListModel(self)
        stagedProxyModel = QSortFilterProxyModel(self)
        stagedProxyModel.setSourceModel(self._stagedModel)
        self.ui.lvStaged.setModel(stagedProxyModel)
        self.ui.lvStaged.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ui.lvStaged.selectionModel().currentRowChanged.connect(
            self._onStagedSelectFileChanged)
        self.ui.lvStaged.clicked.connect(
            self._onStagedFileClicked)

        QTimer.singleShot(0, self._loadLocalChanges)

        self._findSubmoduleThread = FindSubmoduleThread(Git.REPO_DIR, self)
        self._findSubmoduleThread.finished.connect(
            self._onFindSubmoduleFinished)
        self._findSubmoduleThread.start()

        self._curFile: str = None
        self._curFileStatus: FileStatus = None

        self._setupSpinner(self.ui.spinnerUnstaged)
        self._setupSpinner(self.ui.spinnerDiff)

        self._diffSpinnerDelayTimer = QTimer(self)
        self._diffSpinnerDelayTimer.setSingleShot(True)
        self._diffSpinnerDelayTimer.timeout.connect(self.ui.spinnerDiff.start)

    def _setupSpinner(self, spinner):
        height = self.ui.lbUnstaged.height() // 7
        spinner.setLineLength(height)
        spinner.setInnerRadius(height)
        spinner.setNumberOfLines(14)

    def _loadLocalChanges(self):
        submodules = qApp.settings().submodulesCache(Git.REPO_DIR)
        self._statusFetcher.fetch(submodules)
        self.ui.spinnerUnstaged.start()

    def clear(self):
        self._filesModel.clear()
        self._stagedModel.clear()

    def _onFindSubmoduleFinished(self):
        submodules = self._findSubmoduleThread.submodules
        caches = qApp.settings().submodulesCache(Git.REPO_DIR)

        newSubmodules = list(set(submodules) - set(caches))
        # no new submodules, no need to fetch
        if not newSubmodules:
            return

        qApp.settings().setSubmodulesCache(Git.REPO_DIR, submodules)

        if self._statusFetcher.isRunning():
            self._statusFetcher.addTask(newSubmodules)
        else:
            self._statusFetcher.fetch(newSubmodules)

    def _onStatusAvailable(self, repoDir: str, fileList: List[Tuple[str, str]]):
        for status, file in fileList:
            if status[0] != " " and status[0] != "?":
                self._stagedModel.addFile(file, repoDir, status[0])
            if status[1] != " ":
                self._filesModel.addFile(file, repoDir, status[1])

    def _onStatusFetchFinished(self):
        self.ui.spinnerUnstaged.stop()

    def _onSelectFileChanged(self, current: QModelIndex, previous: QModelIndex):
        self.ui.viewer.clear()
        if not current.isValid():
            return

        self._showIndexDiff(current)

    def _onStagedSelectFileChanged(self, current: QModelIndex, previous: QModelIndex):
        self.ui.viewer.clear()
        if not current.isValid():
            return

        file = self._filesModel.data(current, Qt.DisplayRole)
        repoDir = self._filesModel.data(
            current, StatusFileListModel.RepoDirRole)

        self._showDiff(file, repoDir, FileStatus.Staged)

    def _showIndexDiff(self, index: QModelIndex, fromStaged=False):
        model = self._stagedModel if fromStaged else self._filesModel

        file = model.data(index, Qt.DisplayRole)
        repoDir = model.data(index, StatusFileListModel.RepoDirRole)

        if fromStaged:
            fileStatus = FileStatus.Staged
        elif model.data(index, StatusFileListModel.StatusCodeRole) == "?":
            fileStatus = FileStatus.Untracked
        else:
            fileStatus = FileStatus.Unstaged

        self._showDiff(file, repoDir, fileStatus)

    def _showDiff(self, file: str, repoDir: str, status: FileStatus):
        if file == self._curFile and status == self._curFileStatus:
            return

        self.ui.viewer.clear()
        self._diffFetcher.resetRow(0)

        if repoDir and repoDir != ".":
            self._diffFetcher.cwd = os.path.join(Git.REPO_DIR, repoDir)
            self._diffFetcher.repoDir = repoDir
        else:
            self._diffFetcher.cwd = Git.REPO_DIR
            self._diffFetcher.repoDir = None

        if status == FileStatus.Unstaged:
            sha1 = Git.LUC_SHA1
        elif status == FileStatus.Staged:
            sha1 = Git.LCC_SHA1
        else:
            sha1 = None

        self._curFile = file
        self._curFileStatus = status
        self._diffFetcher.fetch(sha1, [file], None)
        self._diffSpinnerDelayTimer.start(1000)

    def _onDiffAvailable(self, lineItems, fileItems):
        self.ui.viewer.appendLines(lineItems)

    def _onDiffFetchFinished(self, exitCode):
        self._diffSpinnerDelayTimer.stop()
        self.ui.spinnerDiff.stop()

    def _onFileClicked(self, index: QModelIndex):
        self._showIndexDiff(index)

    def _onStagedFileClicked(self, index: QModelIndex):
        self._showIndexDiff(index, True)
