# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from ui.gitview import *
from common import *

import subprocess
import re


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
        self.findPattern = None
        self.findNext = True
        self.findField = FindField.Comments

        height = self.ui.splitter.sizeHint().height()
        sizes = [height * 1 / 4, height * 3 / 4]
        self.ui.splitter.setSizes(sizes)

        self.ui.cbBranch.currentIndexChanged.connect(self.__onBranchChanged)
        self.ui.logView.currentIndexChanged.connect(self.__onCommitChanged)
        self.ui.logView.findFinished.connect(self.__onFindFinished)
        self.ui.logView.findProgress.connect(self.__onFindProgress)
        self.ui.diffView.requestCommit.connect(self.__onRequestCommit)

        self.reqCommit.connect(self.__onReqCommit)
        self.reqFind.connect(self.__onFindCommit)

        self.ui.tbPrev.clicked.connect(self.__onPreFindCommit)
        self.ui.tbNext.clicked.connect(self.__onNextFindCommit)

        self.ui.leSha1.returnPressed.connect(self.reqCommit)
        self.ui.leFindWhat.returnPressed.connect(self.reqFind)

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
            commits = data.decode("utf-8", "replace").split("\0")
            self.ui.logView.setLogs(commits)

    def __onCommitChanged(self, index):
        if self.ui.logView.cancelFindCommit():
            self.unsetCursor()
        if index != -1:
            commit = self.ui.logView.getCommit(index)
            self.ui.leSha1.setText(commit.sha1)
            self.ui.diffView.showCommit(commit)
        else:
            self.ui.leSha1.clear()
            self.ui.diffView.clear()

    def __doFindCommit(self, beginCommit=0, findNext=True):
        findWhat = self.ui.leFindWhat.text().strip()
        self.findField = self.ui.cbFindWhat.currentIndex()
        findType = self.ui.cbFindType.currentIndex()
        self.findNext = findNext

        if not findWhat:
            self.ui.logView.highlightKeyword(None)
            self.ui.diffView.highlightKeyword(None)
            return

        pattern = findWhat
        # not regexp, escape the special chars
        if findType != 2:
            pattern = normalizeRegex(findWhat)

        flags = re.IGNORECASE if findType == 1 else 0
        self.findPattern = re.compile(pattern, flags)
        findRange = range(beginCommit, self.ui.logView.getCount()
                          ) if findNext else range(beginCommit, -1, -1)

        findStarted = self.ui.logView.findCommitAsync(
            self.findPattern, findRange, self.findField)

        if findStarted:
            self.window().showProgress(100, self.branchA)
            self.setCursor(Qt.WaitCursor)

    def __onReqCommit(self):
        sha1 = self.ui.leSha1.text().strip()
        if sha1:
            ok = self.ui.logView.switchToCommit(sha1)
            if not ok:
                self.window().showMessage(
                    self.tr("Revision '{0}' is not known".format(sha1)))

    def __onFindCommit(self):
        beginCommit = self.ui.logView.currentIndex()
        self.__doFindCommit(beginCommit, True)

    def __onPreFindCommit(self, checked=False):
        beginCommit = self.ui.logView.currentIndex() - 1
        self.__doFindCommit(beginCommit, False)

    def __onNextFindCommit(self, checked=False):
        beginCommit = self.ui.logView.currentIndex() + 1
        self.__doFindCommit(beginCommit, True)

    def __onFindFinished(self, result):
        self.window().hideProgress(self.branchA)
        self.unsetCursor()

        pattern = self.findPattern
        if self.findField == FindField.Comments:  # comments
            self.ui.logView.highlightKeyword(pattern)
        else:
            self.ui.logView.highlightKeyword(None)
        self.ui.diffView.highlightKeyword(pattern, self.findField)

        if result >= 0:
            self.ui.logView.setCurrentIndex(result)
        elif result == -1:
            message = None
            if self.findNext:
                message = self.tr("Find reached the end of logs.")
            else:
                message = self.tr("Find reached the beginning of logs.")

            self.window().showMessage(message)

    def __onFindProgress(self, progress):
        self.window().updateProgress(progress, self.branchA)

    def __onRequestCommit(self, sha1, isNear, goNext):
        if isNear:
            self.ui.logView.switchToNearCommit(sha1, goNext)
        else:
            self.ui.logView.switchToCommit(sha1)

    def __filterLog(self, pattern):
        if pattern != self.pattern:
            self.pattern = pattern
            index = self.ui.cbBranch.currentIndex()
            preSha1 = None
            if pattern == None:
                curIdx = self.ui.logView.currentIndex()
                if curIdx != -1:
                    preSha1 = self.ui.logView.getCommit(curIdx).sha1

            self.__onBranchChanged(index)

            if preSha1:
                self.ui.logView.switchToCommit(preSha1)

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

    def saveState(self, settings, isBranchA):
        state = self.ui.splitter.saveState()
        settings.setGitViewState(state, isBranchA)

        self.ui.diffView.saveState(settings, isBranchA)

    def restoreState(self, settings, isBranchA):
        state = settings.gitViewState(isBranchA)

        if state:
            self.ui.splitter.restoreState(state)

        self.ui.diffView.restoreState(settings, isBranchA)

    def updateSettings(self):
        self.ui.logView.updateSettings()
        self.ui.diffView.updateSettings()
