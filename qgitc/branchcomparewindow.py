# -*- coding: utf-8 -*-

from qgitc.applicationbase import ApplicationBase
from qgitc.events import ShowCommitEvent
from qgitc.gitutils import Git
from qgitc.statewindow import StateWindow
from qgitc.ui_branchcomparewindow import Ui_BranchCompareWindow


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
        self._setupSignals()

    def _setupSignals(self):
        # TODO: delayed loading
        self.ui.cbBaseBranch.currentIndexChanged.connect(self._loadChanges)
        self.ui.cbTargetBranch.currentIndexChanged.connect(self._loadChanges)
        self.ui.btnShowLogWindow.clicked.connect(self._showLogWindow)

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
            self.ui.cbBaseBranch.setCurrentIndex(curBranchIdx)

        self.ui.cbTargetBranch.setCurrentIndex(-1)
        self.ui.cbBaseBranch.blockSignals(False)
        self.ui.cbTargetBranch.blockSignals(False)

        self._loadChanges()

    def _loadChanges(self):
        pass

    def _showLogWindow(self):
        app = ApplicationBase.instance()
        app.postEvent(app, ShowCommitEvent(None))
