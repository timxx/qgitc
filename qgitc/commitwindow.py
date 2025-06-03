# -*- coding: utf-8 -*-

import os
from enum import Enum
from typing import Callable, Dict, List, Tuple

from PySide6.QtCore import (
    SIGNAL,
    QAbstractListModel,
    QDateTime,
    QElapsedTimer,
    QEvent,
    QEventLoop,
    QFileInfo,
    QModelIndex,
    QObject,
    QProcess,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QDesktopServices,
    QFont,
    QIcon,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QMessageBox,
    QStyle,
    QWidget,
)

from qgitc.actionrunner import ActionRunner
from qgitc.aicommitmessage import AiCommitMessage
from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.colorediconlabel import ColoredIconLabel
from qgitc.coloredlabel import ColoredLabel
from qgitc.commitactiontablemodel import ActionCondition, CommitAction
from qgitc.common import dataDirPath, fullRepoDir, logger, toSubmodulePath
from qgitc.difffetcher import DiffFetcher
from qgitc.diffview import DiffView, _makeTextIcon
from qgitc.events import CodeReviewEvent, LocalChangesCommittedEvent, ShowCommitEvent
from qgitc.findsubmodules import FindSubmoduleThread
from qgitc.gitutils import Git
from qgitc.ntpdatetime import getNtpDateTime
from qgitc.preferences import Preferences
from qgitc.settings import Settings
from qgitc.statewindow import StateWindow
from qgitc.statusfetcher import StatusFetcher
from qgitc.submoduleexecutor import SubmoduleExecutor
from qgitc.ui_commitwindow import Ui_CommitWindow


class FileStatus(Enum):

    Untracked = 0
    Unstaged = 1
    Staged = 2


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
        self.repoUrl: str = None


class RepoInfoEvent(QEvent):
    Type = QEvent.User + 3

    def __init__(self, info: RepoInfo):
        super().__init__(QEvent.Type(RepoInfoEvent.Type))
        self.info = info


class TemplateReadyEvent(QEvent):
    Type = QEvent.User + 4

    def __init__(self, template: str, updateMessage: bool = False):
        super().__init__(QEvent.Type(TemplateReadyEvent.Type))
        self.template = template
        self.updateMessage = updateMessage


class UpdateCommitProgressEvent(QEvent):
    Type = QEvent.User + 5

    def __init__(self, submodule: str, out: str, error: str, updateProgress: bool = True, action: str = None):
        super().__init__(QEvent.Type(UpdateCommitProgressEvent.Type))
        self.submodule = submodule
        self.out = out
        self.error = error
        self.updateProgress = updateProgress
        self.action = action


class FileRestoreEvent(QEvent):
    Type = QEvent.User + 6

    def __init__(self, submodule: str, files: List[str], error: str = None):
        super().__init__(QEvent.Type(FileRestoreEvent.Type))
        self.submodule = submodule
        self.files = files
        self.error = error


