# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from ui.gitview import *
from common import *

import subprocess


class GitView(QWidget):
    reqCommit = pyqtSignal()
    reqFind = pyqtSignal()

    def __init__(self, parent=None):
        super(GitView, self).__init__(parent)

        self.ui = Ui_GitView()
        self.ui.setupUi(self)
        self.repo = None
        self.pattern = None

        height = self.ui.splitter.sizeHint().height()
        sizes = [height * 1 / 4, height * 3 / 4]
        self.ui.splitter.setSizes(sizes)

        self.ui.cbBranch.currentIndexChanged.connect(self.__onBranchChanged)
        self.ui.logView.selectionModel().currentChanged.connect(self.__onCommitChanged)
        self.ui.btnFind.clicked.connect(self.__onBtnFindClicked)

        self.reqCommit.connect(self.__onReqCommit)
        self.reqFind.connect(self.__onBtnFindClicked)

        self.ui.leSha1.installEventFilter(self)
        self.ui.leFindWhat.installEventFilter(self)

    def __updateBranches(self):
        self.ui.cbBranch.clear()
        self.ui.logView.clear()
        self.ui.diffView.clear()
        self.ui.leSha1.clear()

        if not self.repo:
            return

        data = subprocess.check_output(["git", "branch", "-a"])
        data = data.decode("utf-8")
        branches = data.split('\n')

        curBranchIdx = -1
        self.ui.cbBranch.blockSignals(True)

        for branch in branches:
            branch = branch.strip()
            if branch.startswith("remotes/origin/"):
                if not branch.startswith("remotes/origin/HEAD"):
                    self.ui.cbBranch.addItem(branch)
            elif branch:
                if branch.startswith("*"):
                    self.ui.cbBranch.addItem(branch.replace("*", "").strip())
                    curBranchIdx = self.ui.cbBranch.count() - 1
                else:
                    self.ui.cbBranch.addItem(branch.strip())

        if curBranchIdx != -1:
            self.ui.cbBranch.setCurrentIndex(curBranchIdx)

        self.ui.cbBranch.blockSignals(False)
        branchIdx = self.ui.cbBranch.currentIndex()
        self.__onBranchChanged(branchIdx)

    def __onBranchChanged(self, index):
        if index == -1 or self.ui.cbBranch.count() == 0:
            return

        self.ui.logView.clear()
        self.ui.diffView.clear()

        curBranch = self.ui.cbBranch.currentText()
        args = ["git", "log", "-z",
                "--pretty=format:{0}".format(log_fmt),
                curBranch]
        if self.pattern:
            args.append(self.pattern)

        process = subprocess.Popen(args,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        data = process.communicate()[0]

        if process.returncode is 0 and data:
            commits = data.decode("utf-8").split("\0")
            self.ui.logView.setLogs(commits)

    def __onCommitChanged(self, current, previous):
        if current.isValid():
            commit = current.data(Qt.UserRole)
            self.ui.leSha1.setText(commit.sha1)
            self.ui.diffView.showCommit(commit)
        else:
            self.ui.leSha1.clear()
            self.ui.diffView.clear()

    def __onBtnFindClicked(self, checked):
        pass

    def __onReqCommit(self):
        sha1 = self.ui.leSha1.text().strip()
        if sha1:
            ok = self.ui.logView.switchToCommit(sha1)
            if not ok:
                self.window().showMessage(
                    self.tr("Revision '{0}' is not known".format(sha1)))

    def __filterLog(self, pattern):
        if pattern != self.pattern:
            self.pattern = pattern
            index = self.ui.cbBranch.currentIndex()
            self.__onBranchChanged(index)

    def setBranchDesc(self, desc):
        self.ui.lbBranch.setText(desc)

    def setRepo(self, repo):
        if self.repo != repo:
            self.repo = repo
            self.__updateBranches()

    def filterPath(self, path):
        if not path:
            newPattern = None
        else:
            newPattern = path

        self.ui.diffView.setFilterPath(path)
        self.__filterLog(newPattern)

    def filterCommit(self, pattern):
        if not pattern:
            newPattern = None
        else:
            newPattern = "--grep={0}".format(pattern)

        self.ui.diffView.setFilterPath(None)
        self.__filterLog(newPattern)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyRelease and event.key() == Qt.Key_Return:
            if obj == self.ui.leSha1:
                self.reqCommit.emit()
            elif obj == self.ui.leFindWhat:
                self.reqFind.emit()

        return super(GitView, self).eventFilter(obj, event)
