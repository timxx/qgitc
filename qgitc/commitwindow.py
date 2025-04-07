# -*- coding: utf-8 -*-

from enum import Enum
import os
import subprocess
from typing import Dict, List, Tuple
from PySide6.QtCore import (
    QTimer,
    QAbstractListModel,
    Qt,
    QModelIndex,
    QSortFilterProxyModel,
    QEvent,
    QSize
)
from PySide6.QtGui import (
    QFont,
    QIcon,
    QTextCursor,
    QTextCharFormat
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QMessageBox,
    QListView,
    QMenu,
    QWidget,
    QHBoxLayout,
    QLabel,
    QDialog,
    QStyle
)

from .aicommitmessage import AiCommitMessage
from .colorediconlabel import ColoredIconLabel
from .coloredlabel import ColoredLabel
from .commitactiontablemodel import ActionCondition, CommitAction
from .common import dataDirPath, decodeFileData, toSubmodulePath
from .difffetcher import DiffFetcher
from .diffview import DiffView, _makeTextIcon
from .events import CodeReviewEvent, LocalChangesCommittedEvent, ShowCommitEvent
from .findsubmodules import FindSubmoduleThread
from .gitutils import Git
from .preferences import Preferences
from .submoduleexecutor import SubmoduleExecutor
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

    def tryAddFile(self, file: str, repoDir: str, statusCode: str):
        for fileInfo in self._fileList:
            if fileInfo.file == file and fileInfo.repoDir == repoDir:
                return False

        self.addFile(file, repoDir, statusCode)
        return True

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
            elif statusCode == "?":
                color = qApp.colorSchema().Untracked
            elif statusCode == "!":
                color = qApp.colorSchema().Ignored
            else:
                color = qApp.palette().windowText().color()
            icon = _makeTextIcon(statusCode, color, font)
            self._icons[statusCode] = icon
        return icon


class UpdateFilesEvent(QEvent):
    Type = QEvent.User + 1

    def __init__(self, isStaged: bool, submodule: str, files: List[str]):
        super().__init__(QEvent.Type(UpdateFilesEvent.Type))
        self.isStaged = isStaged
        self.submodule = submodule
        self.files = files


class GitErrorEvent(QEvent):
    Type = QEvent.User + 2

    def __init__(self, error: str):
        super().__init__(QEvent.Type(GitErrorEvent.Type))
        self.error = error


class RepoInfo:

    def __init__(self):
        self.userName: str = None
        self.userEmail: str = None
        self.branch: str = None


class RepoInfoEvent(QEvent):
    Type = QEvent.User + 3

    def __init__(self, info: RepoInfo):
        super().__init__(QEvent.Type(RepoInfoEvent.Type))
        self.info = info


class TemplateReadyEvent(QEvent):
    Type = QEvent.User + 4

    def __init__(self, template: str):
        super().__init__(QEvent.Type(TemplateReadyEvent.Type))
        self.template = template


class UpdateCommitProgressEvent(QEvent):
    Type = QEvent.User + 5

    def __init__(self, submodule: str, out: str, error: str, updateProgress: bool = True):
        super().__init__(QEvent.Type(UpdateCommitProgressEvent.Type))
        self.submodule = submodule
        self.out = out
        self.error = error
        self.updateProgress = updateProgress


class CommitWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_CommitWindow()
        self.ui.setupUi(self)
        self.ui.teMessage.setFocus()

        width = self.ui.splitterMain.sizeHint().width()
        sizes = [width * 2 / 5, width * 3 / 5]
        self.ui.splitterMain.setSizes(sizes)

        height = self.ui.splitterRight.sizeHint().height()
        sizes = [height * 3 / 5, height * 2 / 5]
        self.ui.splitterRight.setSizes(sizes)

        self.setWindowTitle(self.tr("QGitc Commit"))

        self._statusFetcher = StatusFetcher(self)
        self._statusFetcher.resultAvailable.connect(self._onStatusAvailable)
        self._statusFetcher.finished.connect(self._onStatusFetchFinished)
        self._statusFetcher.branchInfoAvailable.connect(
            self._onBranchInfoAvailable)

        self._repoBranch = {}

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
        self.ui.lvFiles.setEmptyStateText(
            self.tr("There are no unstaged changes"))

        self._stagedModel = StatusFileListModel(self)
        stagedProxyModel = QSortFilterProxyModel(self)
        stagedProxyModel.setSourceModel(self._stagedModel)
        self.ui.lvStaged.setModel(stagedProxyModel)
        self.ui.lvStaged.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ui.lvStaged.selectionModel().currentRowChanged.connect(
            self._onStagedSelectFileChanged)
        self.ui.lvStaged.clicked.connect(
            self._onStagedFileClicked)
        self.ui.lvStaged.setEmptyStateText(
            self.tr("There are no staged changes"))

        self._stagedModel.rowsInserted.connect(self._onStagedFilesChanged)
        self._stagedModel.rowsRemoved.connect(self._onStagedFilesChanged)

        self.ui.btnCommit.setEnabled(False)
        self.ui.btnGenMessage.setEnabled(False)

        iconsPath = dataDirPath() + "/icons/"
        self.ui.tbUnstage.setIcon(QIcon(iconsPath + "unstage.svg"))
        self.ui.tbUnstage.clicked.connect(
            self._onUnstageClicked)

        self.ui.tbUnstageAll.setIcon(QIcon(iconsPath + "unstage-all.svg"))
        self.ui.tbUnstageAll.setToolTip(self.tr("Unstage all"))
        self.ui.tbUnstageAll.clicked.connect(
            self._onUnstageAllClicked)

        self.ui.tbStage.setIcon(QIcon(iconsPath + "stage.svg"))
        self.ui.tbStage.clicked.connect(
            self._onStageClicked)

        self.ui.tbStageAll.setIcon(QIcon(iconsPath + "stage-all.svg"))
        self.ui.tbStageAll.setToolTip(self.tr("Stage all"))
        self.ui.tbStageAll.clicked.connect(
            self._onStageAllClicked)

        self.ui.tbRefresh.setIcon(QIcon(iconsPath + "refresh.svg"))
        self.ui.tbRefresh.setToolTip(self.tr("Refresh"))
        self.ui.tbRefresh.clicked.connect(self.reloadLocalChanges)

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

        self.ui.teMessage.setPlaceholderText(
            self.tr("Enter commit message here..."))

        self.ui.btnCommit.clicked.connect(self._onCommitClicked)

        # no UI tasks
        self._submoduleExecutor = SubmoduleExecutor(self)
        self._submoduleExecutor.finished.connect(
            self._onNonUITaskFinished)

        self._committedActions = []
        self._commitExecutor = SubmoduleExecutor(self)
        self._commitExecutor.finished.connect(
            self._onCommitFinished)

        infoFetcher = SubmoduleExecutor(self)
        infoFetcher.finished.connect(self._onInfoFetchFinished)
        infoFetcher.submit(None, self._fetchRepoInfo)
        self._repoInfo: RepoInfo = None

        self._setupWDMenu()
        self._setupStatusBar()

        self.ui.tbOptions.setIcon(QIcon(iconsPath + "settings.svg"))
        self.ui.tbOptions.clicked.connect(self._onOptionsClicked)

        self.ui.btnAction.clicked.connect(
            self._onCommitActionClicked)

        self.ui.cbRunAction.setChecked(
            qApp.settings().runCommitActions())
        self.ui.cbRunAction.toggled.connect(
            lambda checked: qApp.settings().setRunCommitActions(checked))

        self.ui.leFilterFiles.textChanged.connect(
            self._onFilterFilesChanged)
        self.ui.leFilterStaged.textChanged.connect(
            self._onFilterStagedChanged)

        self.ui.cbAmend.toggled.connect(
            self._updateCommitButtonState)

        if not qApp.style().styleHint(QStyle.SH_ItemView_ActivateItemOnSingleClick):
            self.ui.lvFiles.activated.connect(
                self._onFilesDoubleClicked)
            self.ui.lvStaged.activated.connect(
                self._onStagedDoubleClicked)
        else:
            self.ui.lvFiles.doubleClicked.connect(
                self._onFilesDoubleClicked)
            self.ui.lvStaged.doubleClicked.connect(
                self._onStagedDoubleClicked)

        icon = QIcon(iconsPath + "/wand-stars.svg")
        self.ui.btnGenMessage.setIcon(icon)
        self.ui.btnGenMessage.setIconSize(QSize(16, 16))
        self.ui.btnGenMessage.clicked.connect(
            self._onGenMessageClicked)

        icon = QIcon(iconsPath + "/stop.svg")
        self.ui.btnCancelGen.setIcon(icon)
        self.ui.btnCancelGen.setIconSize(QSize(16, 16))
        self.ui.btnCancelGen.clicked.connect(
            self._onCancelGenMessageClicked)
        self.ui.btnCancelGen.hide()

        self._aiMessage = AiCommitMessage(self)
        self._aiMessage.messageAvailable.connect(
            self._onAiMessageAvailable)

        icon = QIcon(iconsPath + "/reviews.svg")
        self.ui.btnCodeReview.setIcon(icon)
        self.ui.btnCodeReview.clicked.connect(
            self._onCodeReviewClicked)
        self.ui.btnCodeReview.setEnabled(False)

        icon = QIcon(iconsPath + "/commit.svg")
        self.ui.btnShowLog.setIcon(icon)
        self.ui.btnShowLog.clicked.connect(
            self._onShowCommitClicked)

    def _setupSpinner(self, spinner):
        height = self.ui.tbRefresh.height() // 7
        spinner.setLineLength(height)
        spinner.setInnerRadius(height)
        spinner.setNumberOfLines(14)

    def _loadLocalChanges(self):
        submodules = qApp.settings().submodulesCache(Git.REPO_DIR)
        self._statusFetcher.fetch(submodules)
        self.ui.tbRefresh.setEnabled(False)
        self.ui.tbWDChanges.setEnabled(False)
        self.ui.spinnerUnstaged.start()

    def clear(self):
        self._filesModel.clear()
        self._stagedModel.clear()
        self._curFile = None
        self._curFileStatus = None
        self._repoBranch.clear()
        self._branchMessage.clear()
        self._branchWidget.setVisible(False)

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
            if status[0] != " " and status[0] not in ["?", "!"]:
                self._stagedModel.addFile(file, repoDir, status[0])
            if status[1] != " ":
                self._filesModel.addFile(file, repoDir, status[1])

    def _onBranchInfoAvailable(self, repoDir: str, branch: str):
        self._repoBranch.setdefault(repoDir, branch)

    def _onStatusFetchFinished(self):
        self.ui.spinnerUnstaged.stop()
        self.ui.tbRefresh.setEnabled(True)
        self.ui.tbWDChanges.setEnabled(True)

        # check if all branch in self._repoBranch are same
        branches = set(self._repoBranch.values())
        if len(branches) > 1:
            msg = self.tr("Inconsistent branches")
            self._branchMessage.setText(msg)
            self._branchWidget.setVisible(True)

            tooltip = self.tr("You have different branches in submodules:")
            for repoDir, branch in self._repoBranch.items():
                if not repoDir or repoDir == ".":
                    repoDir = "<main>"
                tooltip += "\n  {}: {}".format(repoDir, branch)
            self._branchMessage.setToolTip(tooltip)

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
        model = self.ui.lvStaged.model() if fromStaged else self.ui.lvFiles.model()

        file = model.data(index, Qt.DisplayRole)
        repoDir = model.data(index, StatusFileListModel.RepoDirRole)

        if fromStaged:
            fileStatus = FileStatus.Staged
        elif model.data(index, StatusFileListModel.StatusCodeRole) in ["?", "!"]:
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

    def _onCommitClicked(self):
        if not self._checkMessage():
            return

        amend = self.ui.cbAmend.isChecked()
        message = self._filterMessage(
            self.ui.teMessage.toPlainText().strip())

        if self.ui.cbRunAction.isChecked():
            allActions = qApp.settings().commitActions()
            actions = []
            self._committedActions = []
            for action in allActions:
                if not action.enabled:
                    continue
                if not action.command:
                    continue
                if action.condition == ActionCondition.AllCommitted:
                    self._committedActions.append(action)
                else:
                    actions.append(action)
        else:
            actions = []
            self._committedActions = []

        submodules = {}
        for row in range(self._stagedModel.rowCount()):
            index = self._stagedModel.index(row, 0)
            repoDir = self._stagedModel.data(
                index, StatusFileListModel.RepoDirRole)
            submodules.setdefault(repoDir, (message, amend, actions))

        # amend to main repo
        if not submodules:
            assert (amend)
            submodules[None] = (message, amend, actions)

        self.ui.progressBar.setRange(
            0, len(submodules) + len(self._committedActions))
        self.ui.progressBar.setValue(0)
        self.ui.teOutput.clear()
        self._updateCommitStatus(True)
        self.ui.stackedWidget.setCurrentWidget(self.ui.pageProgress)
        self._commitExecutor.submit(submodules, self._doCommit)

    def _checkMessage(self):
        if self.ui.cbAmend.isChecked() and self.ui.lvStaged.model().rowCount() > 0:
            return True

        if not self._isMessageValid():
            content = self.tr("Please enter a valid commit message.")
            message = self.ui.teMessage.toPlainText().strip()
            message = self._filterMessage(message)
            if not message:
                content += "\n" + self.tr("Commit message cannot be empty.")
            QMessageBox.critical(
                self,
                self.tr("Invalid commit message"),
                content,
                QMessageBox.Ok)
            return False

        return True

    def _isMessageValid(self):
        message = self.ui.teMessage.toPlainText().strip()
        if not message:
            return False

        message = self._filterMessage(message)
        if not message:
            return False

        # TODO: verify with template or other rules
        return True

    def _filterMessage(self, message: str):
        ignoreCommentLine = qApp.settings().ignoreCommentLine()
        if not ignoreCommentLine:
            return message

        lines = message.splitlines()
        newMessage = ""
        for line in lines:
            if line.startswith("#"):
                continue
            newMessage += line + "\n"
        newMessage = newMessage.rstrip()

        return newMessage

    def _onStagedFilesChanged(self, parent: QModelIndex, first, last):
        self._updateCommitButtonState()

    def _updateCommitButtonState(self):
        hasStagedFiles = self._stagedModel.rowCount() > 0
        enabled = hasStagedFiles or self.ui.cbAmend.isChecked()
        self.ui.btnCommit.setEnabled(enabled)
        self.ui.btnGenMessage.setEnabled(hasStagedFiles)
        self.ui.btnCodeReview.setEnabled(hasStagedFiles)

    def _doCommit(self, submodule: str, userData: Tuple[str, bool, list]):
        amend = userData[1]
        message = userData[0]

        actions: List[CommitAction] = userData[2]

        out, error = Git.commit(message, amend, submodule)
        self._updateCommitProgress(submodule, out, error, not actions)
        if not actions:
            return

        out, error = None, None
        for action in actions:
            o, e = CommitWindow._runCommitAction(submodule, action)
            if o:
                out = out + "\n" + o if out else o
            if e:
                error = error + "\n" + e if error else e

        self._updateCommitProgress(submodule, out, error)

    def _collectSectionFiles(self, view: QListView):
        indexes = view.selectionModel().selectedRows()
        if not indexes:
            return {}

        model = view.model()
        submoduleFiles = {}
        for index in indexes:
            file = model.data(index, Qt.DisplayRole)
            repoDir = model.data(
                index, StatusFileListModel.RepoDirRole)
            submoduleFiles.setdefault(repoDir, []).append(file)

        return submoduleFiles

    def _collectModelFiles(self, model: QAbstractListModel):
        submoduleFiles = {}
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            file = model.data(index, Qt.DisplayRole)
            repoDir = model.data(
                index, StatusFileListModel.RepoDirRole)
            submoduleFiles.setdefault(repoDir, []).append(file)

        return submoduleFiles

    def _onUnstageClicked(self):
        submoduleFiles = self._collectSectionFiles(self.ui.lvStaged)
        if not submoduleFiles:
            return

        self._blockUI()
        self.ui.spinnerUnstaged.start()
        self._submoduleExecutor.submit(submoduleFiles, self._doUnstage)

    def _onUnstageAllClicked(self):
        submoduleFiles = self._collectModelFiles(self.ui.lvStaged.model())
        if not submoduleFiles:
            return

        self._blockUI()
        self.ui.spinnerUnstaged.start()
        self._submoduleExecutor.submit(submoduleFiles, self._doUnstage)
        self._curFile = None
        self._curFileStatus = None

    def _onStageClicked(self):
        submoduleFiles = self._collectSectionFiles(self.ui.lvFiles)
        if not submoduleFiles:
            return

        self._blockUI()
        self.ui.spinnerUnstaged.start()
        self._submoduleExecutor.submit(submoduleFiles, self._doStage)

    def _onStageAllClicked(self):
        submoduleFiles = self._collectModelFiles(self.ui.lvFiles.model())
        if not submoduleFiles:
            return

        self._blockUI()
        self.ui.spinnerUnstaged.start()
        self._submoduleExecutor.submit(submoduleFiles, self._doStage)
        self._curFile = None
        self._curFileStatus = None

    @staticmethod
    def _toRepoDir(submodule: str):
        if not submodule or submodule == ".":
            return Git.REPO_DIR
        return os.path.join(Git.REPO_DIR, submodule)

    def _doUnstage(self, submodule: str, files: List[str]):
        repoDir = self._toRepoDir(submodule)
        repoFiles = [toSubmodulePath(submodule, file) for file in files]
        error = Git.restoreStagedFiles(repoDir, repoFiles)
        if not error:
            qApp.postEvent(self, UpdateFilesEvent(True, submodule, files))
        else:
            qApp.postEvent(self, GitErrorEvent(error))

    def _doStage(self, submodule: str, files: List[str]):
        repoDir = self._toRepoDir(submodule)
        repoFiles = [toSubmodulePath(submodule, file) for file in files]
        error = Git.addFiles(repoDir, repoFiles)
        if not error:
            qApp.postEvent(self, UpdateFilesEvent(False, submodule, files))
        else:
            qApp.postEvent(self, GitErrorEvent(error))

    def _onNonUITaskFinished(self):
        self._blockUI(False)
        self.ui.spinnerUnstaged.stop()

    def _blockUI(self, blocked=True):
        self.ui.tbUnstage.setEnabled(not blocked)
        self.ui.tbUnstageAll.setEnabled(not blocked)
        self.ui.tbStage.setEnabled(not blocked)
        self.ui.tbStageAll.setEnabled(not blocked)
        self.ui.tbRefresh.setEnabled(not blocked)

    def event(self, evt):
        if evt.type() == UpdateFilesEvent.Type:
            self._updateFiles(evt.isStaged, evt.submodule, evt.files)
            return True

        if evt.type() == GitErrorEvent.Type:
            # TODO: merge the same error and report at end
            QMessageBox.critical(
                self,
                self.tr("Git Error"),
                evt.error,
                QMessageBox.Ok)
            return True

        if evt.type() == RepoInfoEvent.Type:
            self._repoInfo = evt.info
            self._commiterLabel.setText("{} <{}>".format(
                self._repoInfo.userName, self._repoInfo.userEmail))
            self._branchLabel.setText(self._repoInfo.branch)
            return True

        if evt.type() == TemplateReadyEvent.Type:
            doc = self.ui.teMessage.document()
            # only set template if user has not modified the message
            if not doc.isUndoAvailable() and not doc.isRedoAvailable():
                self.ui.teMessage.setPlainText(evt.template)
                doc.clearUndoRedoStacks()
            return True

        if evt.type() == UpdateCommitProgressEvent.Type:
            if evt.updateProgress:
                self.ui.progressBar.setValue(self.ui.progressBar.value() + 1)

            if evt.out or evt.error:
                if not evt.submodule or evt.submodule == ".":
                    repoName = "<main>"
                else:
                    repoName = evt.submodule
                repoText = self.tr("Repo: ") + repoName
                format = QTextCharFormat()
                format.setBackground(qApp.colorSchema().RepoTagBg)
                format.setForeground(qApp.colorSchema().RepoTagFg)

                cursor = self.ui.teOutput.textCursor()
                cursor.movePosition(QTextCursor.End)
                cursor.insertText(repoText, format)
                cursor.setCharFormat(QTextCharFormat())
                self.ui.teOutput.setTextCursor(cursor)

            if evt.out:
                self.ui.teOutput.appendPlainText(evt.out + "\n")
            if evt.error:
                cursor.movePosition(QTextCursor.End)

                format = QTextCharFormat()
                format.setForeground(qApp.colorSchema().ErrorText)
                error = "\n" + evt.error if not evt.out else evt.error
                error += "\n"
                cursor.insertText(error, format)
                cursor.setCharFormat(QTextCharFormat())
                self.ui.teOutput.setTextCursor(cursor)
            self.ui.teOutput.moveCursor(QTextCursor.End)
            self.ui.teOutput.ensureCursorVisible()
            return True

        return super().event(evt)

    def _updateFiles(self, isStaged: bool, submodule: str, files: List[str]):
        model = self._stagedModel if isStaged else self._filesModel
        status = self._removeFiles(model, submodule, files)

        model = self._filesModel if isStaged else self._stagedModel
        self._addFiles(model, submodule, files, status)

    def _removeFiles(self, model: StatusFileListModel, submodule: str, files: List[str]):
        status = {}
        for file in files:
            info = model.removeFile(file, submodule)
            status.setdefault(file, info.statusCode)
        return status

    def _addFiles(self, model: StatusFileListModel, submodule: str, files: List[str], oldStatus: Dict[str, str]):
        for file in files:
            status = oldStatus.get(file)
            if status in ["?", "!"] and model == self._stagedModel:
                status = "A"
            elif status == "A" and model == self._filesModel:
                # TODO: might be ignored files
                status = "?"
            model.tryAddFile(file, submodule, status)

    def reloadLocalChanges(self):
        self.clear()
        self._loadLocalChanges()

    def _setupWDMenu(self):
        self._wdMenu = QMenu(self)
        self._acShowUntrackedFiles = self._wdMenu.addAction(
            self.tr("Show untracked files"),
            self._onShowUntrackedFiles)
        self._acShowUntrackedFiles.setCheckable(True)

        settings = qApp.settings()
        checked = settings.showUntrackedFiles()
        self._acShowUntrackedFiles.setChecked(checked)
        self._statusFetcher.setShowUntrackedFiles(checked)

        self._acShowIgnoredFiles = self._wdMenu.addAction(
            self.tr("Show ignored files"),
            self._onShowIgnoredFiles)
        self._acShowIgnoredFiles.setCheckable(True)

        checked = settings.showIgnoredFiles()
        self._acShowIgnoredFiles.setChecked(checked)
        self._statusFetcher.setShowIgnoredFiles(checked)

        self.ui.tbWDChanges.setMenu(self._wdMenu)

    def _onShowUntrackedFiles(self):
        checked = self._acShowUntrackedFiles.isChecked()
        self._statusFetcher.setShowUntrackedFiles(checked)
        qApp.settings().setShowUntrackedFiles(checked)
        self.reloadLocalChanges()

    def _onShowIgnoredFiles(self):
        checked = self._acShowIgnoredFiles.isChecked()
        self._statusFetcher.setShowIgnoredFiles(checked)
        qApp.settings().setShowIgnoredFiles(checked)
        self.reloadLocalChanges()

    def _onInfoFetchFinished(self):
        sender = self.sender()
        del sender

    def _fetchRepoInfo(self, submodule: str, userData: any):
        templateFile = Git.getConfigValue("commit.template", False)
        if templateFile and os.path.exists(templateFile):
            with open(templateFile, "r", encoding="utf-8") as f:
                template = f.read().rstrip()
            if template:
                qApp.postEvent(self, TemplateReadyEvent(template))

        info = RepoInfo()
        info.userName = Git.userName()
        info.userEmail = Git.userEmail()
        info.branch = Git.activeBranch()

        qApp.postEvent(self, RepoInfoEvent(info))

    def _setupStatusBar(self):
        widget = QWidget(self)
        hbox = QHBoxLayout(widget)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(3)
        hbox.addWidget(QLabel(self.tr("Committer:")))
        self._commiterLabel = QLabel(widget)
        hbox.addWidget(self._commiterLabel)
        self.ui.statusbar.addPermanentWidget(widget)

        widget = QWidget(self)
        hbox = QHBoxLayout(widget)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(3)
        hbox.addWidget(QLabel(self.tr("Branch:")))
        self._branchLabel = QLabel(widget)
        hbox.addWidget(self._branchLabel)
        self.ui.statusbar.addPermanentWidget(widget)

        self._branchWidget = QWidget(self)
        hbox = QHBoxLayout(self._branchWidget)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(3)
        warningIcon = ColoredIconLabel(self)
        warningIcon.setIcon(
            QIcon(dataDirPath() + "/icons/warning.svg"), "ErrorText")
        hbox.addWidget(warningIcon)

        self._branchMessage = ColoredLabel("ErrorText", self)
        hbox.addWidget(self._branchMessage)

        self.ui.statusbar.addWidget(self._branchWidget)
        self._branchWidget.setVisible(False)

    def isMaximizedByDefault(self):
        return False

    def restoreState(self):
        if not super().restoreState():
            return False

        sett = qApp.instance().settings()
        state = sett.getSplitterState("cw.splitterMain")
        if state:
            self.ui.splitterMain.restoreState(state)

        state = sett.getSplitterState("cw.splitterLeft")
        if state:
            self.ui.splitterLeft.restoreState(state)

        state = sett.getSplitterState("cw.splitterRight")
        if state:
            self.ui.splitterRight.restoreState(state)

        return True

    def saveState(self):
        if not super().saveState():
            return False

        sett = qApp.instance().settings()

        sett.saveSplitterState(
            "cw.splitterLeft", self.ui.splitterLeft.saveState())
        sett.saveSplitterState(
            "cw.splitterRight", self.ui.splitterRight.saveState())
        sett.saveSplitterState(
            "cw.splitterMain", self.ui.splitterMain.saveState())

        return True

    def _onOptionsClicked(self):
        preferences = Preferences(qApp.settings(), self)
        preferences.ui.tabWidget.setCurrentWidget(
            preferences.ui.tabCommitMessage)
        if preferences.exec() == QDialog.Accepted:
            preferences.save()

    def _onCommitFinished(self):
        # we're not really done yet
        if self._committedActions:
            submodules = {None: self._committedActions}
            self._committedActions = []
            self._commitExecutor.submit(submodules, self._runCommittedAction)
            return

        self.reloadLocalChanges()
        self._updateCommitStatus(False)
        qApp.postEvent(qApp, LocalChangesCommittedEvent())

    def _updateCommitProgress(self, submodule, out: str, error: str, updateProgress=True):
        qApp.postEvent(self, UpdateCommitProgressEvent(
            submodule, out, error, updateProgress))

    def _updateCommitStatus(self, isRunning: bool):
        text = self.tr("&Abort") if isRunning else self.tr("&Back")
        self.ui.btnAction.setText(text)

        text = self.tr("Working on commit...") if isRunning else self.tr(
            "Commit finished")
        self.ui.lbStatus.setText(text)

    def _onCommitActionClicked(self):
        if self._commitExecutor.isRunning():
            self._commitExecutor.cancel()
            self._committedActions.clear()
        else:
            self.ui.stackedWidget.setCurrentWidget(self.ui.pageMessage)

    @staticmethod
    def _runCommitAction(submodule: str, action: CommitAction):
        if action.condition == ActionCondition.MainRepoOnly:
            # not main repo, ignore it
            if not (not submodule or submodule == "."):
                return None, None

        repoDir = CommitWindow._toRepoDir(submodule)

        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        def _quote(path):
            if " " in path:
                return '"' + path + '"'
            return path

        args = _quote(action.command)
        if action.args:
            args += " " + action.args

        try:
            process = subprocess.Popen(
                args,
                cwd=repoDir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                shell=True)

            out, error = process.communicate()
            if out is not None:
                out, _ = decodeFileData(out)
            if error is not None:
                error, _ = decodeFileData(error)
        except Exception as e:
            out = None
            error = str(e)

        return out, error

    def _runCommittedAction(self, submodule: str, actions: List[CommitAction]):
        for action in actions:
            out, error = CommitWindow._runCommitAction(submodule, action)
            self._updateCommitProgress(submodule, out, error)

    def _onFilterFilesChanged(self, text: str):
        model: QSortFilterProxyModel = self.ui.lvFiles.model()
        model.setFilterRegularExpression(text)

    def _onFilterStagedChanged(self, text: str):
        model: QSortFilterProxyModel = self.ui.lvStaged.model()
        model.setFilterRegularExpression(text)

    def _onFilesDoubleClicked(self, index: QModelIndex):
        statusCode = index.data(StatusFileListModel.StatusCodeRole)
        if statusCode in ["?", "!"]:
            fileStatus = FileStatus.Untracked
        else:
            fileStatus = FileStatus.Unstaged
        self._runDiffTool(index, fileStatus)

    def _onStagedDoubleClicked(self, index: QModelIndex):
        self._runDiffTool(index, FileStatus.Staged)

    def _runDiffTool(self, index: QModelIndex, fileStatus: FileStatus):
        if not index.isValid():
            return

        submodule = index.data(StatusFileListModel.RepoDirRole)
        file = toSubmodulePath(submodule, index.data(Qt.DisplayRole))

        tool = DiffView.diffToolForFile(file)

        args = ["difftool", "--no-prompt"]
        if fileStatus == FileStatus.Unstaged:
            pass
        elif fileStatus == FileStatus.Staged:
            args.append("--cached")
        else:
            args.append("--no-index")
            args.append("/dev/null")

        if tool:
            args.append("--tool={}".format(tool))

        args.append("--")
        args.append(file)

        repoDir = CommitWindow._toRepoDir(submodule)
        try:
            process = Git.run(args, repoDir=repoDir)
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Run External Diff Tool Error"),
                str(e),
                QMessageBox.Ok)

    def _onGenMessageClicked(self):
        submodules = self._collectStagedRepos()
        assert (submodules)
        self.ui.btnGenMessage.hide()
        self.ui.btnCancelGen.show()
        self._aiMessage.generate(list(submodules))

    def _collectStagedRepos(self):
        model = self.ui.lvStaged.model()
        submodules = set()
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            repoDir = model.data(
                index, StatusFileListModel.RepoDirRole)
            submodules.add(repoDir)

        return submodules

    def _onAiMessageAvailable(self, message: str):
        self.ui.btnCancelGen.hide()
        self.ui.btnGenMessage.show()
        if not message:
            return

        self.ui.teMessage.setPlainText(message)
        self.ui.teMessage.moveCursor(QTextCursor.End)

    def _onCancelGenMessageClicked(self):
        self._aiMessage.cancel()
        self.ui.btnCancelGen.hide()
        self.ui.btnGenMessage.show()

    def _onShowCommitClicked(self):
        qApp.postEvent(qApp, ShowCommitEvent(None))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            sett = qApp.instance().settings()
            if sett.quitViaEsc():
                self.close()
                return

        super().keyPressEvent(event)

    def _onCodeReviewClicked(self):
        submodules = self._collectStagedRepos()
        assert (submodules)

        event = CodeReviewEvent(list(submodules))
        qApp.postEvent(qApp, event)
