# -*- coding: utf-8 -*-

from typing import Tuple

from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.common import fullRepoDir
from qgitc.events import ShowCommitEvent
from qgitc.gitutils import Git
from qgitc.statewindow import StateWindow
from qgitc.submoduleexecutor import SubmoduleExecutor
from qgitc.ui_branchcomparewindow import Ui_BranchCompareWindow
from qgitc.waitingspinnerwidget import QtWaitingSpinner


class BranchCompareWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_BranchCompareWindow()
        self.ui.setupUi(self)

        width = self.ui.splitterChanges.sizeHint().width()
        sizes = [width * 1 / 5, width * 4 / 5]
        self.ui.splitterChanges.setSizes(sizes)

        height = self.ui.splitter.sizeHint().height()
        sizes = [height * 4 / 5, height * 1 / 5]
        self.ui.splitter.setSizes(sizes)

        self._isFirstShow = True
        self._filesFetcher = SubmoduleExecutor(self)

        self._setupSignals()
        self._setupSpinner(self.ui.spinnerFiles)

    def _setupSignals(self):
        # TODO: delayed loading
        self.ui.cbBaseBranch.currentIndexChanged.connect(self._loadChanges)
        self.ui.cbTargetBranch.currentIndexChanged.connect(self._loadChanges)
        self.ui.btnShowLogWindow.clicked.connect(self._showLogWindow)
        self._filesFetcher.started.connect(self._onFetchStarted)
        self._filesFetcher.finished.connect(self._onFetchFinished)

    def showEvent(self, event):
        super().showEvent(event)

        if not self._isFirstShow:
            return

        self._reloadBranches()

        self._isFirstShow = False

    def _reloadBranches(self):
        branches = Git.branches()

        curBranchIdx = -1
        defBranchIdx = -1
        self.ui.cbBaseBranch.blockSignals(True)
        self.ui.cbTargetBranch.blockSignals(True)

        self.ui.cbBaseBranch.clear()
        self.ui.cbTargetBranch.clear()

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
        baseBranch = self.ui.cbBaseBranch.currentText()
        if not baseBranch:
            return

        targetBranch = self.ui.cbTargetBranch.currentText()
        if not targetBranch:
            return

        submodules = ApplicationBase.instance().submodules or [None]
        repoData = {}
        for submodule in submodules:
            repoData[submodule] = (baseBranch, targetBranch)

        self._filesFetcher.submit(repoData, self._fetchChanges)

    def _showLogWindow(self):
        app = ApplicationBase.instance()
        app.postEvent(app, ShowCommitEvent(None))

    def _fetchChanges(self, submodule: str, branches: Tuple[str, str], cancelEvent: CancelEvent):
        baseBranch = branches[0]
        targetBranch = branches[1]

        if cancelEvent.isSet():
            return None

        repoDir = fullRepoDir(submodule)
        args = ["diff", "--name-status", f"{baseBranch}..{targetBranch}"]
        data = Git.checkOutput(args, text=True, repoDir=repoDir)
        if cancelEvent.isSet() or not data:
            return None

        lines = data.rstrip().splitlines()

    def _onFetchStarted(self):
        self.ui.spinnerFiles.start()

    def _onFetchFinished(self):
        self.ui.spinnerFiles.stop()

    def _setupSpinner(self, spinner: QtWaitingSpinner):
        height = self.ui.leFileFilter.height() // 7
        spinner.setLineLength(height)
        spinner.setInnerRadius(height)
        spinner.setNumberOfLines(14)
