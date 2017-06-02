# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from ui.gitview import *
from common import *
from git import Git

import re


class BranchFilterProxyModel(QSortFilterProxyModel):

    def __init__(self, parent=None):
        super(BranchFilterProxyModel, self).__init__(parent)

    def filterAcceptsRow(self, sourceRow, sourceParent):
        regExp = self.filterRegExp()
        if regExp.isEmpty():
            return False

        model = self.sourceModel()
        index = model.index(sourceRow, 0, sourceParent)
        if not index.isValid():
            return False

        branch = index.data(Qt.DisplayRole).lower()
        pattern = regExp.pattern().lower()

        if branch == pattern:
            return False
        return pattern in branch


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

        self.ui.cbBranch.setInsertPolicy(QComboBox.NoInsert)
        self.ui.cbBranch.setEditable(True)

        # Qt5: uses setFilterMode(Qt.MatchContains) instead the buggy code
        self.filterModel = BranchFilterProxyModel(self)
        self.filterModel.setSourceModel(self.ui.cbBranch.model())
        self.ui.cbBranch.completer().setModel(self.filterModel)
        self.ui.cbBranch.completer().setCompletionMode(
            QCompleter.UnfilteredPopupCompletion)

        self.__setupSignals()

    def __setupSignals(self):
        self.ui.cbBranch.currentIndexChanged.connect(self.__onBranchChanged)
        # don't use editTextChanged as it will emit when activated signaled
        self.ui.cbBranch.lineEdit().textEdited.connect(
            self.filterModel.setFilterFixedString)

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

        self.ui.cbBranch.completer().activated.connect(self.__onBranchChanged)

    def __updateBranches(self):
        self.ui.cbBranch.clear()
        self.ui.logView.clear()
        self.ui.diffView.clear()
        self.ui.leSha1.clear()

        if not self.repo:
            return

        branches = Git.branches()
        if not branches:
            self.window().showMessage(self.tr("Can't get branch"))
            return

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
        if self.ui.cbBranch.count() == 0:
            return
        if isinstance(index, int) and index == -1:
            return
        if isinstance(index, str) and not index:
            return

        self.ui.logView.clear()
        self.ui.diffView.clear()

        qApp.setOverrideCursor(Qt.WaitCursor)

        curBranch = self.ui.cbBranch.currentText()
        commits = Git.branchLogs(curBranch, self.pattern)
        if commits:
            self.ui.logView.setLogs(commits)

        qApp.restoreOverrideCursor()

    def __onCommitChanged(self, index):
        if self.ui.logView.cancelFindCommit(False):
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
            self.ui.logView.clearFindData()
            return

        if beginCommit == -1 or \
                beginCommit == self.ui.logView.getCount():
            self.__onFindFinished(FIND_NOTFOUND)
            return

        pattern = findWhat
        # not regexp, escape the special chars
        if findType != FIND_REGEXP:
            pattern = re.escape(findWhat)

        flags = re.IGNORECASE if findType == FIND_IGNORECASE else 0
        self.findPattern = re.compile(pattern, flags)
        findRange = range(beginCommit, self.ui.logView.getCount()
                          ) if findNext else range(beginCommit, -1, -1)

        if self.findField == FindField.Comments:
            self.window().showProgress(100, self.branchA)
            self.setCursor(Qt.WaitCursor)
            result = self.ui.logView.findCommitSync(self.findPattern,
                                                    findRange,
                                                    self.findField)
            self.__onFindFinished(result)
        else:
            param = FindParameter(findRange, findWhat,
                                  self.findField, findType)
            findStarted = self.ui.logView.findCommitAsync(param)
            if findStarted:
                self.window().showProgress(0, self.branchA)
                self.setCursor(Qt.WaitCursor)

    def __onReqCommit(self):
        sha1 = self.ui.leSha1.text().strip()
        if sha1:
            ok = self.ui.logView.switchToCommit(sha1)
            if not ok:
                msg = self.tr("Revision '{0}' is not known")
                self.window().showMessage(msg.format(sha1))

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
        elif result == FIND_NOTFOUND:
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
        self.ui.logView.setFilterPath(path)
        self.__filterLog(newPattern)

    def filterCommit(self, pattern):
        if not pattern:
            newPattern = None
        else:
            newPattern = "--grep={0}".format(pattern)

        self.ui.diffView.setFilterPath(None)
        self.ui.logView.setFilterPath(None)
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