class NtpDateTimeReadyEvent(QEvent):
    Type = QEvent.User + 7

    def __init__(self, ntpDateTime: QDateTime, localDateTime: QDateTime):
        super().__init__(QEvent.Type(NtpDateTimeReadyEvent.Type))
        self.ntpDateTime = ntpDateTime
        self.localDateTime = localDateTime


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
        self.ui.lvFiles.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.lvFiles.customContextMenuRequested.connect(
            self._onFilesContextMenuRequested)

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
        self.ui.lvStaged.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.lvStaged.customContextMenuRequested.connect(
            self._onStagedContextMenuRequested)

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

        self._findSubmoduleThread = None
        self._threads: List[QThread] = []

        self._curFile: str = None
        self._curFileStatus: FileStatus = None

        self._setupSpinner(self.ui.spinnerUnstaged)
        self._setupSpinner(self.ui.spinnerDiff)

        self._diffSpinnerDelayTimer = QTimer(self)
        self._diffSpinnerDelayTimer.setSingleShot(True)
        self._diffSpinnerDelayTimer.timeout.connect(self.ui.spinnerDiff.start)

        self.ui.teMessage.setPlaceholderText(
            self.tr("Enter commit message here..."))
        self.ui.teMessage.textChanged.connect(
            self._onMessageChanged)

        self.ui.btnCommit.clicked.connect(self._onCommitClicked)

        # no UI tasks
        self._submoduleExecutor = SubmoduleExecutor(self)
        self._submoduleExecutor.finished.connect(
            self._onNonUITaskFinished)

        self._committedActions = []
        self._commitExecutor = SubmoduleExecutor(self)
        self._commitExecutor.finished.connect(
            self._onCommitFinished)

        self._infoFetcher = SubmoduleExecutor(self)
        self._repoInfo: RepoInfo = None

        self._setupWDMenu()
        self._setupStatusBar()

        self.ui.tbOptions.setIcon(QIcon(iconsPath + "settings.svg"))
        self.ui.tbOptions.clicked.connect(self._onOptionsClicked)

        self.ui.btnAction.clicked.connect(
            self._onCommitActionClicked)

        self.ui.cbRunAction.setChecked(
            ApplicationBase.instance().settings().runCommitActions())
        self.ui.cbRunAction.toggled.connect(
            lambda checked: ApplicationBase.instance().settings().setRunCommitActions(checked))

        self.ui.leFilterFiles.textChanged.connect(
            self._onFilterFilesChanged)
        self.ui.leFilterStaged.textChanged.connect(
            self._onFilterStagedChanged)

        self.ui.cbAmend.toggled.connect(
            self._onAmendToggled)

        if not ApplicationBase.instance().style().styleHint(QStyle.SH_ItemView_ActivateItemOnSingleClick):
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

        icon = QIcon(iconsPath + "/wand-shine.svg")
        self.ui.btnRefineMsg.setIcon(icon)
        self.ui.btnRefineMsg.setIconSize(QSize(16, 16))
        self.ui.btnRefineMsg.clicked.connect(
            self._onRefineMessageClicked)
        self.ui.btnRefineMsg.setEnabled(False)

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

        self._setupContextMenu()

        self._outputBlocks: Dict[str, int] = {}

        self._ntpTimer = None
        self._ntpDateTime = None
        self._ntpElapsed = None

        ApplicationBase.instance().repoDirChanged.connect(
            self._onRepoDirChanged)
        ApplicationBase.instance().settings().useNtpTimeChanged.connect(
            self._onUseNtpTimeChanged)

        if Git.REPO_DIR:
            self._onRepoDirChanged()

    def _setupSpinner(self, spinner):
        height = self.ui.tbRefresh.height() // 7
        spinner.setLineLength(height)
        spinner.setInnerRadius(height)
        spinner.setNumberOfLines(14)

    def _loadLocalChanges(self):
        submodules = ApplicationBase.instance().settings().submodulesCache(Git.REPO_DIR)
        self._statusFetcher.fetch(submodules)
        self.ui.tbRefresh.setEnabled(False)
        self.ui.tbWDChanges.setEnabled(False)
        self.ui.spinnerUnstaged.start()
        logger.debug("Begin fetch status")

    def clear(self):
        self.clearModels()
        self._repoBranch.clear()
        self._branchMessage.clear()
        self._branchWidget.setVisible(False)
        self._outputBlocks.clear()

    def clearModels(self):
        self._filesModel.clear()
        self._stagedModel.clear()
        self._curFile = None
        self._curFileStatus = None

    def _onFindSubmoduleFinished(self):
        thread: FindSubmoduleThread = self.sender()
        if thread == self._findSubmoduleThread:
            self._findSubmoduleThread = None

        submodules = thread.submodules
        caches = ApplicationBase.instance().settings().submodulesCache(Git.REPO_DIR)

        newSubmodules = list(set(submodules) - set(caches))
        # no new submodules, no need to fetch
        if not newSubmodules:
            return

        ApplicationBase.instance().settings().setSubmodulesCache(Git.REPO_DIR, submodules)

        if not caches and "." in newSubmodules:
            # do not reload for main repo
            newSubmodules.remove(".")

        if not newSubmodules:
            return

        if self._statusFetcher.isRunning():
            self._statusFetcher.addTask(newSubmodules)
        else:
            self._statusFetcher.fetch(newSubmodules)

    def _onStatusAvailable(self, repoDir: str, fileList: List[Tuple[str, str, str]]):
        logger.debug("Status available %s -> %s", repoDir, fileList)
        for status, file, oldFile in fileList:
            if status[0] != " " and status[0] not in ["?", "!"]:
                self._stagedModel.addFile(file, repoDir, status[0], oldFile)
            if status[1] != " ":
                self._filesModel.addFile(file, repoDir, status[1])

    def _onBranchInfoAvailable(self, repoDir: str, branch: str):
        self._repoBranch.setdefault(repoDir, branch)

    def _onStatusFetchFinished(self):
        logger.debug("End fetch status")

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

        file = self._stagedModel.data(current, Qt.DisplayRole)
        repoDir = self._stagedModel.data(
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

    def _collectCommitActions(self, commitActions: List[CommitAction], filterActions: List[CommitAction], committedActions: List[CommitAction]):
        for action in commitActions:
            if not action.enabled:
                continue
            if not action.command:
                continue
            if action.condition == ActionCondition.AllCommitted:
                committedActions.append(action)
            else:
                filterActions.append(action)

    def _repoName(self):
        if not self._repoInfo or not self._repoInfo.repoUrl:
            return ApplicationBase.instance().repoName()

        repoUrl = self._repoInfo.repoUrl
        index = repoUrl.rfind('/')
        if index == -1:
            return repoUrl
        return repoUrl[index+1:]

    def _onCommitClicked(self):
        doc = self.ui.teMessage.document()
        if not doc.isEmpty() and not doc.isUndoAvailable():
            r = QMessageBox.question(
                self,
                self.tr("Confirm commit"),
                self.tr(
                    "You did not edit the message template. Do you want to use the template as commit message?"),
                QMessageBox.Yes | QMessageBox.No)
            if r == QMessageBox.No:
                self.ui.teMessage.setFocus()
                return

        if not self._checkMessage():
            return

        amend = self.ui.cbAmend.isChecked()
        message = self._filterMessage(
            self.ui.teMessage.toPlainText().strip())

        settings: Settings = ApplicationBase.instance().settings()

        if self.ui.cbRunAction.isChecked():
            actions = []
            self._committedActions = []

            self._collectCommitActions(
                settings.commitActions(self._repoName()),
                actions,
                self._committedActions)

            if settings.useGlobalCommitActions():
                self._collectCommitActions(
                    settings.globalCommitActions(),
                    actions,
                    self._committedActions)
        else:
            actions = []
            self._committedActions = []

        date = None
        if settings.useNtpTime():
            if not self._ntpDateTime:
                logger.warning("NTP time is not available, using local time")
            else:
                ntpDateTime = self._ntpDateTime.addMSecs(self._ntpElapsed.elapsed())
                date = ntpDateTime.toString(Qt.ISODate)

        submodules = {}
        for row in range(self._stagedModel.rowCount()):
            index = self._stagedModel.index(row, 0)
            repoDir = self._stagedModel.data(
                index, StatusFileListModel.RepoDirRole)
            submodules.setdefault(repoDir, (message, amend, actions, date))

        # amend to main repo
        if not submodules:
            assert (amend)
            submodules[None] = (message, amend, actions, date)

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
        ignoreCommentLine = ApplicationBase.instance().settings().ignoreCommentLine()
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

        # do not enable generate button if it is running
        if not self.ui.btnCancelGen.isVisible():
            self.ui.btnGenMessage.setEnabled(hasStagedFiles)

        self.ui.btnCodeReview.setEnabled(hasStagedFiles)

    def _doCommit(self, submodule: str, userData: Tuple[str, bool, list, str], cancelEvent: CancelEvent):
        amend = userData[1]
        message = userData[0]

        actions: List[CommitAction] = userData[2]
        date = userData[3]

        repoDir = fullRepoDir(submodule)
        out, error = Git.commit(message, amend, repoDir, date=date)
        if cancelEvent.isSet():
            return

        self._updateCommitProgress(submodule, out, error, not actions)
        if not actions:
            return

        out, error = None, None
        for action in actions:
            if cancelEvent.isSet():
                return
            self._runCommitAction(submodule, action, cancelEvent)

    def _collectSectionFiles(self, view: QListView, filter: Callable = None):
        indexes = view.selectionModel().selectedRows()
        if not indexes:
            return {}

        model = view.model()
        submoduleFiles = {}
        for index in indexes:
            if filter and filter(model, index):
                continue
            file = model.data(index, Qt.DisplayRole)
            repoDir = model.data(
                index, StatusFileListModel.RepoDirRole)
            submoduleFiles.setdefault(repoDir, []).append(file)

        return submoduleFiles

    @staticmethod
    def _isFileIgnored(file: str, extsToExclude: List[str] = []):
        if not extsToExclude:
            return False

        lowerFile = file.lower()
        for ext in extsToExclude:
            if lowerFile.endswith(ext.lower()):
                return True

        return False

    def _collectModelFiles(self, model: QAbstractListModel, extsToExclude=[]):
        submoduleFiles = {}
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            file = model.data(index, Qt.DisplayRole)
            if CommitWindow._isFileIgnored(file, extsToExclude):
                continue
            repoDir = model.data(
                index, StatusFileListModel.RepoDirRole)
            submoduleFiles.setdefault(repoDir, []).append(file)

        return submoduleFiles

    def _updateSubmoduleFiles(self, submoduleFiles: Dict[str, List[str]], model: QAbstractListModel):
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            repoDir = model.data(
                index, StatusFileListModel.RepoDirRole)
            if repoDir not in submoduleFiles:
                submoduleFiles[repoDir] = []

    def _onUnstageClicked(self):
        submoduleFiles = self._collectSectionFiles(self.ui.lvStaged)
        if not submoduleFiles:
            return

        self._updateSubmoduleFiles(submoduleFiles, self.ui.lvFiles.model())
        self._updateSubmoduleFiles(submoduleFiles, self.ui.lvStaged.model())

        self._blockUI()
        self.ui.spinnerUnstaged.start()
        self._submoduleExecutor.submit(submoduleFiles, self._doUnstage)
        self.clearModels()

    def _onUnstageAllClicked(self):
        submoduleFiles = self._collectModelFiles(self.ui.lvStaged.model())
        if not submoduleFiles:
            return

        self._updateSubmoduleFiles(submoduleFiles, self.ui.lvFiles.model())

        self._blockUI()
        self.ui.spinnerUnstaged.start()
        self._submoduleExecutor.submit(submoduleFiles, self._doUnstage)
        self.clearModels()

    def _onStageClicked(self):
        submoduleFiles = self._collectSectionFiles(self.ui.lvFiles)
        if not submoduleFiles:
            return

        self._updateSubmoduleFiles(submoduleFiles, self.ui.lvFiles.model())
        self._updateSubmoduleFiles(submoduleFiles, self.ui.lvStaged.model())

        self._blockUI()
        self.ui.spinnerUnstaged.start()
        self._submoduleExecutor.submit(submoduleFiles, self._doStage)
        self.clearModels()

    def _onStageAllClicked(self):
        submoduleFiles = self._collectModelFiles(self.ui.lvFiles.model())
        if not submoduleFiles:
            return

        self._updateSubmoduleFiles(submoduleFiles, self.ui.lvStaged.model())

        self._blockUI()
        self.ui.spinnerUnstaged.start()
        self._submoduleExecutor.submit(submoduleFiles, self._doStage)
        self.clearModels()

    def _doUnstage(self, submodule: str, files: List[str], cancelEvent: CancelEvent):
        repoDir = fullRepoDir(submodule)
        if files:
            repoFiles = [toSubmodulePath(submodule, file) for file in files]
            error = Git.restoreStagedFiles(repoDir, repoFiles)
            if error:
                ApplicationBase.instance().postEvent(self, GitErrorEvent(error))
        self._statusFetcher.fetchStatus(submodule, cancelEvent)

    def _doStage(self, submodule: str, files: List[str], cancelEvent: CancelEvent):
        repoDir = fullRepoDir(submodule)
        if files:
            repoFiles = [toSubmodulePath(submodule, file) for file in files]
            error = Git.addFiles(repoDir, repoFiles)
            if error:
                ApplicationBase.instance().postEvent(self, GitErrorEvent(error))
        self._statusFetcher.fetchStatus(submodule, cancelEvent)

    def _onNonUITaskFinished(self):
        self._blockUI(False)
        self.ui.spinnerUnstaged.stop()

    def _blockUI(self, blocked=True):
        self.ui.tbUnstage.setEnabled(not blocked)
        self.ui.tbUnstageAll.setEnabled(not blocked)
        self.ui.tbStage.setEnabled(not blocked)
        self.ui.tbStageAll.setEnabled(not blocked)
        self.ui.tbRefresh.setEnabled(not blocked)
        self.ui.cbAmend.setEnabled(not blocked)

    def event(self, evt: QEvent):
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
            if evt.updateMessage:
                if self._canUpdateMessage():
                    self._replaceMessage(evt.template)
            elif not doc.isUndoAvailable() and not doc.isRedoAvailable():
                # only set template if user has not modified the message
                self.ui.teMessage.setPlainText(evt.template)

            return True

        if evt.type() == UpdateCommitProgressEvent.Type:
            self._handleUpdateCommitProgress(
                evt.submodule, evt.out, evt.error, evt.updateProgress, evt.action)
            return True

        if evt.type() == FileRestoreEvent.Type:
            self._handleFileRestoreEvent(evt.submodule, evt.files, evt.error)
            return True

        if evt.type() == NtpDateTimeReadyEvent.Type:
            self._handleNtpDateTimeReadyEvent(
                evt.ntpDateTime, evt.localDateTime)
            return True

        return super().event(evt)

    def _addBlock(self, key: str, title: str):
        cursor = self.ui.teOutput.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()

        blockFmt = QTextBlockFormat()
        blockFmt.topMargin = 8

        charFmt = QTextCharFormat()
        charFmt.setBackground(
            ApplicationBase.instance().colorSchema().RepoTagBg)
        charFmt.setForeground(
            ApplicationBase.instance().colorSchema().RepoTagFg)

        cursor.setBlockFormat(blockFmt)
        cursor.insertText(f"{title}\n", charFmt)
        self._outputBlocks[key] = cursor.position()
        cursor.setCharFormat(QTextCharFormat())
        self.ui.teOutput.setTextCursor(cursor)

    def _updateBlockOutput(self, repoName: str, content: str, isError: bool = False, action: str = None):
        cursor = self.ui.teOutput.textCursor()
        blockKey = f"{repoName}.{action}" if action else repoName
        pos = self._outputBlocks.get(blockKey)
        if pos is None:
            if action:
                title = self.tr("Action: ") + action + f" ({repoName})"
            else:
                title = self.tr("Repo: ") + repoName

            self._addBlock(blockKey, title)
            pos = self._outputBlocks[blockKey]

        if not content:
            return

        cursor.setPosition(pos)
        cursor.movePosition(QTextCursor.EndOfBlock)
        format = QTextCharFormat()
        if isError:
            format.setForeground(
                ApplicationBase.instance().colorSchema().ErrorText)
        cursor.insertText(content if content.endswith("\n")
                          else (content + "\n"), format)
        cursor.setCharFormat(QTextCharFormat())
        self._outputBlocks[blockKey] = cursor.position()
        self.ui.teOutput.setTextCursor(cursor)
        self.ui.teOutput.ensureCursorVisible()

    def _handleUpdateCommitProgress(self, submodule: str, out: str, error: str, updateProgress: bool = True, action: str = None):
        if updateProgress:
            self.ui.progressBar.setValue(self.ui.progressBar.value() + 1)

        if not submodule or submodule == ".":
            repoName = "<main>"
        else:
            repoName = submodule

        if out:
            self._updateBlockOutput(repoName, out, False, action)
        if error:
            self._updateBlockOutput(repoName, error, True, action)

        if not out and not error:
            # add title only
            self._updateBlockOutput(repoName, "", False, action)

    def reloadLocalChanges(self):
        self._statusFetcher.cancel()
        self.clear()
        self._loadLocalChanges()

    def _setupWDMenu(self):
        self._wdMenu = QMenu(self)
        self._acShowUntrackedFiles = self._wdMenu.addAction(
            self.tr("Show untracked files"),
            self._onShowUntrackedFiles)
        self._acShowUntrackedFiles.setCheckable(True)

        settings = ApplicationBase.instance().settings()
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
        ApplicationBase.instance().settings().setShowUntrackedFiles(checked)
        self.reloadLocalChanges()

    def _onShowIgnoredFiles(self):
        checked = self._acShowIgnoredFiles.isChecked()
        self._statusFetcher.setShowIgnoredFiles(checked)
        ApplicationBase.instance().settings().setShowIgnoredFiles(checked)
        self.reloadLocalChanges()

    def _fetchRepoInfo(self, submodule: str, userData: any, cancelEvent: CancelEvent):
        templateFile = Git.getConfigValue("commit.template", False)
        if cancelEvent.isSet():
            return

        if templateFile and os.path.exists(templateFile):
            with open(templateFile, "r", encoding="utf-8") as f:
                template = f.read().rstrip()
            if cancelEvent.isSet():
                return
            if template:
                ApplicationBase.instance().postEvent(self, TemplateReadyEvent(template))

        if cancelEvent.isSet():
            return

        info = RepoInfo()
        info.userName = Git.userName()
        if cancelEvent.isSet():
            return

        info.userEmail = Git.userEmail()
        if cancelEvent.isSet():
            return

        info.branch = Git.activeBranch()
        if cancelEvent.isSet():
            return

        info.repoUrl = Git.repoUrl()
        if cancelEvent.isSet():
            return

        ApplicationBase.instance().postEvent(self, RepoInfoEvent(info))

        dt = getNtpDateTime()
        localDt = QDateTime.currentDateTime()
        if cancelEvent.isSet():
            return

        if dt is not None:
            ApplicationBase.instance().postEvent(
                self, NtpDateTimeReadyEvent(dt, localDt))

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

        self._ntpDateTimeLabel = ColoredLabel("ErrorText", self)
        self.ui.statusbar.addWidget(self._ntpDateTimeLabel)
        self._ntpDateTimeLabel.setVisible(False)

    def isMaximizedByDefault(self):
        return False

    def restoreState(self):
        if not super().restoreState():
            return False

        sett = ApplicationBase.instance().settings()
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

        sett = ApplicationBase.instance().settings()

        sett.saveSplitterState(
            "cw.splitterLeft", self.ui.splitterLeft.saveState())
        sett.saveSplitterState(
            "cw.splitterRight", self.ui.splitterRight.saveState())
        sett.saveSplitterState(
            "cw.splitterMain", self.ui.splitterMain.saveState())

        return True

    def _onOptionsClicked(self):
        preferences = Preferences(ApplicationBase.instance().settings(), self)
        preferences.ui.tabWidget.setCurrentWidget(
            preferences.ui.tabCommitMessage)
        preferences.exec()

    def _onCommitFinished(self):
        # we're not really done yet
        if self._committedActions:
            submodules = {None: self._committedActions}
            self._committedActions = []
            self._commitExecutor.submit(submodules, self._runCommittedAction)
            return

        self._outputBlocks.clear()
        self.reloadLocalChanges()
        self._updateCommitStatus(False)
        ApplicationBase.instance().postEvent(
            ApplicationBase.instance(), LocalChangesCommittedEvent())

    def _updateCommitProgress(self, submodule, out: str, error: str, updateProgress=True, action: str = None):
        ApplicationBase.instance().postEvent(self, UpdateCommitProgressEvent(
            submodule, out, error, updateProgress, action))

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
            self._updateCommitStatus(False)
            self.ui.lbStatus.setText(self.tr("Commit aborted"))
        else:
            self.ui.stackedWidget.setCurrentWidget(self.ui.pageMessage)

    def _runCommitAction(self, submodule: str, action: CommitAction, cancelEvent: CancelEvent):
        if action.condition == ActionCondition.MainRepoOnly:
            # not main repo, ignore it
            if not (not submodule or submodule == "."):
                return

        repoDir = fullRepoDir(submodule)

        def _quote(path):
            if " " in path:
                return '"' + path + '"'
            return path

        args = _quote(action.command)
        if action.args:
            args += " " + action.args

        # Update status as soon as we start the action
        self._updateCommitProgress(submodule, None, None, False, args)

        eventLoop = QEventLoop()
        runner = ActionRunner()

        def _update(data: bytes, isError: bool):
            if cancelEvent.isSet():
                runner.cancel()
                return

            if isError:
                self._updateCommitProgress(
                    submodule, None, data.decode("utf-8"), False, args)
            else:
                self._updateCommitProgress(
                    submodule, data.decode("utf-8"), None, False, args)

        runner.stdoutAvailable.connect(lambda data: _update(data, False))
        runner.stderrAvailable.connect(lambda data: _update(data, True))
        runner.finished.connect(eventLoop.quit)
        runner.run(args, repoDir)
        eventLoop.exec()

        self._updateCommitProgress(submodule, None, None, True, args)

    def _runCommittedAction(self, submodule: str, actions: List[CommitAction], cancelEvent: CancelEvent):
        for action in actions:
            if cancelEvent and cancelEvent.isSet():
                return
            self._runCommitAction(submodule, action, cancelEvent)

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

        repoDir = fullRepoDir(submodule)
        try:
            process = Git.run(args, repoDir=repoDir)
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Run External Diff Tool Error"),
                str(e),
                QMessageBox.Ok)

    def _onGenMessageClicked(self):
        exts = ApplicationBase.instance().settings().aiExcludedFileExtensions()
        submoduleFiles = self._collectModelFiles(self._stagedModel, exts)
        if not submoduleFiles:
            return

        self.ui.btnGenMessage.hide()
        self.ui.btnCancelGen.show()
        self.ui.btnRefineMsg.setEnabled(False)
        self._aiMessage.generate(submoduleFiles)
        logger.debug("Begin generate commit message")

    def _onRefineMessageClicked(self):
        self.ui.btnRefineMsg.hide()
        self.ui.btnCancelGen.show()
        self.ui.btnGenMessage.setEnabled(False)

        self._aiMessage.refine(self.ui.teMessage.toPlainText().strip())
        logger.debug("Begin refine commit message")

    def _collectStagedRepos(self):
        model = self.ui.lvStaged.model()
        submodules = set()
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            repoDir = model.data(
                index, StatusFileListModel.RepoDirRole)
            submodules.add(repoDir)

        return submodules

    def _restoreAiMessageButtons(self):
        self.ui.btnCancelGen.hide()
        if self.ui.btnGenMessage.isHidden():
            self.ui.btnGenMessage.show()
            doc = self.ui.teMessage.document()
            isEmpty = doc.isEmpty() or not doc.toPlainText().strip()
            self.ui.btnRefineMsg.setEnabled(not isEmpty)
        else:
            self.ui.btnGenMessage.setEnabled(self._stagedModel.rowCount() > 0)
            self.ui.btnRefineMsg.show()

    def _onAiMessageAvailable(self, message: str):
        self._restoreAiMessageButtons()
        logger.debug("AI message: %s", message)
        if not message:
            return

        oldMessage = self.ui.teMessage.toPlainText().strip()
        if oldMessage == message:
            return

        self._replaceMessage(message)

    def _replaceMessage(self, message: str):
        cursor = self.ui.teMessage.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(message)
        cursor.endEditBlock()
        self.ui.teMessage.moveCursor(QTextCursor.End)

    def _onCancelGenMessageClicked(self):
        self._aiMessage.cancel()
        self._restoreAiMessageButtons()

    def _onShowCommitClicked(self):
        ApplicationBase.instance().postEvent(
            ApplicationBase.instance(), ShowCommitEvent(None))

    def _onCodeReviewClicked(self):
        exts = ApplicationBase.instance().settings().aiExcludedFileExtensions()
        submoduleFiles = self._collectModelFiles(self._stagedModel, exts)
        if not submoduleFiles:
            return

        event = CodeReviewEvent(submoduleFiles)
        ApplicationBase.instance().postEvent(ApplicationBase.instance(), event)

    def cancel(self, force=False):
        self._aiMessage.cancel(force)
        self._submoduleExecutor.cancel(force)
        self._commitExecutor.cancel(force)
        self._statusFetcher.cancel(force)
        self._infoFetcher.cancel(force)
        if self._findSubmoduleThread:
            QObject.disconnect(self._findSubmoduleThread,
                               SIGNAL("finished"),
                               self._onFindSubmoduleFinished)
            self._findSubmoduleThread.requestInterruption()
            if force and ApplicationBase.instance().terminateThread(self._findSubmoduleThread):
                self._threads.remove(self._findSubmoduleThread)
                self._findSubmoduleThread.finished.disconnect(
                    self._onThreadFinished)
                logger.warning("Terminate find submodule thread")
            self._findSubmoduleThread = None

        if force:
            for thread in self._threads:
                thread.finished.disconnect(self._onThreadFinished)
                ApplicationBase.instance().terminateThread(thread)
            self._threads.clear()

    def closeEvent(self, event):
        logger.debug("Before cancel")
        self.cancel(True)
        logger.debug("After cancel")
        return super().closeEvent(event)

    def _onFilesContextMenuRequested(self, pos):
        self._showStatusContextMenu(pos, self.ui.lvFiles)

    def _onStagedContextMenuRequested(self, pos):
        self._showStatusContextMenu(pos, self.ui.lvStaged)

    def _showStatusContextMenu(self, pos, listView: QListView):
        if self._submoduleExecutor.isRunning():
            return

        indexes = listView.selectedIndexes()
        if not indexes:
            return

        text = self.tr("&Restore these files") if len(
            indexes) > 1 else self.tr("&Restore this file")
        self._acRestoreFiles.setText(text)
        self._acRestoreFiles.setData(listView)
        self._contexMenu.exec(listView.mapToGlobal(pos))

    def _setupContextMenu(self):
        self._contexMenu = QMenu(self)
        self._acRestoreFiles = self._contexMenu.addAction(
            self.tr("&Restore this file"),
            self._onRestoreFiles)
        self._contexMenu.addSeparator()
        self._contexMenu.addAction(self.tr("External &diff"),
                                   self._onExternalDiff)
        self._contexMenu.addSeparator()
        self._contexMenu.addAction(self.tr("&Open Containing Folder"),
                                   self._onOpenContainingFolder)

    @staticmethod
    def _filterUntrackedFiles(model: QAbstractListModel, index: QModelIndex):
        statusCode = model.data(index, StatusFileListModel.StatusCodeRole)
        return statusCode in ["?", "!"]

    def _onRestoreFiles(self):
        listView: QListView = self._acRestoreFiles.data()
        repoFiles = self._collectSectionFiles(
            listView, CommitWindow._filterUntrackedFiles)
        if not repoFiles:
            return

        self._blockUI()
        self.ui.spinnerUnstaged.start()
        self._submoduleExecutor.submit(repoFiles, self._doRestoreStaged)
        self._curFile = None
        self._curFileStatus = None

    def _doRestore(self, submodule: str, files: List[str], cancelEvent: CancelEvent):
        self._doRestoreFiles(submodule, files, cancelEvent, False)

    def _doRestoreStaged(self, submodule: str, files: List[str], cancelEvent: CancelEvent):
        self._doRestoreFiles(submodule, files, cancelEvent, True)

    def _doRestoreFiles(self, submodule: str, files: List[str], cancelEvent: CancelEvent, isStaged: bool):
        if cancelEvent.isSet():
            return

        repoDir = fullRepoDir(submodule)
        repoFiles = [toSubmodulePath(submodule, file) for file in files]
        error = Git.restoreFiles(repoDir, repoFiles, isStaged)
        ApplicationBase.instance().postEvent(
            self, FileRestoreEvent(submodule, files, error))

    def _handleFileRestoreEvent(self, submodule: str, files: List[str], error: str):
        if error:
            QMessageBox.critical(
                self,
                self.tr("Restore File Failed"),
                error,
                QMessageBox.Ok)
            return

        for file in files:
            self._stagedModel.removeFile(file, submodule)
            self._filesModel.removeFile(file, submodule)

    def _onAmendToggled(self, checked: bool):
        self._updateCommitButtonState()
        if not checked:
            return

        if not self._canUpdateMessage():
            return

        submoduleFiles = self._collectModelFiles(self._stagedModel)
        if not submoduleFiles:
            return

        if self._submoduleExecutor.isRunning():
            logger.info(
                "Submodule executor is running, ignore get last commit message")
            return

        # get the last commit message
        self._blockUI()
        self.ui.spinnerUnstaged.start()
        self._submoduleExecutor.submit(
            list(submoduleFiles.keys()), self._doGetMessage)

    def _canUpdateMessage(self):
        doc = self.ui.teMessage.document()

        # should be template if no undo
        if not doc.isUndoAvailable():
            return True

        isEmpty = doc.isEmpty() or not doc.toPlainText().strip()
        if isEmpty:
            return True

        return False

    def _doGetMessage(self, submodule: str, userData, cancelEvent: CancelEvent):
        if cancelEvent.isSet():
            return

        repoDir = fullRepoDir(submodule)
        message = Git.commitMessage("HEAD", repoDir)
        if cancelEvent.isSet():
            return
        ApplicationBase.instance().postEvent(self, TemplateReadyEvent(message, True))

    def _onExternalDiff(self):
        listView: QListView = self._acRestoreFiles.data()
        index = listView.currentIndex()
        if not index.isValid():
            return
        if listView == self.ui.lvFiles:
            self._onFilesDoubleClicked(index)
        else:
            self._onStagedDoubleClicked(index)

    def _onOpenContainingFolder(self):
        listView: QListView = self._acRestoreFiles.data()
        index = listView.currentIndex()
        if not index.isValid():
            return

        fullPath = os.path.join(Git.REPO_DIR, index.data())
        if os.name == "nt":
            args = ["/select,", fullPath.replace("/", "\\")]
            QProcess.startDetached("explorer", args)
        else:
            dir = QFileInfo(fullPath).absolutePath()
            QDesktopServices.openUrl(QUrl.fromLocalFile(dir))

    def _onRepoDirChanged(self):
        self.clear()
        self._branchLabel.clear()
        self.cancel()
        if not Git.REPO_DIR:
            return

        self._infoFetcher.submit(None, self._fetchRepoInfo)

        self._findSubmoduleThread = FindSubmoduleThread(Git.REPO_DIR, self)
        self._findSubmoduleThread.finished.connect(
            self._onFindSubmoduleFinished)
        self._findSubmoduleThread.finished.connect(
            self._onThreadFinished)
        self._findSubmoduleThread.setRepoDir(Git.REPO_DIR)
        self._threads.append(self._findSubmoduleThread)

        self._findSubmoduleThread.start()
        self._loadLocalChanges()

    def _onMessageChanged(self):
        if self.ui.btnCancelGen.isVisible():
            return

        doc = self.ui.teMessage.document()
        isEmpty = doc.isEmpty() or not doc.toPlainText().strip()
        self.ui.btnRefineMsg.setEnabled(not isEmpty)

    def _onThreadFinished(self):
        thread = self.sender()
        if thread in self._threads:
            self._threads.remove(thread)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            findWidget = self.ui.viewer.findWidget
            if findWidget and findWidget.isVisible():
                findWidget.hideAnimate()
                return

        super().keyPressEvent(event)

    def _handleNtpDateTimeReadyEvent(self, ntpDateTime: QDateTime, localDateTime: QDateTime):
        # ms elapsed since last local time
        ms = localDateTime.msecsTo(QDateTime.currentDateTime())
        self._ntpDateTime = ntpDateTime.addMSecs(ms)

        self._ntpElapsed = QElapsedTimer()
        self._ntpElapsed.start()

        # 10 seconds difference is acceptable
        outOfSync = abs(ntpDateTime.secsTo(localDateTime)) > 10
        if outOfSync or ApplicationBase.instance().settings().useNtpTime():
            self._showNtpTime(outOfSync)
        else:
            self._clearNtpTime()

    def _onUpdateNtpTime(self):
        self._ntpDateTime = self._ntpDateTime.addMSecs(
            self._ntpElapsed.elapsed())
        self._ntpElapsed.restart()
        self._ntpDateTimeLabel.setText(
            self._ntpDateTime.toString("yyyy/MM/dd hh:mm:ss"))

        interval = 1000 - self._ntpDateTime.toMSecsSinceEpoch() % 1000
        self._ntpTimer.start(interval)

    def _showNtpTime(self, outOfSync=False):
        self._ntpTimer = QTimer(self)
        self._ntpTimer.setSingleShot(True)
        self._ntpTimer.timeout.connect(self._onUpdateNtpTime)
        self._onUpdateNtpTime()

        self._ntpDateTimeLabel.setVisible(True)
        if outOfSync:
            self._ntpDateTimeLabel.setColorSchema("ErrorText")
            self._ntpDateTimeLabel.setToolTip(
                self.tr("Local time is not synchronized with the network time"))
        else:
            self._ntpDateTimeLabel.setColorSchema(None)
            self._ntpDateTimeLabel.setToolTip("")

    def _clearNtpTime(self):
        if self._ntpTimer:
            self._ntpTimer.stop()
            self._ntpTimer = None
        self._ntpDateTimeLabel.setVisible(False)

    def _isDateTimeOutOfSync(self) -> bool:
        if not self._ntpDateTime:
            return False

        # 10 seconds difference is acceptable
        return abs(self._ntpDateTime.secsTo(QDateTime.currentDateTime())) > 10

    def _onUseNtpTimeChanged(self, use: bool):
        if not use:
            if not self._isDateTimeOutOfSync():
                self._clearNtpTime()
            return

        if not self._ntpDateTime:
            # TODO: maybe NTP unavailable
            pass
        elif not self._ntpTimer:
            self._showNtpTime(self._isDateTimeOutOfSync())
