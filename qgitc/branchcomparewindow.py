# -*- coding: utf-8 -*-
import os
from typing import Dict, List, Tuple

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QTimer,
)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QMessageBox,
    QWidget,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.branchcomparefetcher import BranchCompareFetcher
from qgitc.colorediconlabel import ColoredIconLabel
from qgitc.coloredlabel import ColoredLabel
from qgitc.common import dataDirPath, fullRepoDir, logger
from qgitc.diffview import DiffView, _makeTextIcon
from qgitc.findconstants import FindFlags
from qgitc.findsubmodules import FindSubmoduleThread
from qgitc.gitutils import Git
from qgitc.settings import Settings
from qgitc.statewindow import StateWindow
from qgitc.ui_branchcomparewindow import Ui_BranchCompareWindow


class BranchFileInfo:
    """Branch comparison file information"""
    
    def __init__(self, file: str, repoDir: str, statusCode: str, fullPath: str = None):
        self.file = file  # relative to repo
        self.repoDir = repoDir  # submodule path
        self.statusCode = statusCode  # A/M/D/R etc.
        self.fullPath = fullPath or file  # full path relative to root


class BranchFileListModel(QAbstractListModel):
    """Model for branch comparison file list"""
    
    StatusCodeRole = Qt.UserRole
    RepoDirRole = Qt.UserRole + 1
    FullPathRole = Qt.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fileList: List[BranchFileInfo] = []
        self._icons = {}

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._fileList)

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def data(self, index, role=Qt.DisplayRole):
        row = index.row()
        if row < 0 or row >= self.rowCount():
            return None

        fileInfo = self._fileList[row]
        
        if role == Qt.DisplayRole:
            return fileInfo.fullPath  # Show full path relative to root
        elif role == BranchFileListModel.StatusCodeRole:
            return fileInfo.statusCode
        elif role == BranchFileListModel.RepoDirRole:
            return fileInfo.repoDir
        elif role == BranchFileListModel.FullPathRole:
            return fileInfo.fullPath
        elif role == Qt.DecorationRole:
            return self._statusIcon(fileInfo.statusCode)
        elif role == Qt.ToolTipRole:
            tooltip = f"Status: {fileInfo.statusCode}"
            if fileInfo.repoDir and fileInfo.repoDir != ".":
                tooltip += f"\nSubmodule: {fileInfo.repoDir}"
            return tooltip

        return None

    def addFile(self, file: str, repoDir: str, statusCode: str):
        # Calculate full path relative to root repository
        if repoDir and repoDir != ".":
            fullPath = os.path.join(repoDir, file).replace("\\", "/")
        else:
            fullPath = file
            
        rowCount = self.rowCount()
        self.beginInsertRows(QModelIndex(), rowCount, rowCount)
        self._fileList.append(BranchFileInfo(file, repoDir, statusCode, fullPath))
        self.endInsertRows()

    def clear(self):
        if self._fileList:
            self.beginRemoveRows(QModelIndex(), 0, len(self._fileList) - 1)
            self._fileList.clear()
            self.endRemoveRows()

    def _statusIcon(self, statusCode):
        icon = self._icons.get(statusCode)
        if not icon:
            font = ApplicationBase.instance().font()
            font.setBold(True)
            
            if statusCode == "A":
                color = ApplicationBase.instance().colorSchema().Adding
            elif statusCode == "M":
                color = ApplicationBase.instance().colorSchema().Modified
            elif statusCode == "D":
                color = ApplicationBase.instance().colorSchema().Deletion
            elif statusCode == "R":
                color = ApplicationBase.instance().colorSchema().Renamed
            else:
                color = ApplicationBase.instance().palette().windowText().color()
                
            icon = _makeTextIcon(statusCode, color, font)
            self._icons[statusCode] = icon
        return icon


class BranchInfoEvent(QEvent):
    """Event for branch information updates"""
    Type = QEvent.User + 10

    def __init__(self, branches: List[str]):
        super().__init__(QEvent.Type(BranchInfoEvent.Type))
        self.branches = branches


