# -*- coding: utf-8 -*-

import os
import re
from typing import Tuple

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QProcess,
    QSortFilterProxyModel,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QMenu,
    QMessageBox,
    QStyle,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.common import fullRepoDir, toSubmodulePath
from qgitc.difffetcher import DiffFetcher
from qgitc.diffview import DiffView
from qgitc.events import ShowCommitEvent
from qgitc.filestatus import StatusFileItemDelegate, StatusFileListModel
from qgitc.findconstants import FindFlags
from qgitc.gitutils import Git
from qgitc.statewindow import StateWindow
from qgitc.submoduleexecutor import SubmoduleExecutor
from qgitc.ui_branchcomparewindow import Ui_BranchCompareWindow
from qgitc.waitingspinnerwidget import QtWaitingSpinner


class FileStatusEvent(QEvent):
    EventType = QEvent.Type(QEvent.User + 1)

    def __init__(self, file: str, repoDir: str, statusCode: str, oldFile: str = None, mergeBase: str = None):
        super().__init__(FileStatusEvent.EventType)
        self.file = file
        self.repoDir = repoDir
        self.statusCode = statusCode
        self.oldFile = oldFile
        self.mergeBase = mergeBase


class BranchCompareWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_BranchCompareWindow()
        self.ui.setupUi(self)
        self._setupUi()

        width = self.ui.splitterChanges.sizeHint().width()
        sizes = [width * 1 / 5, width * 4 / 5]
        self.ui.splitterChanges.setSizes(sizes)

        height = self.ui.splitter.sizeHint().height()
        sizes = [height * 4 / 5, height * 1 / 5]
        self.ui.splitter.setSizes(sizes)

        self._isFirstShow = True
        self._filesFetcher = SubmoduleExecutor(self)
        self._isBranchDiff = True
        self._tryRenamedIndex = -1
        self._repoMergeBase = {}

        self._contextMenu: QMenu = None

        self._diffFetcher = DiffFetcher(self)
        self._diffFetcher.diffAvailable.connect(
            self._onDiffAvailable)
        self._diffFetcher.fetchFinished.connect(
            self._onDiffFetchFinished)

        self._diffSpinnerDelayTimer = QTimer(self)
        self._diffSpinnerDelayTimer.setSingleShot(True)
        self._diffSpinnerDelayTimer.timeout.connect(self.ui.spinnerDiff.start)

        self._fileSpinnerDelayTimer = QTimer(self)
        self._fileSpinnerDelayTimer.setSingleShot(True)
        self._fileSpinnerDelayTimer.timeout.connect(self.ui.spinnerFiles.start)

        self._loadChangesDelayTimer = QTimer(self)
        self._loadChangesDelayTimer.setSingleShot(True)
        self._loadChangesDelayTimer.timeout.connect(self._loadChanges)

        self._setupSignals()
        self._setupSpinner(self.ui.spinnerFiles)

    def _setupUi(self):
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
            self.tr("Please select base and target branches to see changes"))
        self.ui.lvFiles.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.lvFiles.customContextMenuRequested.connect(
            self._onFilesContextMenuRequested)
        self.ui.lvFiles.setItemDelegate(StatusFileItemDelegate(self))
        self.ui.commitPanel.logView.setAllowSelectOnFetch(False)

        self._setupBranchComboboxes()

    def _setupBranchComboboxes(self):
        self._setupBranchCombobox(self.ui.cbBaseBranch)
        self._setupBranchCombobox(self.ui.cbTargetBranch)

    def _setupBranchCombobox(self, comboBox: QComboBox):
        comboBox.setInsertPolicy(QComboBox.NoInsert)
        comboBox.setEditable(True)

        comboBox.completer().setFilterMode(Qt.MatchContains)
        comboBox.completer().setCompletionMode(
            QCompleter.PopupCompletion)

    def _delayLoadChanges(self):
        self._loadChangesDelayTimer.start(300)

    def _setupSignals(self):
        self.ui.cbBaseBranch.currentIndexChanged.connect(
            self._delayLoadChanges)
        self.ui.cbTargetBranch.currentIndexChanged.connect(
            self._delayLoadChanges)
        self.ui.cbBaseBranch.editTextChanged.connect(
            self._delayLoadChanges)
        self.ui.cbTargetBranch.editTextChanged.connect(
            self._delayLoadChanges)
        self.ui.cbMergeBase.toggled.connect(
            self._delayLoadChanges)

        self.ui.btnShowLogWindow.clicked.connect(self._showLogWindow)
        self._filesFetcher.started.connect(self._onFetchStarted)
        self._filesFetcher.finished.connect(self._onFetchFinished)

        self.ui.commitPanel.logView.currentIndexChanged.connect(
            self._onSha1Changed)

        self.ui.leFileFilter.textChanged.connect(
            self._onFilterTextChanged)
        self.ui.leFileFilter.findFlagsChanged.connect(
            self._onFilterFlagsChanged)

        app = ApplicationBase.instance()
        app.repoDirChanged.connect(self._reloadBranches)

        if not ApplicationBase.instance().style().styleHint(QStyle.SH_ItemView_ActivateItemOnSingleClick):
            self.ui.lvFiles.activated.connect(
                self._onFileDoubleClicked)
        else:
            self.ui.lvFiles.doubleClicked.connect(
                self._onFileDoubleClicked)

    def showEvent(self, event):
        super().showEvent(event)

        if not self._isFirstShow:
            return

        self._reloadBranches()

        self._isFirstShow = False

    def closeEvent(self, event):
        self._filesFetcher.cancel()
        self._diffFetcher.cancel()
        self.ui.commitPanel.logView.queryClose()
        super().closeEvent(event)

    def _reloadBranches(self):
        branches = Git.branches()

        curBranchIdx = -1
        defBranchIdx = -1
        self.ui.cbBaseBranch.blockSignals(True)
        self.ui.cbTargetBranch.blockSignals(True)

        self.ui.cbBaseBranch.clear()
        self.ui.cbTargetBranch.clear()
        self._repoMergeBase.clear()

        for branch in branches:
            branch = branch.strip()
            if branch.startswith("remotes/origin/"):
                if not branch.startswith("remotes/origin/HEAD"):
                    branch = branch.replace("remotes/", "")
                    self.ui.cbBaseBranch.addItem(branch)
                    self.ui.cbTargetBranch.addItem(branch)
            elif branch:
                if branch.startswith("*"):
                    pure_branch = branch.replace("*", "").strip()
                    self.ui.cbBaseBranch.addItem(pure_branch)
                    self.ui.cbTargetBranch.addItem(pure_branch)
                    defBranchIdx = self.ui.cbBaseBranch.count() - 1
                    if curBranchIdx == -1:
                        curBranchIdx = defBranchIdx
                else:
                    if branch.startswith("+ "):
                        branch = branch[2:]
                    branch = branch.strip()
                    self.ui.cbBaseBranch.addItem(branch)
                    self.ui.cbTargetBranch.addItem(branch)

        if curBranchIdx == -1:
            curBranchIdx = defBranchIdx
        if curBranchIdx != -1:
            self.ui.cbTargetBranch.setCurrentIndex(curBranchIdx)

        self.ui.cbBaseBranch.setCurrentIndex(-1)
        self.ui.cbBaseBranch.blockSignals(False)
        self.ui.cbTargetBranch.blockSignals(False)

        self._loadChanges()

    def _loadChanges(self):
        self._filesModel.clear()
        self.ui.diffViewer.clear()
        self.ui.commitPanel.logView.clear()

        baseBranch = self.ui.cbBaseBranch.currentText()
        if not baseBranch:
            return

        targetBranch = self.ui.cbTargetBranch.currentText()
        if not targetBranch:
            return

        submodules = ApplicationBase.instance().submodules or [None]
        repoData = {}
        useMergeBase = self.ui.cbMergeBase.isChecked()
        for submodule in submodules:
            repoData[submodule] = (baseBranch, targetBranch, useMergeBase)

        self._filesFetcher.submit(repoData, self._fetchChanges)

    def _showLogWindow(self):
        app = ApplicationBase.instance()
        app.postEvent(app, ShowCommitEvent(None))

    def _fetchChanges(self, submodule: str, branches: Tuple[str, str, bool], cancelEvent: CancelEvent):
        baseBranch = branches[0]
        targetBranch = branches[1]
        useMergeBase = branches[2]

        if cancelEvent.isSet():
            return None

        repoDir = fullRepoDir(submodule)
        merbeBase = None
        if useMergeBase:
            args = ["merge-base", baseBranch, targetBranch]
            merbeBase = Git.checkOutput(args, True, repoDir).strip()
            if cancelEvent.isSet():
                return None

        args = ["diff", "--name-status",
                f"{merbeBase or baseBranch}..{targetBranch}"]
        data = Git.checkOutput(args, text=True, repoDir=repoDir)
        if cancelEvent.isSet() or not data:
            return None

        app = ApplicationBase.instance()
        lines = data.rstrip().splitlines()
        for line in lines:
            if cancelEvent.isSet():
                return None

            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status = parts[0]
            file = parts[1]
            repoFile = os.path.normpath(os.path.join(
                submodule, file) if submodule and submodule != '.' else file)
            oldFile = None
            if status.startswith("R"):
                status = "R"
                newRepoFile = os.path.normpath(os.path.join(
                    submodule, parts[2]) if submodule and submodule != '.' else parts[2])
                repoFile, oldFile = newRepoFile, repoFile
            app.postEvent(self, FileStatusEvent(
                repoFile, submodule, status, oldFile, merbeBase))

    def _onFetchStarted(self):
        if not self.ui.spinnerFiles.isSpinning():
            self._fileSpinnerDelayTimer.start(500)

    def _onFetchFinished(self):
        self.ui.spinnerFiles.stop()
        self._fileSpinnerDelayTimer.stop()

    def _setupSpinner(self, spinner: QtWaitingSpinner):
        height = self.ui.leFileFilter.height() // 7
        spinner.setLineLength(height)
        spinner.setInnerRadius(height)
        spinner.setNumberOfLines(14)

    def _onSelectFileChanged(self, current: QModelIndex, previous: QModelIndex):
        self.ui.commitPanel.logView.clear()
        self.ui.diffViewer.clear()
        self._tryRenamedIndex = -1
        if not current.isValid():
            return

        baseBranch = self.ui.cbBaseBranch.currentText()
        targetBranch = self.ui.cbTargetBranch.currentText()
        if not baseBranch or not targetBranch:
            return

        repoFile = current.data(Qt.DisplayRole)
        repoDir = current.data(StatusFileListModel.RepoDirRole)
        file = toSubmodulePath(repoDir, repoFile)

        mergeBase = self._repoMergeBase.get(repoDir)
        arg = f"{mergeBase or baseBranch}..{targetBranch}"

        self.ui.commitPanel.showLogs(repoDir, file, args=[arg])
        self.ui.commitPanel.logView.setCurrentIndex(-1)

        self._isBranchDiff = True
        self._showDiff(file, repoDir, arg)

    def _onFileClicked(self, index: QModelIndex):
        if not self._isBranchDiff:
            self._onSelectFileChanged(index, index)

    def _onFilesContextMenuRequested(self, point):
        curIndex = self.ui.lvFiles.indexAt(point)
        if not curIndex.isValid():
            return

        self._setupContextMenu()
        self._contextMenu.exec(self.ui.lvFiles.mapToGlobal(point))

    def event(self, event: QEvent):
        if event.type() == FileStatusEvent.EventType:
            self._handleFileStatusEvent(event)
            return True

        return super().event(event)

    def _handleFileStatusEvent(self, event: FileStatusEvent):
        self._filesModel.addFile(
            event.file, event.repoDir, event.statusCode, event.oldFile)
        self._repoMergeBase[event.repoDir] = event.mergeBase

    def _onDiffAvailable(self, lineItems, fileItems):
        self.ui.diffViewer.appendLines(lineItems)

    def _onDiffFetchFinished(self, exitCode):
        self._diffSpinnerDelayTimer.stop()
        self.ui.spinnerDiff.stop()

        if self._isBranchDiff or self.ui.diffViewer.textLineCount() > 0:
            return

        if self._tryRenamedIndex != -1:
            return

        self._tryRenamedIndex = self.ui.commitPanel.logView.currentIndex()
        self._showDiffForCommit(self._tryRenamedIndex, useOldFile=True)

    def _showDiff(self, file: str, repoDir: str, sha1: str):
        self.ui.diffViewer.clear()
        self._diffFetcher.resetRow(0)

        if repoDir and repoDir != ".":
            self._diffFetcher.cwd = os.path.join(Git.REPO_DIR, repoDir)
            self._diffFetcher.repoDir = repoDir
        else:
            self._diffFetcher.cwd = Git.REPO_DIR
            self._diffFetcher.repoDir = None

        self._diffFetcher.fetch(sha1, [file], None)
        self._diffSpinnerDelayTimer.start(1000)

    def _onSha1Changed(self, index: int):
        self._tryRenamedIndex = -1
        self._showDiffForCommit(index, useOldFile=False)

    def _showDiffForCommit(self, index: int, useOldFile: bool = False):
        self.ui.diffViewer.clear()
        if index == -1:
            return

        commit = self.ui.commitPanel.logView.getCommit(index)
        if not commit:
            return

        selModel = self.ui.lvFiles.selectionModel()
        if not selModel or not selModel.hasSelection():
            return

        selIndex = selModel.currentIndex()
        if not selIndex.isValid():
            return

        self._isBranchDiff = False
        repoFile = selIndex.data(
            StatusFileListModel.OldFileRole if useOldFile else Qt.DisplayRole)
        if not repoFile:
            return

        repoDir = selIndex.data(StatusFileListModel.RepoDirRole)
        file = toSubmodulePath(repoDir, repoFile)
        self._showDiff(file, repoDir, commit.sha1)

    def _onFilterTextChanged(self, text: str):
        model: QSortFilterProxyModel = self.ui.lvFiles.model()
        flags = self.ui.leFileFilter.findFlags
        self._doFilterFiles(model, text, flags)

        ApplicationBase.instance().trackFeatureUsage("bc.filter_files", {
            "caseSensitive": bool(flags & FindFlags.CaseSenitively),
            "wholeWords": bool(flags & FindFlags.WholeWords),
            "useRegExp": bool(flags & FindFlags.UseRegExp),
        })

    def _doFilterFiles(self, model: QSortFilterProxyModel, text: str, flags: FindFlags):
        caseSensitive = Qt.CaseInsensitive
        if flags & FindFlags.CaseSenitively:
            caseSensitive = Qt.CaseSensitive
        model.setFilterCaseSensitivity(caseSensitive)

        if not (flags & FindFlags.UseRegExp):
            text = re.escape(text)
        if (flags & FindFlags.WholeWords):
            text = r"\b" + text + r"\b"
        model.setFilterRegularExpression(text)

    def _onFilterFlagsChanged(self, flags: FindFlags):
        self._onFilterTextChanged(self.ui.leFileFilter.text())

    def compareBranches(self, targetBranch: str = None, baseBranch: str = None):
        if targetBranch:
            self._setBranch(self.ui.cbTargetBranch, targetBranch)

        if baseBranch:
            self._setBranch(self.ui.cbBaseBranch, baseBranch)

    def _setBranch(self, comboBox: QComboBox, branch: str):
        if branch.startswith("remotes/"):
            branch = branch.replace("remotes/", "")

        idx = comboBox.findText(branch)
        if idx != -1:
            comboBox.setCurrentIndex(idx)
        else:
            comboBox.setEditText(branch)

    def restoreState(self):
        if not super().restoreState():
            return False

        sett = ApplicationBase.instance().settings()
        state = sett.getSplitterState("bc.splitter")
        if state:
            self.ui.splitter.restoreState(state)

        state = sett.getSplitterState("bc.splitterChanges")
        if state:
            self.ui.splitterChanges.restoreState(state)

        return True

    def saveState(self):
        if not super().saveState():
            return False

        sett = ApplicationBase.instance().settings()
        sett.saveSplitterState("bc.splitter", self.ui.splitter.saveState())
        sett.saveSplitterState("bc.splitterChanges",
                              self.ui.splitterChanges.saveState())

        return True

    def _setupContextMenu(self):
        if self._contextMenu:
            return

        self._contextMenu = QMenu(self)
        self._contextMenu.addAction(self.tr("External &diff"),
                                   self._onExternalDiff)
        self._contextMenu.addSeparator()
        self._contextMenu.addAction(self.tr("&Open Containing Folder"),
                                   self._onOpenContainingFolder)
        self._contextMenu.addAction(self.tr("&Copy File Path"),
                                    self._onCopyFilePath)

    def _onExternalDiff(self):
        ApplicationBase.instance().trackFeatureUsage("bc.external_diff")
        index = self.ui.lvFiles.currentIndex()
        if not index.isValid():
            return

        self._onFileDoubleClicked(index)

    def _onOpenContainingFolder(self):
        index = self.ui.lvFiles.currentIndex()
        if not index.isValid():
            return

        fullPath = os.path.join(Git.REPO_DIR, index.data())
        if os.name == "nt":
            args = ["/select,", fullPath.replace("/", "\\")]
            QProcess.startDetached("explorer", args)
        else:
            dir = QFileInfo(fullPath).absolutePath()
            QDesktopServices.openUrl(QUrl.fromLocalFile(dir))

    def _onCopyFilePath(self):
        ApplicationBase.instance().trackFeatureUsage("bc.copy_file_path")
        index = self.ui.lvFiles.currentIndex()
        if not index.isValid():
            return

        fullPath = os.path.normpath(os.path.join(Git.REPO_DIR, index.data()))
        clipboard = ApplicationBase.instance().clipboard()
        clipboard.setText(fullPath)

    def _onFileDoubleClicked(self, index: QModelIndex):
        self._runDiffTool(index)

    def _runDiffTool(self, index: QModelIndex):
        if not index.isValid():
            return

        baseBranch = self.ui.cbBaseBranch.currentText()
        if not baseBranch:
            return

        targetBranch = self.ui.cbTargetBranch.currentText()
        if not targetBranch:
            return

        submodule = index.data(StatusFileListModel.RepoDirRole)
        repoDir = index.data(StatusFileListModel.RepoDirRole)
        file = toSubmodulePath(submodule, index.data(Qt.DisplayRole))

        tool = DiffView.diffToolForFile(file)

        mergeBase = self._repoMergeBase.get(repoDir)
        arg = f"{mergeBase or baseBranch}..{targetBranch}"

        args = ["difftool", "--no-prompt", arg]
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
