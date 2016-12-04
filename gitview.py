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
        self.branchA = True

        self.__clearFindState()

        height = self.ui.splitter.sizeHint().height()
        sizes = [height * 1 / 4, height * 3 / 4]
        self.ui.splitter.setSizes(sizes)

        self.ui.cbBranch.currentIndexChanged.connect(self.__onBranchChanged)
        self.ui.logView.currentIndexChanged.connect(self.__onCommitChanged)

        self.reqCommit.connect(self.__onReqCommit)
        self.reqFind.connect(self.__doFindCommit)

        self.ui.tbPrev.clicked.connect(self.__onPreFindCommit)
        self.ui.tbNext.clicked.connect(self.__onNextFindCommit)

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

    def __clearFindState(self):
        self.foundItems = None
        self.curFindItem = -1
        self.ui.tbPrev.setEnabled(False)
        self.ui.tbNext.setEnabled(False)

    def __onBranchChanged(self, index):
        if index == -1 or self.ui.cbBranch.count() == 0:
            return

        self.ui.logView.clear()
        self.ui.diffView.clear()
        self.__clearFindState()

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

    def __onCommitChanged(self, index):
        if index != -1:
            commit = self.ui.logView.getCommit(index)
            self.ui.leSha1.setText(commit.sha1)
            self.ui.diffView.showCommit(commit)
        else:
            self.ui.leSha1.clear()
            self.ui.diffView.clear()

    def __doFindCommit(self):
        findWhat = self.ui.leFindWhat.text().strip()
        findField = self.ui.cbFindWhat.currentIndex()
        findType = self.ui.cbFindType.currentIndex()

        self.__clearFindState()

        # find commit in logview
        if findField == 0:
            self.ui.diffView.findCommit(0, None, findType, False)
            self.foundItems = self.ui.logView.findCommit(0, findWhat, findType)
        else:
            self.foundItems = self.ui.logView.findCommit(0, None, findType)
            self.foundItems = self.ui.diffView.findCommit(
                0, findWhat, findType, findField == 1)

        if self.foundItems:
            self.curFindItem = 0
            self.ui.logView.setCurrentIndex(self.foundItems[0])
            self.ui.tbNext.setEnabled(len(self.foundItems) > 1)
        elif findWhat:
            self.window().showMessage(
                self.tr("Not found '{0}'".format(findWhat)))

    def __onReqCommit(self):
        sha1 = self.ui.leSha1.text().strip()
        if sha1:
            ok = self.ui.logView.switchToCommit(sha1)
            if not ok:
                self.window().showMessage(
                    self.tr("Revision '{0}' is not known".format(sha1)))

    def __onPreFindCommit(self, checked=False):
        # should not happen
        if self.curFindItem == 0:
            return

        self.curFindItem -= 1
        index = self.foundItems[self.curFindItem]
        self.ui.logView.setCurrentIndex(index)

        self.ui.tbPrev.setEnabled(self.curFindItem != 0)
        self.ui.tbNext.setEnabled(True)

    def __onNextFindCommit(self, checked=False):
        # should not happen
        if self.curFindItem + 1 >= len(self.foundItems):
            return

        self.curFindItem += 1
        index = self.foundItems[self.curFindItem]
        self.ui.logView.setCurrentIndex(index)

        self.ui.tbPrev.setEnabled(True)
        self.ui.tbNext.setEnabled(self.curFindItem + 1 != len(self.foundItems))

    def __filterLog(self, pattern):
        if pattern != self.pattern:
            self.pattern = pattern
            index = self.ui.cbBranch.currentIndex()
            self.__onBranchChanged(index)

    def setBranchDesc(self, desc):
        self.ui.lbBranch.setText(desc)

    def setBranchB(self):
        self.branchA = False
        self.ui.logView.setBranchB()

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

    def updateSettings(self):
        self.ui.logView.updateSettings()
        self.ui.diffView.updateSettings()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyRelease and event.key() == Qt.Key_Return:
            if obj == self.ui.leSha1:
                self.reqCommit.emit()
            elif obj == self.ui.leFindWhat:
                self.reqFind.emit()

        return super(GitView, self).eventFilter(obj, event)