class FileListReadyEvent(QEvent):
    """Event when file list is ready"""
    Type = QEvent.User + 11

    def __init__(self, files: List[Tuple[str, str, str]]):  # (file, repoDir, status)
        super().__init__(QEvent.Type(FileListReadyEvent.Type))
        self.files = files


class BranchCompareWindow(StateWindow):
    """Window for comparing branches across repositories"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_BranchCompareWindow()
        self.ui.setupUi(self)

        self.setWindowTitle(self.tr("Branch Compare"))
        
        # Initialize components
        self._setupUI()
        self._setupModels()
        self._setupConnections()
        self._setupSpinners()
        self._setupContextMenu()
        
        # Data fetcher
        self._fetcher = BranchCompareFetcher(self)
        self._fetcher.branchesAvailable.connect(self._onBranchesAvailable)
        self._fetcher.filesAvailable.connect(self._onFilesAvailable)
        self._fetcher.diffAvailable.connect(self._onDiffAvailable)
        self._fetcher.fetchFinished.connect(self._onFetchFinished)
        
        # Find submodules thread
        self._findSubmoduleThread = None
        
        # Current selection
        self._currentFile = None
        self._currentRepoDir = None
        
        # Load initial data
        self._loadBranches()
        
        ApplicationBase.instance().repoDirChanged.connect(self._onRepoDirChanged)
        
        if Git.REPO_DIR:
            self._onRepoDirChanged()

    def _setupUI(self):
        """Setup UI components"""
        # Branch selection layout
        branchLayout = QHBoxLayout()
        branchLayout.addWidget(QLabel(self.tr("Base branch:")))
        
        self.cbBaseBranch = QComboBox()
        self.cbBaseBranch.setMinimumWidth(150)
        branchLayout.addWidget(self.cbBaseBranch)
        
        branchLayout.addWidget(QLabel(self.tr("Compare branch:")))
        
        self.cbCompareBranch = QComboBox()
        self.cbCompareBranch.setMinimumWidth(150)
        branchLayout.addWidget(self.cbCompareBranch)
        
        branchLayout.addStretch()
        
        # Refresh button
        iconsPath = dataDirPath() + "/icons/"
        self.btnRefresh = self.ui.tbRefresh
        self.btnRefresh.setIcon(QIcon(iconsPath + "refresh.svg"))
        self.btnRefresh.setToolTip(self.tr("Refresh"))
        
        branchLayout.addWidget(self.btnRefresh)
        
        # Add to main layout
        self.ui.branchLayout.addLayout(branchLayout)

    def _setupModels(self):
        """Setup data models"""
        self._filesModel = BranchFileListModel(self)
        
        # Proxy model for filtering
        self._filesProxyModel = QSortFilterProxyModel(self)
        self._filesProxyModel.setSourceModel(self._filesModel)
        
        self.ui.lvFiles.setModel(self._filesProxyModel)
        self.ui.lvFiles.setEditTriggers(QAbstractItemView.NoEditTriggers)

    def _setupConnections(self):
        """Setup signal connections"""
        self.cbBaseBranch.currentTextChanged.connect(self._onBranchSelectionChanged)
        self.cbCompareBranch.currentTextChanged.connect(self._onBranchSelectionChanged)
        self.btnRefresh.clicked.connect(self._onRefreshClicked)
        
        self.ui.lvFiles.selectionModel().currentRowChanged.connect(self._onFileSelectionChanged)
        self.ui.lvFiles.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.lvFiles.customContextMenuRequested.connect(self._onFilesContextMenuRequested)
        
        # Filter connections
        self.ui.leFilterFiles.textChanged.connect(self._onFilterFilesChanged)
        self.ui.leFilterFiles.findFlagsChanged.connect(self._onFilterFilesFlagsChanged)

    def _setupSpinners(self):
        """Setup loading spinners"""
        height = self.btnRefresh.height() // 7
        
        self.ui.spinnerFiles.setLineLength(height)
        self.ui.spinnerFiles.setInnerRadius(height)
        self.ui.spinnerFiles.setNumberOfLines(14)
        
        self.ui.spinnerDiff.setLineLength(height)
        self.ui.spinnerDiff.setInnerRadius(height)
        self.ui.spinnerDiff.setNumberOfLines(14)

    def _setupContextMenu(self):
        """Setup context menu"""
        self._contextMenu = QMenu(self)
        self._contextMenu.addAction(self.tr("External &diff"), self._onExternalDiff)
        self._contextMenu.addSeparator()
        self._contextMenu.addAction(self.tr("&Open Containing Folder"), self._onOpenContainingFolder)

    def _loadBranches(self):
        """Load available branches"""
        if not Git.REPO_DIR:
            return
            
        self.ui.spinnerFiles.start()
        self._fetcher.fetchBranches()

    def _onBranchesAvailable(self, branches: List[str]):
        """Handle available branches"""
        self.ui.spinnerFiles.stop()
        
        # Update combo boxes
        self.cbBaseBranch.blockSignals(True)
        self.cbCompareBranch.blockSignals(True)
        
        self.cbBaseBranch.clear()
        self.cbCompareBranch.clear()
        
        for branch in branches:
            self.cbBaseBranch.addItem(branch)
            self.cbCompareBranch.addItem(branch)
        
        # Set default selections
        if branches:
            # Try to set master/main as base
            for defaultBase in ["master", "main"]:
                index = self.cbBaseBranch.findText(defaultBase)
                if index >= 0:
                    self.cbBaseBranch.setCurrentIndex(index)
                    break
            
            # Set current branch as compare target
            currentBranch = Git.activeBranch()
            if currentBranch and currentBranch in branches:
                index = self.cbCompareBranch.findText(currentBranch)
                if index >= 0:
                    self.cbCompareBranch.setCurrentIndex(index)
        
        self.cbBaseBranch.blockSignals(False)
        self.cbCompareBranch.blockSignals(False)
        
        # Load comparison if both branches are selected
        self._loadComparison()

    def _onBranchSelectionChanged(self):
        """Handle branch selection change"""
        self._loadComparison()

    def _loadComparison(self):
        """Load branch comparison"""
        baseBranch = self.cbBaseBranch.currentText()
        compareBranch = self.cbCompareBranch.currentText()
        
        if not baseBranch or not compareBranch or baseBranch == compareBranch:
            self._filesModel.clear()
            self.ui.viewer.clear()
            return
        
        self._filesModel.clear()
        self.ui.viewer.clear()
        self.ui.spinnerFiles.start()
        
        # Get submodules and fetch comparison
        submodules = ApplicationBase.instance().settings().submodulesCache(Git.REPO_DIR)
        self._fetcher.fetchComparison(baseBranch, compareBranch, submodules)

    def _onFilesAvailable(self, files: List[Tuple[str, str, str]]):
        """Handle available files from comparison"""
        for file, repoDir, status in files:
            self._filesModel.addFile(file, repoDir, status)

    def _onFetchFinished(self):
        """Handle fetch completion"""
        self.ui.spinnerFiles.stop()

    def _onFileSelectionChanged(self, current: QModelIndex, previous: QModelIndex):
        """Handle file selection change"""
        self.ui.viewer.clear()
        
        if not current.isValid():
            self._currentFile = None
            self._currentRepoDir = None
            return
        
        # Get file info
        file = self._filesProxyModel.data(current, Qt.DisplayRole)
        fullPath = self._filesProxyModel.data(current, BranchFileListModel.FullPathRole)
        repoDir = self._filesProxyModel.data(current, BranchFileListModel.RepoDirRole)
        
        self._currentFile = file
        self._currentRepoDir = repoDir
        
        # Show diff
        self._showFileDiff(fullPath, repoDir)

    def _showFileDiff(self, fullPath: str, repoDir: str):
        """Show diff for selected file"""
        baseBranch = self.cbBaseBranch.currentText()
        compareBranch = self.cbCompareBranch.currentText()
        
        if not baseBranch or not compareBranch:
            return
        
        self.ui.spinnerDiff.start()
        
        # Extract actual file path relative to the repo
        if repoDir and repoDir != ".":
            # Remove the submodule prefix to get the file path within the submodule
            if fullPath.startswith(repoDir + "/"):
                filePath = fullPath[len(repoDir) + 1:]
            else:
                filePath = fullPath
        else:
            filePath = fullPath
        
        self._fetcher.fetchFileDiff(baseBranch, compareBranch, filePath, repoDir)

    def _onDiffAvailable(self, lineItems, fileItems):
        """Handle diff content available"""
        self.ui.spinnerDiff.stop()
        self.ui.viewer.appendLines(lineItems)

    def _onRefreshClicked(self):
        """Handle refresh button click"""
        self._loadBranches()

    def _onFilesContextMenuRequested(self, pos):
        """Handle files context menu request"""
        index = self.ui.lvFiles.indexAt(pos)
        if not index.isValid():
            return
        
        self._contextMenu.exec(self.ui.lvFiles.mapToGlobal(pos))

    def _onExternalDiff(self):
        """Open external diff tool"""
        if not self._currentFile or not self._currentRepoDir:
            return
        
        baseBranch = self.cbBaseBranch.currentText()
        compareBranch = self.cbCompareBranch.currentText()
        
        if not baseBranch or not compareBranch:
            return
        
        # Build git command for external diff
        repoDir = fullRepoDir(self._currentRepoDir)
        
        try:
            args = ["difftool", "--no-prompt", f"{baseBranch}..{compareBranch}", "--", self._currentFile]
            Git.run(args, repoDir=repoDir)
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("External Diff Error"),
                str(e),
                QMessageBox.Ok
            )

    def _onOpenContainingFolder(self):
        """Open containing folder"""
        if not self._currentFile or not self._currentRepoDir:
            return
        
        repoDir = fullRepoDir(self._currentRepoDir)
        filePath = os.path.join(repoDir, self._currentFile)
        folderPath = os.path.dirname(filePath)
        
        if os.path.exists(folderPath):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(folderPath))

    def _onFilterFilesChanged(self, text: str):
        """Handle file filter change"""
        flags = self.ui.leFilterFiles.findFlags
        caseSensitive = Qt.CaseInsensitive
        if flags & FindFlags.CaseSenitively:
            caseSensitive = Qt.CaseSensitive
        
        self._filesProxyModel.setFilterCaseSensitivity(caseSensitive)
        
        if not (flags & FindFlags.UseRegExp):
            import re
            text = re.escape(text)
        if flags & FindFlags.WholeWords:
            text = r"\b" + text + r"\b"
        
        self._filesProxyModel.setFilterRegularExpression(text)

    def _onFilterFilesFlagsChanged(self, flags: FindFlags):
        """Handle filter flags change"""
        self._onFilterFilesChanged(self.ui.leFilterFiles.text())

    def _onRepoDirChanged(self):
        """Handle repository directory change"""
        self._filesModel.clear()
        self.ui.viewer.clear()
        self.cbBaseBranch.clear()
        self.cbCompareBranch.clear()
        
        if Git.REPO_DIR:
            self._loadBranches()

    def isMaximizedByDefault(self):
        return False

    def restoreState(self):
        if not super().restoreState():
            return False
        
        settings = ApplicationBase.instance().settings()
        
        # Restore splitter states
        state = settings.getSplitterState("bcw.splitterMain")
        if state:
            self.ui.splitterMain.restoreState(state)
        
        state = settings.getSplitterState("bcw.splitterRight")
        if state:
            self.ui.splitterRight.restoreState(state)
        
        return True

    def saveState(self):
        if not super().saveState():
            return False
        
        settings = ApplicationBase.instance().settings()
        
        # Save splitter states
        settings.saveSplitterState("bcw.splitterMain", self.ui.splitterMain.saveState())
        settings.saveSplitterState("bcw.splitterRight", self.ui.splitterRight.saveState())
        
        return True

    def closeEvent(self, event):
        """Handle close event"""
        if self._fetcher:
            self._fetcher.cancel()
        
        if self._findSubmoduleThread:
            self._findSubmoduleThread.requestInterruption()
            self._findSubmoduleThread = None
        
        super().closeEvent(event)

    def event(self, evt: QEvent):
        """Handle custom events"""
        if evt.type() == BranchInfoEvent.Type:
            self._onBranchesAvailable(evt.branches)
            return True
        elif evt.type() == FileListReadyEvent.Type:
            self._onFilesAvailable(evt.files)
            return True
        
        return super().event(evt)
