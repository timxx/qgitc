# -*- coding: utf-8 -*-

import re
from typing import List, Tuple

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QMessageBox,
    QProgressDialog,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.common import Commit, dataDirPath, fullRepoDir
from qgitc.events import ShowCommitEvent
from qgitc.gitutils import Git
from qgitc.preferences import Preferences
from qgitc.statewindow import StateWindow
from qgitc.ui_pickbranchwindow import Ui_PickBranchWindow
from qgitc.waitingspinnerwidget import QtWaitingSpinner


class CommitsAvailableEvent(QEvent):
    """Event to notify that commits are available"""
    EventType = QEvent.Type(QEvent.User + 1)

    def __init__(self):
        super().__init__(CommitsAvailableEvent.EventType)


class PickBranchWindow(StateWindow):
    """Window for cherry-picking commits from one branch to another"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_PickBranchWindow()
        self.ui.setupUi(self)
        self._setupUi()

        # Set splitter sizes
        width = self.ui.splitterMain.sizeHint().width()
        sizes = [width * 2 / 5, width * 3 / 5]
        self.ui.splitterMain.setSizes(sizes)

        height = self.ui.splitterRight.sizeHint().height()
        sizes = [height * 3 / 5, height * 2 / 5]
        self.ui.splitterRight.setSizes(sizes)

        self._isFirstShow = True
        self._pendingSourceBranch = None

        # Spinner delay timers
        self._commitSpinnerDelayTimer = QTimer(self)
        self._commitSpinnerDelayTimer.setSingleShot(True)
        self._commitSpinnerDelayTimer.timeout.connect(
            self.ui.spinnerCommits.start)

        # Timer for delayed commits loading
        self._loadCommitsDelayTimer = QTimer(self)
        self._loadCommitsDelayTimer.setSingleShot(True)
        self._loadCommitsDelayTimer.timeout.connect(self._loadCommits)

        self._setupSpinner(self.ui.spinnerCommits)
        self._setupSignals()

        # Setup DiffView with vertical orientation (file list on bottom)
        self.ui.diffView.setFileListOrientation(Qt.Vertical)

    def _setupUi(self):
        """Setup UI components"""
        # Setup branch comboboxes
        self._setupBranchComboboxes()

        # Setup LogView to allow marking commits
        self.ui.logView.setEditable(False)
        self.ui.logView.setShowNoDataTips(True)

        # Setup icons for tool buttons
        iconsPath = dataDirPath() + "/icons/"
        icon = QIcon(iconsPath + "select-all.svg")
        self.ui.btnSelectAll.setIcon(icon)
        icon = QIcon(iconsPath + "clear-all.svg")
        self.ui.btnSelectNone.setIcon(icon)
        icon = QIcon(iconsPath + "filter-list.svg")
        self.ui.btnFilterCommits.setIcon(icon)
        icon = QIcon(iconsPath + "settings.svg")
        self.ui.btnSettings.setIcon(icon)

        self.ui.cbRecordOrigin.setChecked(
            ApplicationBase.instance().settings().recordOrigin())

        # Initialize button states (no commits loaded yet)
        self._updateButtonStates()

    def _setupBranchComboboxes(self):
        """Setup branch selection comboboxes"""
        self._setupBranchCombobox(self.ui.cbSourceBranch)
        self._setupBranchCombobox(self.ui.cbTargetBranch)
        self._setupBranchCombobox(self.ui.cbBaseBranch)

    def _setupBranchCombobox(self, comboBox: QComboBox):
        """Setup a single branch combobox with auto-completion"""
        comboBox.setInsertPolicy(QComboBox.NoInsert)
        comboBox.setEditable(True)
        comboBox.completer().setFilterMode(Qt.MatchContains)
        comboBox.completer().setCompletionMode(QCompleter.PopupCompletion)

    def _setupSignals(self):
        """Connect all signals"""
        # Branch selection changes - only when user selects from dropdown or presses Enter
        self.ui.cbSourceBranch.activated.connect(self._delayLoadCommits)
        self.ui.cbBaseBranch.activated.connect(self._delayLoadCommits)

        # Button clicks
        self.ui.btnShowLogWindow.clicked.connect(self._showLogWindow)
        self.ui.btnSelectAll.clicked.connect(self._selectAllCommits)
        self.ui.btnSelectNone.clicked.connect(self._selectNoneCommits)
        self.ui.btnFilterCommits.clicked.connect(self._filterCommits)
        self.ui.btnSettings.clicked.connect(self._openSettings)
        self.ui.btnCherryPick.clicked.connect(self._onCherryPickClicked)
        self.ui.cbRecordOrigin.toggled.connect(
            lambda checked: ApplicationBase.instance().settings().setRecordOrigin(checked))

        # LogView signals
        self.ui.logView.currentIndexChanged.connect(self._onCommitSelected)
        self.ui.logView.beginFetch.connect(self._onCommitsFetchStarted)
        self.ui.logView.endFetch.connect(self._onCommitsFetchFinished)
        self.ui.logView.markerChanged.connect(self._updateButtonStates)

        # Application signals
        app = ApplicationBase.instance()
        app.repoDirChanged.connect(self._reloadBranches)

    def _setupSpinner(self, spinner: QtWaitingSpinner):
        """Setup spinner appearance"""
        height = self.ui.cbSourceBranch.height() // 7
        spinner.setLineLength(height)
        spinner.setInnerRadius(height)
        spinner.setNumberOfLines(14)

    def showEvent(self, event):
        """Handle show event"""
        super().showEvent(event)

        if not self._isFirstShow:
            return

        QTimer.singleShot(0, self._reloadBranches)
        self._isFirstShow = False

    def closeEvent(self, event):
        """Handle close event"""
        self.ui.diffView.queryClose()
        self.ui.logView.queryClose()
        super().closeEvent(event)

    def event(self, event: QEvent):
        """Handle custom events"""
        if event.type() == CommitsAvailableEvent.EventType:
            # mark all by default
            self._selectAllCommits()

            # Apply filter by default if enabled
            settings = ApplicationBase.instance().settings()
            if settings.applyFilterByDefault():
                self._filterCommits()

            return True

        return super().event(event)

    def setSourceBranch(self, branchName: str):
        """Set source branch by name if it exists in the combobox

        Args:
            branchName: The name of the branch to select
        """
        # If branches haven't been loaded yet, store for later
        if self.ui.cbSourceBranch.count() == 0:
            self._pendingSourceBranch = branchName
            return

        self._pendingSourceBranch = None
        index = self.ui.cbSourceBranch.findText(branchName)
        if index != -1:
            self.ui.cbSourceBranch.setCurrentIndex(index)
            self._delayLoadCommits()

    def _reloadBranches(self):
        """Reload branch list from git"""
        curBranchIdx = -1
        defBranchIdx = -1

        def _blockSignals(block: bool):
            self.ui.cbSourceBranch.blockSignals(block)
            self.ui.cbTargetBranch.blockSignals(block)
            self.ui.cbBaseBranch.blockSignals(block)

        _blockSignals(True)

        self.ui.cbSourceBranch.clear()
        self.ui.cbTargetBranch.clear()
        self.ui.cbBaseBranch.clear()

        branches = Git.branches()
        if not branches:
            text = self.tr("No branches found in the repository") if Git.REPO_DIR else self.tr(
                "Please select a valid repository")
            self._updateStatus(text)
            _blockSignals(False)
            return

        for branch in branches:
            branch = branch.strip()
            if branch.startswith("remotes/origin/"):
                if not branch.startswith("remotes/origin/HEAD"):
                    branch = branch.replace("remotes/", "")
                    self.ui.cbSourceBranch.addItem(branch)
                    self.ui.cbTargetBranch.addItem(branch)
                    self.ui.cbBaseBranch.addItem(branch)
            elif branch:
                if branch.startswith("*"):
                    pure_branch = branch.replace("*", "").strip()
                    self.ui.cbSourceBranch.addItem(pure_branch)
                    self.ui.cbTargetBranch.addItem(pure_branch)
                    self.ui.cbBaseBranch.addItem(pure_branch)
                    defBranchIdx = self.ui.cbTargetBranch.count() - 1
                    if curBranchIdx == -1:
                        curBranchIdx = defBranchIdx
                else:
                    if branch.startswith("+ "):
                        branch = branch[2:]
                    branch = branch.strip()
                    self.ui.cbSourceBranch.addItem(branch)
                    self.ui.cbTargetBranch.addItem(branch)
                    self.ui.cbBaseBranch.addItem(branch)

        # Set current branch as target by default
        if curBranchIdx == -1:
            curBranchIdx = defBranchIdx
        if curBranchIdx != -1:
            self.ui.cbTargetBranch.setCurrentIndex(curBranchIdx)
            # Set base branch to target branch by default
            self.ui.cbBaseBranch.setCurrentIndex(curBranchIdx)

        self.ui.cbSourceBranch.setCurrentIndex(-1)
        # Apply pending source branch if set
        if self._pendingSourceBranch:
            index = self.ui.cbSourceBranch.findText(self._pendingSourceBranch)
            if index != -1:
                self.ui.cbSourceBranch.setCurrentIndex(index)
            self._pendingSourceBranch = None

        _blockSignals(False)

        self._loadCommits()

    def _delayLoadCommits(self):
        """Delay loading commits to avoid too many requests"""
        self._loadCommitsDelayTimer.start(300)

    def _loadCommits(self):
        """Load commits from source branch"""
        self.ui.logView.clear()
        self.ui.diffView.clear()

        sourceBranch = self.ui.cbSourceBranch.currentText()
        baseBranch = self.ui.cbBaseBranch.currentText()

        if not sourceBranch or not baseBranch:
            self._updateButtonStates()
            self._updateStatus(
                self.tr("Please select both source and base branches"))
            return

        if sourceBranch == baseBranch:
            self._updateButtonStates()
            self._updateStatus(
                self.tr("Source and base branches must be different"))
            return

        revisionRange = ["--not", baseBranch]

        branchDir = Git.branchDir(sourceBranch)
        self.ui.logView.showLogs(
            sourceBranch, branchDir, revisionRange)
        self.ui.diffView.setBranchDir(branchDir)
        self._updateStatus(
            self.tr("Loading commits from {0}...").format(sourceBranch))

    def _onCommitsFetchStarted(self):
        """Handle commits fetch started"""
        if not self.ui.spinnerCommits.isSpinning():
            self._commitSpinnerDelayTimer.start(500)

    def _onCommitsFetchFinished(self):
        """Handle commits fetch finished"""
        self._commitSpinnerDelayTimer.stop()
        self.ui.spinnerCommits.stop()

        commitCount = self.ui.logView.getCount()
        if commitCount == 0:
            self._updateButtonStates()
            self._updateStatus(self.tr("No commits to cherry-pick"))
        else:
            self._updateStatus(
                self.tr("Found {0} commit(s) to cherry-pick").format(commitCount))
            # Post event to update button state after UI is ready
            ApplicationBase.instance().postEvent(self, CommitsAvailableEvent())

    def _onCommitSelected(self, index):
        """Handle commit selection change"""
        if index < 0:
            return

        commit = self.ui.logView.getCommit(index)
        if not commit:
            return

        # Show commit in DiffView (handles both details and diff)
        self.ui.diffView.showCommit(commit)

    def _showLogWindow(self):
        """Show the main log window to change repository"""
        app = ApplicationBase.instance()
        app.postEvent(app, ShowCommitEvent(None))

    def _selectAllCommits(self):
        """Select all commits"""
        commitCount = self.ui.logView.getCount()
        if commitCount > 0:
            # Mark all commits
            self.ui.logView.marker.mark(0, commitCount - 1)
            self.ui.logView.viewport().update()
            self._updatePickButton()

    def _selectNoneCommits(self):
        """Deselect all commits"""
        self.ui.logView.marker.clear()
        self.ui.logView.viewport().update()
        self._updatePickButton()

    def _filterCommits(self):
        """Filter commits based on user preferences"""
        app = ApplicationBase.instance()
        settings = app.settings()
        filterReverted = settings.filterRevertedCommits()
        filterPatterns = settings.filterCommitPatterns()
        useRegex = settings.filterUseRegex()

        if not filterReverted and not filterPatterns:
            # No filters enabled, show message
            self._updateStatus(
                self.tr("No filters configured. Please configure filters in Settings > Cherry-Pick"))
            return

        app.trackFeatureUsage("cherry_pick_filter_commits", {
            "filter_reverted": filterReverted,
            "filter_patterns": bool(filterPatterns),
            "use_regex": useRegex,
            "by_default": settings.applyFilterByDefault(),
        })

        commitCount = self.ui.logView.getCount()
        if commitCount == 0:
            return

        # Compile regex patterns if needed
        compiledPatterns = []
        if filterPatterns:
            if useRegex:
                try:
                    compiledPatterns = [re.compile(
                        pattern) for pattern in filterPatterns]
                except re.error as e:
                    self._updateStatus(
                        self.tr("Invalid regex pattern: {0}").format(str(e)))
                    return
            else:
                # Convert to lowercase for case-insensitive matching
                compiledPatterns = [pattern.lower()
                                    for pattern in filterPatterns]

        filteredCount = 0

        # Get currently marked indices
        markedIndices = self.ui.logView.marker.getMarkedIndices()
        for index in markedIndices:
            commit: Commit = self.ui.logView.getCommit(index)
            if not commit:
                continue

            shouldFilter = False

            # Check if commit is a revert commit
            # TODO: check if it is reverted later
            if filterReverted:
                if "This reverts commit " in commit.comments:
                    shouldFilter = True

            # Check if commit matches any pattern
            if not shouldFilter and compiledPatterns:
                lowercase_commit_message = commit.comments.lower()
                for pattern in compiledPatterns:
                    if useRegex:
                        # Pattern is a compiled regex
                        if pattern.search(commit.comments):
                            shouldFilter = True
                            break
                    else:
                        # Pattern is a lowercase string
                        if pattern in lowercase_commit_message:
                            shouldFilter = True
                            break

            # Unmark the commit if it matches filter criteria
            if shouldFilter:
                self.ui.logView.marker.unmark(index)
                filteredCount += 1

        self.ui.logView.viewport().update()
        self._updatePickButton()

        if filteredCount > 0:
            self._updateStatus(
                self.tr("Filtered out {0} commit(s)").format(filteredCount))
        else:
            self._updateStatus(
                self.tr("No commits matched the filter criteria"))

    def _openSettings(self):
        """Open preferences dialog to cherry-pick tab"""
        settings = ApplicationBase.instance().settings()
        dialog = Preferences(settings, self)
        dialog.ui.tabWidget.setCurrentWidget(dialog.ui.tabCherryPick)
        result = dialog.exec()

        # Update UI after preferences dialog closes
        if result == QDialog.Accepted:
            self.ui.cbRecordOrigin.setChecked(settings.recordOrigin())

    def _updateButtonStates(self):
        """Update all button states based on commit count and mark count"""
        commitCount = self.ui.logView.getCount()
        hasMarkedCommits = self.ui.logView.marker.hasMark()
        markedCount = self.ui.logView.marker.countMarked() if hasMarkedCommits else 0

        # Enable/disable buttons based on commit count and mark count
        self.ui.btnSelectAll.setEnabled(
            commitCount > 0 and markedCount < commitCount)
        self.ui.btnSelectNone.setEnabled(markedCount > 0)
        self.ui.btnFilterCommits.setEnabled(markedCount > 0)
        self.ui.btnCherryPick.setEnabled(hasMarkedCommits and commitCount > 0)

        # Update status message
        if not hasMarkedCommits:
            if commitCount > 0:
                status = self.tr("Please select commits to cherry-pick")
            else:
                status = self.tr("No commits available")
        else:
            status = self.tr(
                "Selected {0} commit(s) to cherry-pick").format(markedCount)
        self._updateStatus(status)

    def _updatePickButton(self):
        """Update cherry-pick button state and selection/filter buttons (legacy method)"""
        self._updateButtonStates()

    def _onCherryPickClicked(self):
        """Handle cherry-pick button click"""
        commitCount = self.ui.logView.getCount()
        if commitCount == 0:
            return

        markedCommits: List[Tuple[Commit, int]] = []
        for step in self.ui.logView.marker.getMarkedIndices():
            commit = self.ui.logView.getCommit(step)
            if commit:
                markedCommits.append((commit, step))

        if not markedCommits:
            return

        # Reverse the list to pick from oldest to newest
        markedCommits = list(reversed(markedCommits))

        # Check if target branch is checked out
        targetBranch = self.ui.cbTargetBranch.currentText()
        sourceBranch = self.ui.cbSourceBranch.currentText()
        if targetBranch == sourceBranch:
            QMessageBox.warning(
                self,
                self.tr("Cherry-pick Failed"),
                self.tr("The target branch '{0}' is the same as source branch.\n\n"
                        "Please select a different target branch.").format(targetBranch))
            return

        targetRepoDir = Git.branchDir(targetBranch)
        if not targetRepoDir or not Git.REPO_DIR:
            QMessageBox.warning(
                self,
                self.tr("Cherry-pick Failed"),
                self.tr("The target branch '{0}' is not checked out.\n\n"
                        "Please checkout the branch first.").format(targetBranch))
            return

        progress = QProgressDialog(
            self.tr("Cherry-picking commits..."),
            self.tr("Cancel"),
            0, len(markedCommits), self)
        progress.setWindowTitle(self.window().windowTitle())
        progress.setWindowModality(Qt.NonModal)

        recordOrigin = self.ui.cbRecordOrigin.isChecked()
        sourceBranchDir = Git.branchDir(sourceBranch)
        app = ApplicationBase.instance()
        for step, (commit, index) in enumerate(markedCommits):
            progress.setValue(step)
            app.processEvents()
            if progress.wasCanceled():
                break

            self.ui.logView.ensureVisible(index)

            fullTargetRepoDir = fullRepoDir(commit.repoDir, targetRepoDir)
            fullSourceDir = fullRepoDir(commit.repoDir, sourceBranchDir)
            if not self.ui.logView.doCherryPick(fullTargetRepoDir, commit.sha1, fullSourceDir, self.ui.logView, recordOrigin):
                break

        progress.setValue(len(markedCommits))

    def _updateStatus(self, message: str):
        """Update status label"""
        self.ui.labelStatus.setText(message)
