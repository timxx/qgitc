# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from ui.gitview import *
from common import *

import subprocess


class GitView(QWidget):

    def __init__(self, parent=None):
        super(GitView, self).__init__(parent)

        self.ui = Ui_GitView()
        self.ui.setupUi(self)
        self.repo = None

        height = self.ui.splitter.sizeHint().height()
        sizes = [height * 1 / 4, height * 3 / 4]
        self.ui.splitter.setSizes(sizes)

        self.ui.cbBranch.currentIndexChanged.connect(self.__onBranchChanged)
        self.ui.logView.clicked.connect(self.__onCommitChanged)

    def __updateBranches(self):
        self.ui.cbBranch.clear()
        self.ui.logView.clear()
        self.ui.diffView.clear()
        self.ui.leSha1.clear()

        if not self.repo:
            return

        data = subprocess.check_output(["git", "symbolic-ref", "HEAD"])
        data = data.decode("utf-8").replace("\n", "")
        index = data.rfind('/')
        curBranch = data[index + 1:]

        data = subprocess.check_output(["git", "branch", "-a"])
        data = data.decode("utf-8")
        branches = data.split('\n')

        curBranchIdx = -1
        self.ui.cbBranch.blockSignals(True)

        for branch in branches:
            branch = branch.strip()
            if branch.startswith("remotes/origin/"):
                branch = branch.replace("remotes/origin/", "")
                if not branch.startswith("HEAD"):
                    self.ui.cbBranch.addItem(branch)
                    if curBranchIdx == -1 and branch == curBranch:
                        curBranchIdx = self.ui.cbBranch.count() - 1

        if curBranchIdx != -1:
            self.ui.cbBranch.setCurrentIndex(curBranchIdx)

        self.ui.cbBranch.blockSignals(False)
        branchIdx = self.ui.cbBranch.currentIndex()
        self.__onBranchChanged(branchIdx)

    def __onBranchChanged(self, index):
        if index == -1 or self.ui.cbBranch.count() == 0:
            return

        # TODO: get that branch's log
        data = subprocess.check_output(["git", "log",
                                        "--pretty=format:{0}".format(
                                            short_log_fmt),
                                        "-z", "--boundary"])
        commits = data.decode("utf-8").split("\0")

        self.ui.logView.setLogs(commits)

    def __onCommitChanged(self, index):
        if index.isValid():
            commit = index.data(Qt.UserRole)
            self.ui.leSha1.setText(commit.sha1)
            self.ui.diffView.showCommit(commit)
        else:
            self.ui.leSha1.clear()
            self.ui.diffView.clear()

    def setBranchDesc(self, desc):
        self.ui.lbBranch.setText(desc)

    def setRepo(self, repo):
        if self.repo != repo:
            self.repo = repo
            self.__updateBranches()
