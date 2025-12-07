# -*- coding: utf-8 -*-

from typing import List

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QCompleter, QMessageBox

from qgitc.applicationbase import ApplicationBase
from qgitc.common import Commit, fullRepoDir
from qgitc.difffetcher import DiffFetcher
from qgitc.events import ShowCommitEvent
from qgitc.gitutils import Git
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
        self._mergeBase = None
        self._sourceBranch = None
        self._targetBranch = None

        # Diff fetcher for showing commit diffs
        self._diffFetcher = DiffFetcher(self)
        self._diffFetcher.diffAvailable.connect(self._onDiffAvailable)
        self._diffFetcher.fetchFinished.connect(self._onDiffFetchFinished)

        # Spinner delay timers
        self._diffSpinnerDelayTimer = QTimer(self)
        self._diffSpinnerDelayTimer.setSingleShot(True)
        self._diffSpinnerDelayTimer.timeout.connect(self.ui.spinnerDiff.start)

        self._commitSpinnerDelayTimer = QTimer(self)
        self._commitSpinnerDelayTimer.setSingleShot(True)
        self._commitSpinnerDelayTimer.timeout.connect(
            self.ui.spinnerCommits.start)

        # Timer for delayed commits loading
        self._loadCommitsDelayTimer = QTimer(self)
        self._loadCommitsDelayTimer.setSingleShot(True)
        self._loadCommitsDelayTimer.timeout.connect(self._loadCommits)

        self._setupSpinner(self.ui.spinnerCommits)
        self._setupSpinner(self.ui.spinnerDiff)
        self._setupSignals()

    def _setupUi(self):
        """Setup UI components"""
        # Setup branch comboboxes
        self._setupBranchComboboxes()

        # Setup LogView to allow marking commits
        self.ui.logView.setEditable(False)
        self.ui.logView.setAllowSelectOnFetch(False)
        self.ui.logView.setStandalone(False)
        self.ui.logView.setShowNoDataTips(True)

    def _setupBranchComboboxes(self):
        """Setup branch selection comboboxes"""
        self._setupBranchCombobox(self.ui.cbSourceBranch)
        self._setupBranchCombobox(self.ui.cbTargetBranch)

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
        self.ui.cbTargetBranch.activated.connect(self._delayLoadCommits)
        self.ui.cbMergeBase.toggled.connect(self._delayLoadCommits)

        # Button clicks
        self.ui.btnShowLogWindow.clicked.connect(self._showLogWindow)
        self.ui.btnSelectAll.clicked.connect(self._selectAllCommits)
        self.ui.btnSelectNone.clicked.connect(self._selectNoneCommits)
        self.ui.btnCherryPick.clicked.connect(self._onCherryPickClicked)

        # LogView signals
        self.ui.logView.currentIndexChanged.connect(self._onCommitSelected)
        self.ui.logView.beginFetch.connect(self._onCommitsFetchStarted)
        self.ui.logView.endFetch.connect(self._onCommitsFetchFinished)

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

        self._reloadBranches()
        self._isFirstShow = False

    def closeEvent(self, event):
        """Handle close event"""
        self._diffFetcher.cancel()
        self.ui.logView.queryClose()
        super().closeEvent(event)

    def event(self, event: QEvent):
        """Handle custom events"""
        if event.type() == CommitsAvailableEvent.EventType:
            self._updatePickButton()
            return True

        return super().event(event)

    def _reloadBranches(self):
        """Reload branch list from git"""
        branches = Git.branches()

        curBranchIdx = -1
        defBranchIdx = -1

        self.ui.cbSourceBranch.blockSignals(True)
        self.ui.cbTargetBranch.blockSignals(True)

        self.ui.cbSourceBranch.clear()
        self.ui.cbTargetBranch.clear()

        for branch in branches:
            branch = branch.strip()
            if branch.startswith("remotes/origin/"):
                if not branch.startswith("remotes/origin/HEAD"):
                    branch = branch.replace("remotes/", "")
                    self.ui.cbSourceBranch.addItem(branch)
                    self.ui.cbTargetBranch.addItem(branch)
            elif branch:
                if branch.startswith("*"):
                    pure_branch = branch.replace("*", "").strip()
                    self.ui.cbSourceBranch.addItem(pure_branch)
                    self.ui.cbTargetBranch.addItem(pure_branch)
                    defBranchIdx = self.ui.cbTargetBranch.count() - 1
                    if curBranchIdx == -1:
                        curBranchIdx = defBranchIdx
                else:
                    if branch.startswith("+ "):
                        branch = branch[2:]
                    branch = branch.strip()
                    self.ui.cbSourceBranch.addItem(branch)
                    self.ui.cbTargetBranch.addItem(branch)

        # Set current branch as target by default
        if curBranchIdx == -1:
            curBranchIdx = defBranchIdx
        if curBranchIdx != -1:
            self.ui.cbTargetBranch.setCurrentIndex(curBranchIdx)

        self.ui.cbSourceBranch.setCurrentIndex(-1)
        self.ui.cbSourceBranch.blockSignals(False)
        self.ui.cbTargetBranch.blockSignals(False)

        self._loadCommits()

    def _delayLoadCommits(self):
        """Delay loading commits to avoid too many requests"""
        self._loadCommitsDelayTimer.start(300)

    def _loadCommits(self):
        """Load commits from source branch"""
        self.ui.logView.clear()
        self.ui.diffViewer.clear()
        self.ui.commitDetailPanel.clear()
        self._mergeBase = None

        sourceBranch = self.ui.cbSourceBranch.currentText()
        targetBranch = self.ui.cbTargetBranch.currentText()

        if not sourceBranch or not targetBranch:
            self._updateStatus(
                self.tr("Please select both source and target branches"))
            self.ui.btnCherryPick.setEnabled(False)
            return

        if sourceBranch == targetBranch:
            self._updateStatus(
                self.tr("Source and target branches must be different"))
            self.ui.btnCherryPick.setEnabled(False)
            return

        self._sourceBranch = sourceBranch
        self._targetBranch = targetBranch

        # Calculate merge base if requested
        useMergeBase = self.ui.cbMergeBase.isChecked()
        if useMergeBase:
            try:
                args = ["merge-base", targetBranch, sourceBranch]
                self._mergeBase = Git.checkOutput(args, True).strip()
            except Exception as e:
                self._updateStatus(
                    self.tr("Failed to find merge base: {0}").format(str(e)))
                self.ui.btnCherryPick.setEnabled(False)
                return

        # Load commits using git log
        # Show commits that are in source but not in target
        if useMergeBase and self._mergeBase:
            revisionRange = f"{self._mergeBase}..{sourceBranch}"
        else:
            revisionRange = f"{targetBranch}..{sourceBranch}"

        branchDir = Git.branchDir(sourceBranch)
        self.ui.logView.showLogs(sourceBranch, branchDir, [revisionRange])
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
            self._updateStatus(self.tr("No commits to cherry-pick"))
            self.ui.btnCherryPick.setEnabled(False)
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

        # Show commit details
        self.ui.commitDetailPanel.showCommit(commit)

        # Fetch and show diff
        self.ui.diffViewer.clear()
        self._diffFetcher.resetRow(0)

        if not self.ui.spinnerDiff.isSpinning():
            self._diffSpinnerDelayTimer.start(500)

        repoDir = fullRepoDir(commit.repoDir)
        if repoDir and repoDir != ".":
            self._diffFetcher.cwd = repoDir
            self._diffFetcher.repoDir = commit.repoDir
        else:
            self._diffFetcher.cwd = Git.REPO_DIR
            self._diffFetcher.repoDir = None

        self._diffFetcher.fetch(commit.sha1, [], None)

    def _onDiffAvailable(self, lineItems, fileItems):
        """Handle diff data available"""
        self.ui.diffViewer.appendLines(lineItems)

    def _onDiffFetchFinished(self, exitCode):
        """Handle diff fetch finished"""
        self._diffSpinnerDelayTimer.stop()
        self.ui.spinnerDiff.stop()

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

    def _updatePickButton(self):
        """Update cherry-pick button state"""
        hasMarkedCommits = self.ui.logView.marker.hasMark()
        commitCount = self.ui.logView.getCount()
        self.ui.btnCherryPick.setEnabled(hasMarkedCommits and commitCount > 0)

        if hasMarkedCommits:
            # Count marked commits
            markedCount = sum(1 for i in range(commitCount)
                              if self.ui.logView.marker.isMarked(i))
            self._updateStatus(
                self.tr("Selected {0} commit(s) to cherry-pick").format(markedCount))

    def _onCherryPickClicked(self):
        """Handle cherry-pick button click"""
        # Get marked commits
        commitCount = self.ui.logView.getCount()
        if commitCount == 0:
            return

        markedCommits: List[Commit] = []
        for i in range(commitCount):
            if self.ui.logView.marker.isMarked(i):
                commit = self.ui.logView.getCommit(i)
                if commit:
                    markedCommits.append(commit)

        if not markedCommits:
            return

        # Reverse the list to pick from oldest to newest
        markedCommits = list(reversed(markedCommits))

        # Check if target branch is checked out
        targetRepoDir = Git.branchDir(self._targetBranch)
        if not targetRepoDir or not Git.REPO_DIR:
            QMessageBox.warning(
                self,
                self.tr("Cherry-pick Failed"),
                self.tr("The target branch '{0}' is not checked out.\n\n"
                        "Please checkout the branch first.").format(self._targetBranch))
            return

        # Execute cherry-pick using LogView's implementation
        needReload = False

        recordOrigin = self.ui.cbRecordOrigin.isChecked()
        for commit in markedCommits:
            if self.ui.logView.doCherryPick(targetRepoDir, commit.sha1, commit.repoDir, self.ui.logView, recordOrigin):
                needReload = True
            else:
                # Stop processing remaining commits on error
                break

        # Reload the commit list to show the result
        if needReload:
            self._loadCommits()

    def _updateStatus(self, message: str):
        """Update status label"""
        self.ui.labelStatus.setText(message)
