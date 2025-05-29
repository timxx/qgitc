# -*- coding: utf-8 -*-

import re
from typing import List

from PySide6.QtCore import QMimeData, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QConicalGradient,
    QCursor,
    QFontMetrics,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QFileDialog,
    QFrame,
    QMenu,
    QMessageBox,
    QScrollBar,
    QWidget,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.commitsource import CommitSource
from qgitc.common import *
from qgitc.difffinder import DiffFinder
from qgitc.events import CodeReviewEvent, CopyConflictCommit
from qgitc.gitutils import *
from qgitc.logsfetcher import LogsFetcher
from qgitc.windowtype import WindowType

HALF_LINE_PERCENT = 0.76


class Marker():
    CHAR_MARK = chr(0x2713)

    def __init__(self):
        self._begin = -1
        self._end = -1

    def mark(self, begin, end):
        self._begin = min(begin, end)
        self._end = max(begin, end)

    def clear(self):
        self._begin = -1
        self._end = -1

    def hasMark(self):
        return self._begin != -1 and \
            self._end != -1

    def begin(self):
        return self._begin

    def end(self):
        return self._end

    def isMarked(self, index):
        return self.hasMark() and \
            self._begin <= index and \
            self._end >= index

    def draw(self, index, painter, rect):
        if not self.isMarked(index):
            return

        painter.save()

        painter.setPen(ApplicationBase.instance().colorSchema().Mark)
        br = painter.drawText(rect, Qt.AlignVCenter, Marker.CHAR_MARK)
        rect.adjust(br.width(), 0, 0, 0)

        painter.restore()


# reference to QGit source code
class Lane():
    EMPTY = 0
    ACTIVE = 1
    NOT_ACTIVE = 2
    MERGE_FORK = 3
    MERGE_FORK_R = 4
    MERGE_FORK_L = 5
    JOIN = 6
    JOIN_R = 7
    JOIN_L = 8
    HEAD = 9
    HEAD_R = 10
    HEAD_L = 11
    TAIL = 12
    TAIL_R = 13
    TAIL_L = 14
    CROSS = 15
    CROSS_EMPTY = 16
    INITIAL = 17
    BRANCH = 18
    BOUNDARY = 19
    BOUNDARY_C = 20
    BOUNDARY_R = 21
    BOUNDARY_L = 22
    UNAPPLIED = 23
    APPLIED = 24

    @staticmethod
    def isHead(t):
        return t >= Lane.HEAD and \
            t <= Lane.HEAD_L

    @staticmethod
    def isTail(t):
        return t >= Lane.TAIL and \
            t <= Lane.TAIL_L

    @staticmethod
    def isJoin(t):
        return t >= Lane.JOIN and \
            t <= Lane.JOIN_L

    @staticmethod
    def isFreeLane(t):
        return t == Lane.NOT_ACTIVE or \
            t == Lane.CROSS or \
            Lane.isJoin(t)

    @staticmethod
    def isBoundary(t):
        return t >= Lane.BOUNDARY and \
            t <= Lane.BOUNDARY_L

    @staticmethod
    def isMerge(t):
        return (t >= Lane.MERGE_FORK and
                t <= Lane.MERGE_FORK_L) or \
            Lane.isBoundary(t)

    @staticmethod
    def isActive(t):
        return t == Lane.ACTIVE or \
            t == Lane.INITIAL or \
            t == Lane.BRANCH or \
            Lane.isMerge(t)


class Lanes():

    def __init__(self):
        self.activeLane = 0
        self.types = []
        self.nextSha = []
        self.isBoundary = False
        self.node = 0
        self.node_l = 0
        self.node_r = 0

    def isEmpty(self):
        return not self.types

    def isFork(self, sha1):
        pos = self.findNextSha1(sha1, 0)
        isDiscontinuity = self.activeLane != pos
        if pos == -1:  # new branch case
            return False, isDiscontinuity

        isFork = self.findNextSha1(sha1, pos + 1) != -1
        return isFork, isDiscontinuity

    def isBranch(self):
        return self.types[self.activeLane] == Lane.BRANCH

    def isNode(self, t):
        return t == self.node or \
            t == self.node_r or \
            t == self.node_l

    def findNextSha1(self, next, pos):
        for i in range(pos, len(self.nextSha)):
            if self.nextSha[i] == next:
                return i

        return -1

    def init(self, sha1):
        self.clear()
        self.activeLane = 0
        self.setBoundary(False)
        self.add(Lane.BRANCH, sha1, self.activeLane)

    def clear(self):
        self.types.clear()
        self.nextSha.clear()

    def setBoundary(self, b):
        if b:
            self.node = Lane.BOUNDARY_C
            self.node_r = Lane.BOUNDARY_R
            self.node_l = Lane.BOUNDARY_L
            self.types[self.activeLane] = Lane.BOUNDARY
        else:
            self.node = Lane.MERGE_FORK
            self.node_r = Lane.MERGE_FORK_R
            self.node_l = Lane.MERGE_FORK_L

        self.isBoundary = b

    def findType(self, type, pos):
        for i in range(pos, len(self.types)):
            if self.types[i] == type:
                return i
        return -1

    def add(self, type, next, pos):
        if pos < len(self.types):
            pos = self.findType(Lane.EMPTY, pos)
            if pos != -1:
                self.types[pos] = type
                self.nextSha[pos] = next
                return pos

        self.types.append(type)
        self.nextSha.append(next)

        return len(self.types) - 1

    def changeActiveLane(self, sha1):
        t = self.types[self.activeLane]
        if t == Lane.INITIAL or Lane.isBoundary(t):
            self.types[self.activeLane] = Lane.EMPTY
        else:
            self.types[self.activeLane] = Lane.NOT_ACTIVE

        idx = self.findNextSha1(sha1, 0)
        if idx != -1:
            self.types[idx] = Lane.ACTIVE
        else:
            idx = self.add(Lane.BRANCH, sha1, self.activeLane)

        self.activeLane = idx

    def setFork(self, sha1):
        s = e = idx = self.findNextSha1(sha1, 0)
        while idx != -1:
            e = idx
            self.types[idx] = Lane.TAIL
            idx = self.findNextSha1(sha1, idx + 1)

        self.types[self.activeLane] = self.node
        if self.types[s] == self.node:
            self.types[s] = self.node_l

        if self.types[e] == self.node:
            self.types[e] = self.node_r

        if self.types[s] == Lane.TAIL:
            self.types[s] == Lane.TAIL_L

        if self.types[e] == Lane.TAIL:
            self.types[e] = Lane.TAIL_R

        for i in range(s + 1, e):
            if self.types[i] == Lane.NOT_ACTIVE:
                self.types[i] = Lane.CROSS
            elif self.types[i] == Lane.EMPTY:
                self.types[i] = Lane.CROSS_EMPTY

    def setMerge(self, parents):
        if self.isBoundary:
            return

        t = self.types[self.activeLane]
        wasFork = t == self.node
        wasForkL = t == self.node_l
        wasForkR = t == self.node_r

        self.types[self.activeLane] = self.node

        s = e = self.activeLane
        startJoinWasACross = False
        endJoinWasACross = False
        # skip first parent
        for i in range(1, len(parents)):
            idx = self.findNextSha1(parents[i], 0)
            if idx != -1:
                if idx > e:
                    e = idx
                    endJoinWasACross = self.types[idx] == Lane.CROSS
                if idx < s:
                    s = idx
                    startJoinWasACross = self.types[idx] == Lane.CROSS

                self.types[idx] = Lane.JOIN
            else:
                e = self.add(Lane.HEAD, parents[i], e + 1)

        if self.types[s] == self.node and not wasFork and not wasForkR:
            self.types[s] = self.node_l
        if self.types[e] == self.node and not wasFork and not wasForkL:
            self.types[e] = self.node_r

        if self.types[s] == Lane.JOIN and not startJoinWasACross:
            self.types[s] = Lane.JOIN_L
        if self.types[e] == Lane.JOIN and not endJoinWasACross:
            self.types[e] = Lane.JOIN_R

        if self.types[s] == Lane.HEAD:
            self.types[s] = Lane.HEAD_L
        if self.types[e] == Lane.HEAD:
            self.types[e] = Lane.HEAD_R

        for i in range(s + 1, e):
            if self.types[i] == Lane.NOT_ACTIVE:
                self.types[i] = Lane.CROSS
            elif self.types[i] == Lane.EMPTY:
                self.types[i] = Lane.CROSS_EMPTY
            elif self.types[i] == Lane.TAIL_R or \
                    self.types[i] == Lane.TAIL_L:
                self.types[i] = Lane.TAIL

    def setInitial(self):
        t = self.types[self.activeLane]
        # TODO: applied
        if not self.isNode(t):
            if self.isBoundary:
                self.types[self.activeLane] = Lane.BOUNDARY
            else:
                self.types[self.activeLane] = Lane.INITIAL

    def getLanes(self):
        return list(self.types)

    def nextParent(self, sha1):
        if self.isBoundary:
            self.nextSha[self.activeLane] = ""
        else:
            self.nextSha[self.activeLane] = sha1

    def afterMerge(self):
        if self.isBoundary:
            return

        for i in range(len(self.types)):
            t = self.types[i]
            if Lane.isHead(t) or Lane.isJoin(t) or t == Lane.CROSS:
                self.types[i] = Lane.NOT_ACTIVE
            elif t == Lane.CROSS_EMPTY:
                self.types[i] = Lane.EMPTY
            elif self.isNode(t):
                self.types[i] = Lane.ACTIVE

    def afterFork(self):
        for i in range(len(self.types)):
            t = self.types[i]
            if t == Lane.CROSS:
                self.types[i] = Lane.NOT_ACTIVE
            elif Lane.isTail(t) or t == Lane.CROSS_EMPTY:
                self.types[i] = Lane.EMPTY

            if not self.isBoundary and self.isNode(t):
                self.types[i] = Lane.ACTIVE

        while self.types[-1] == Lane.EMPTY:
            self.types.pop()
            self.nextSha.pop()

    def afterBranch(self):
        self.types[self.activeLane] = Lane.ACTIVE


class LogGraph(QWidget):

    def __init__(self, parent=None):
        super(LogGraph, self).__init__(parent)

        self.setFocusPolicy(Qt.NoFocus)
        self.setBackgroundRole(QPalette.Base)
        self.setAutoFillBackground(True)

        self._graphImage: QImage = None

    def render(self, graphImage):
        self._graphImage = graphImage
        self.update()

    def sizeHint(self):
        return QSize(25, 100)

    def paintEvent(self, event):
        if self._graphImage:
            painter = QPainter(self)
            painter.drawImage(0, 0, self._graphImage)


class LogView(QAbstractScrollArea, CommitSource):
    currentIndexChanged = Signal(int)
    findFinished = Signal(int)

    beginFetch = Signal()
    endFetch = Signal()

    def __init__(self, parent=None):
        QAbstractScrollArea.__init__(self, parent)
        CommitSource.__init__(self)

        self.setFocusPolicy(Qt.StrongFocus)
        self.setFrameStyle(QFrame.NoFrame)
        self.setMouseTracking(True)
        self.setViewportMargins(1, 3, 3, 3)

        self.data: List[Commit] = []
        self.fetcher = LogsFetcher(self)
        self.curIdx = -1
        self.hoverIdx = -1
        self.branchA = True
        self.curBranch = ""
        self.args = None
        self.preferSha1 = None
        self.delayVisible = False
        self.delayUpdateParents = False

        self.lineSpace = 8

        # commit history graphs
        self.graphs = {}
        self.lanes = Lanes()
        self.firstFreeLane = 0

        self.logGraph = None

        self.authorRe = re.compile("(.*) <.*>$")

        self._finder = DiffFinder(self, self)
        self.needUpdateFindResult = True

        self.highlightPattern = None
        self.marker = Marker()

        self.filterPath = None
        self.menu = None
        self._branchDir = None

        self._editable = True

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)

        # never show the horizontalScrollBar
        # since we can view the long content in diff view
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.fetcher.logsAvailable.connect(
            self.__onLogsAvailable)
        self.fetcher.fetchFinished.connect(
            self.__onFetchFinished)
        self.fetcher.localChangesAvailable.connect(
            self.__onLocalChangesAvailable)

        self.updateSettings()

        ApplicationBase.instance().settings().logViewFontChanged.connect(
            self.updateSettings)
        ApplicationBase.instance().settings().compositeModeChanged.connect(
            self.__onCompositeModeChanged)

        logWindow = self.logWindow()
        if logWindow:
            logWindow.submoduleAvailable.connect(self.__onSubmoduleAvailable)

        self._finder.resultAvailable.connect(
            self.__onFindResultAvailable)
        self._finder.findFinished.connect(
            self.__onFindFinished)

    def __ensureContextMenu(self):
        if self.menu:
            return

        self.menu = QMenu()

        self.acCopySummary = self.menu.addAction(
            self.tr("&Copy commit summary"),
            self.__onCopyCommitSummary)
        self.acCopyAbbrevCommit = self.menu.addAction(
            self.tr("Copy &abbrev commit"),
            self.__onCopyAbbrevCommit)
        self.acCopyToLog = self.menu.addAction(
            self.tr("Copy to conflict &log"),
            self.copyToLog)
        self.menu.addSeparator()

        self.menu.addAction(self.tr("&Mark this commit"),
                            self.__onMarkCommit)
        self.acMarkTo = self.menu.addAction(self.tr("Mark &to this commit"),
                                            self.__onMarkToCommit)
        self.acClearMarks = self.menu.addAction(self.tr("Clea&r Marks"),
                                                self.__onClearMarks)

        self.menu.addSeparator()
        self.acGenPatch = self.menu.addAction(
            self.tr("Generate &patch"),
            self.__onGeneratePatch)
        self.acGenDiff = self.menu.addAction(
            self.tr("Generate &diff"),
            self.__onGenerateDiff)

        if self._editable:
            self.menu.addSeparator()
            self.acRevert = self.menu.addAction(
                self.tr("Re&vert this commit"),
                self.__onRevertCommit)
            resetMenu = self.menu.addMenu(self.tr("Re&set to here"))
            resetMenu.addAction(
                self.tr("&Soft"),
                self.__onResetSoft)
            resetMenu.addAction(
                self.tr("&Mixed"),
                self.__onResetMixed)
            resetMenu.addAction(
                self.tr("&Hard"),
                self.__onResetHard)
            self.resetMenu = resetMenu

        self.menu.addSeparator()
        self.menu.addAction(self.tr("&Code Review"), self.__onCodeReview)

    def setBranchB(self):
        self.branchA = False

    @property
    def color(self):
        settings = ApplicationBase.instance().settings()
        if self.branchA:
            return settings.commitColorA().name()

        return settings.commitColorB().name()

    def showLogs(self, branch, branchDir, args=None):
        self.curBranch = branch
        self.args = args
        self._finder.reset()
        self._branchDir = branchDir

        submodules = []
        if ApplicationBase.instance().settings().isCompositeMode():
            submodules = self.submodules()
        self.fetcher.setSubmodules(submodules)

        self.fetcher.fetch(branch, args, branchDir=self._branchDir)
        self.beginFetch.emit()

    def clear(self):
        self.data.clear()
        self.curIdx = -1
        self.__resetGraphs()
        self.marker.clear()
        self.delayVisible = False
        self.delayUpdateParents = False
        self.clearFindData()
        self.updateGeometries()
        self.viewport().update()
        self.currentIndexChanged.emit(self.curIdx)
        self.cancelFindCommit()
        if self.logGraph:
            self.logGraph.render(None)

    def getCommit(self, index):
        if index < 0 or index >= len(self.data):
            return None
        return self.data[index]

    def isCurrentCommitted(self):
        if not self.data or self.curIdx == -1:
            return False

        return self.data[self.curIdx].sha1 not in [Git.LCC_SHA1, Git.LUC_SHA1]

    def getCount(self):
        return len(self.data)

    def currentIndex(self):
        return self.curIdx

    def ensureVisible(self):
        if self.curIdx == -1:
            return

        startLine = self.verticalScrollBar().value()
        endLineF = startLine + self.__linesPerPageF()

        if (self.curIdx < startLine) or (self.curIdx > int(endLineF)):
            self.verticalScrollBar().setValue(self.curIdx)
        elif self.curIdx == int(endLineF):
            # allow the last line not full visible
            if (endLineF - self.curIdx) < HALF_LINE_PERCENT:
                self.verticalScrollBar().setValue(startLine + 1)

    def setCurrentIndex(self, index):
        self.preferSha1 = None
        if index == self.curIdx:
            return

        self.curIdx = index
        if index >= 0 and index < len(self.data):
            self.ensureVisible()
            self.__ensureChildren(index)

        self.viewport().update()
        self.currentIndexChanged.emit(index)

    def switchToCommit(self, sha1, delay=False):
        # ignore if sha1 same as current's
        if self.curIdx != -1 and self.curIdx < len(self.data):
            commit = self.data[self.curIdx]
            if commit and commit.sha1.startswith(sha1):
                self.ensureVisible()
                return True

        index = self.findCommitIndex(sha1)
        if index != -1:
            self.setCurrentIndex(index)
        elif self.fetcher.isLoading() or delay:
            self.preferSha1 = sha1
            return True

        return index != -1

    def switchToNearCommit(self, sha1, goNext=True):
        self.curIdx = self.curIdx if self.curIdx >= 0 else 0
        index = self.findCommitIndex(sha1, self.curIdx, goNext)
        if index != -1:
            self.setCurrentIndex(index)
        return index != -1

    def findCommitIndex(self, sha1, begin=0, findNext=True):
        findRange = range(begin, len(self.data)) \
            if findNext else range(begin, -1, -1)
        for i in findRange:
            commit = self.data[i]
            if commit.sha1.startswith(sha1):
                return i

            for subCommit in commit.subCommits:
                if subCommit.sha1.startswith(sha1):
                    return i

        return -1

    def showContextMenu(self, pos):
        if self.curIdx == -1:
            return

        self.__ensureContextMenu()

        isCommitted = self.isCurrentCommitted()
        self.acCopySummary.setEnabled(isCommitted)
        self.acGenPatch.setEnabled(isCommitted)
        self.acCopyAbbrevCommit.setEnabled(isCommitted)

        logWindow = self.logWindow()
        w = logWindow.mergeWidget if logWindow else None
        visible = w is not None
        self.acCopyToLog.setVisible(visible)
        if visible:
            self.acCopyToLog.setEnabled(isCommitted and w.isResolving())

        if self._editable:
            enabled = isCommitted and not not self._branchDir
            self.acRevert.setEnabled(enabled)

            # to avoid bad reset on each repo
            if enabled and ApplicationBase.instance().settings().isCompositeMode():
                # disable only if have submodules
                enabled = not self.submodules()
            self.resetMenu.setEnabled(enabled)

        hasMark = self.marker.hasMark()
        self.acMarkTo.setVisible(hasMark)
        self.acClearMarks.setVisible(hasMark)

        globalPos = self.mapToGlobal(pos)
        self.menu.exec(globalPos)

    def updateSettings(self):
        settings = ApplicationBase.instance().settings()
        self.font = settings.logViewFont()

        self.lineHeight = QFontMetrics(self.font).height() + self.lineSpace

        self.updateGeometries()
        self.updateView()

    def updateView(self):
        return self.viewport().update()

    def __onCopyCommitSummary(self):
        if self.curIdx == -1:
            return
        commit = self.data[self.curIdx]
        if not commit:
            return

        repoDir = commitRepoDir(commit)
        commit = Git.commitSummary(commit.sha1, repoDir)
        if not commit:
            return

        clipboard = ApplicationBase.instance().clipboard()

        htmlText = '<html>\n'
        htmlText += '<head>\n'
        htmlText += '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>\n'
        htmlText += '</head>\n'
        htmlText += '<body>\n'
        htmlText += '<div>\n'
        htmlText += '<p style="margin:0pt">\n'
        htmlText += '<span style="font-size:10pt;color:{0}">'.format(
            self.color)
        htmlText += self.__sha1Url(commit["sha1"])
        htmlText += ' (&quot;'
        htmlText += self.__filterBug(commit["subject"])
        htmlText += '&quot;, ' + \
            self.__mailTo(commit["author"], commit["email"])
        htmlText += ', ' + commit["date"]
        htmlText += ')</span>'
        htmlText += '</p>\n'
        htmlText += '</div>\n'
        htmlText += '</body>\n'
        htmlText += '</html>\n'

        mimeData = QMimeData()
        mimeData.setHtml(htmlText)
        mimeData.setText('{0} ("{1}", {2}, {3})'.format(
            commit["sha1"],
            commit["subject"],
            commit["author"],
            commit["date"]))

        clipboard.setMimeData(mimeData)

    def __onCopyAbbrevCommit(self):
        if self.curIdx == -1:
            return
        commit = self.data[self.curIdx]
        if not commit:
            return

        mimeData = QMimeData()
        abbrev = Git.abbrevCommit(commit.sha1)
        mimeData.setText(abbrev)

        clipboard = ApplicationBase.instance().clipboard()
        clipboard.setMimeData(mimeData)

    def copyToLog(self):
        if self.curIdx == -1:
            return
        commit = self.data[self.curIdx]
        if not commit:
            return

        repoDir = commitRepoDir(commit)
        commit = Git.commitSummary(commit.sha1, repoDir)
        if not commit:
            return

        commit["branchA"] = self.branchA
        logWindow = self.logWindow()
        mergeWidget = logWindow.mergeWidget if logWindow else None
        ApplicationBase.instance().postEvent(mergeWidget, CopyConflictCommit(commit))

    def __onMarkCommit(self):
        assert self.curIdx >= 0

        begin = self.curIdx
        end = self.curIdx
        self.marker.mark(begin, end)
        # TODO: update marked lines only
        self.viewport().update()

    def __onMarkToCommit(self):
        assert self.curIdx >= 0

        begin = self.marker.begin()
        end = self.curIdx
        self.marker.mark(begin, end)
        # TODO: update marked lines only
        self.viewport().update()

    def __onClearMarks(self):
        self.marker.clear()
        # TODO: update marked lines only
        self.viewport().update()

    def __onGeneratePatch(self):
        if self.curIdx == -1:
            return
        commit = self.data[self.curIdx]
        if not commit:
            return

        f, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Patch"))
        if f:
            repoDir = commitRepoDir(commit)
            patch = Git.commitRawPatch(commit.sha1, repoDir)
            if patch is None:
                patch = b''

            for subCommit in commit.subCommits:
                repoDir = commitRepoDir(subCommit)
                subPatch = Git.commitRawPatch(subCommit.sha1, repoDir)
                if subPatch:
                    patch += b'\n' + subPatch

            if patch:
                with open(f, "wb+") as h:
                    h.write(patch)

    def __onGenerateDiff(self):
        if self.curIdx == -1:
            return
        commit = self.data[self.curIdx]
        if not commit:
            return

        f, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Diff"))
        if f:
            repoDir = commitRepoDir(commit)
            diff = Git.commitRawDiff(commit.sha1, repoDir=repoDir)
            if diff is None:
                diff = b''
            for subCommit in commit.subCommits:
                repoDir = commitRepoDir(subCommit)
                subDiff = Git.commitRawDiff(subCommit.sha1, repoDir=repoDir)
                if subDiff:
                    diff += b'\n' + subDiff

            if diff:
                with open(f, "wb+") as h:
                    h.write(diff)

    def __onRevertCommit(self):
        if self.curIdx == -1:
            return
        commit = self.data[self.curIdx]
        if not commit:
            return

        def _doRevert(sha1, repoDir):
            ret, error = Git.revertCommit(self.curBranch, sha1, repoDir)
            # ret == 1 with no error can happened but still reverted
            if ret != 0 and error:
                QMessageBox.critical(
                    self, self.window().windowTitle(),
                    error)
                return False
            return True

        repoDir = commitRepoDir(commit)
        if not _doRevert(commit.sha1, repoDir):
            return

        for subCommit in commit.subCommits:
            repoDir = commitRepoDir(subCommit)
            _doRevert(subCommit.sha1, repoDir)

        # FIXME: fetch the new one only?
        self.clear()
        self.showLogs(self.curBranch, self._branchDir, self.args)

    def __resetToCurCommit(self, method):
        if self.curIdx == -1:
            return
        commit = self.data[self.curIdx]
        if not commit:
            return

        ret, error = Git.resetCommitTo(self.curBranch, commit.sha1, method)
        if ret != 0:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                error)
        else:
            self.reloadLogs()

    def __onResetSoft(self):
        self.__resetToCurCommit("soft")

    def __onResetMixed(self):
        self.__resetToCurCommit("mixed")

    def __onResetHard(self):
        self.__resetToCurCommit("hard")

    def __onCodeReview(self):
        if self.curIdx == -1:
            return
        commit = self.data[self.curIdx]
        if not commit:
            return

        logWindow = self.logWindow()
        args = logWindow.getFilterArgs() if logWindow else []
        event = CodeReviewEvent(commit, args)
        ApplicationBase.instance().postEvent(ApplicationBase.instance(), event)

    def __onFindResultAvailable(self):
        if self.needUpdateFindResult:
            index = self._finder.nextResult()
            self.findFinished.emit(index)

            self.viewport().update()

    def __onFindFinished(self, state):
        self.findFinished.emit(state)

    def __onLogsAvailable(self, logs):
        self.data.extend(logs)

        if self.delayUpdateParents and len(self.data) > 2:
            if self.data[1].sha1 == Git.LCC_SHA1:
                self.data[1].parents = [self.data[2].sha1]
            elif self.data[0].sha1 in (Git.LUC_SHA1, Git.LCC_SHA1):
                self.data[0].parents = [self.data[1].sha1]

            self.__resetGraphs()
            self.viewport().update()
            self.delayUpdateParents = False

        if self.currentIndex() == -1:
            if self.preferSha1:
                begin = len(self.data) - len(logs)
                idx = self.findCommitIndex(self.preferSha1, begin)
                if idx != -1:
                    self.setCurrentIndex(idx)
                    # might not visible at the time
                    self.delayVisible = True
            else:
                self.setCurrentIndex(0)

        self.updateGeometries()

    def __onFetchFinished(self, exitCode):
        if self.delayVisible:
            self.ensureVisible()
            self.delayVisible = False
        elif self.curIdx == -1:
            self.setCurrentIndex(0)

        self.endFetch.emit()
        if exitCode != 0 and self.fetcher.errorData:
            QMessageBox.critical(self, self.window().windowTitle(),
                                 self.fetcher.errorData.decode("utf-8"))
        else:
            self.viewport().update()

    def __onLocalChangesAvailable(self, lccCommit: Commit, lucCommit: Commit):
        parent_sha1 = self.data[0].sha1 if self.data else None

        self.delayUpdateParents = False
        hasLCC = lccCommit.isValid()
        hasLUC = lucCommit.isValid()

        if hasLCC:
            lccCommit.comments = self.tr(
                "Local changes checked in to index but not committed")
            lccCommit.parents = [parent_sha1] if parent_sha1 else []
            lccCommit.children = [lucCommit] if hasLUC else []

            if len(self.data) > 0 and self.data[0].sha1 == Git.LCC_SHA1:
                self.data[0] = lccCommit
            elif len(self.data) > 1 and self.data[1].sha1 == Git.LCC_SHA1:
                self.data[1] = lccCommit
            else:
                self.data.insert(0, lccCommit)
            parent_sha1 = lccCommit.sha1
            self.delayUpdateParents = len(lccCommit.parents) == 0

            if not self.delayUpdateParents:
                if self.data[1].children is None:
                    self.data[1].children = []

                self.data[1].children.append(lccCommit)

            if self.curIdx > 0:
                self.curIdx += 1

        if hasLUC:
            lucCommit.comments = self.tr(
                "Local uncommitted changes, not checked in to index")
            lucCommit.parents = [parent_sha1] if parent_sha1 else []
            lucCommit.children = []

            if len(self.data) > 0 and self.data[0].sha1 == Git.LUC_SHA1:
                self.data[0] = lucCommit
            else:
                self.data.insert(0, lucCommit)
            self.delayUpdateParents = self.delayUpdateParents or len(
                lucCommit.parents) == 0

            if not self.delayUpdateParents and not hasLCC:
                if self.data[1].children is None:
                    self.data[1].children = []
                self.data[1].children.append(lucCommit)

            if self.curIdx > 0:
                self.curIdx += 1

        # FIXME: modified the graphs directly
        if self.graphs and (hasLUC or hasLCC) and not self.delayUpdateParents:
            self.__resetGraphs()
            self.viewport().update()

        if self.curIdx == 0 and (hasLUC or hasLCC):
            # force update the diff
            self.currentIndexChanged.emit(0)
            self.viewport().update()

    def __resetGraphs(self):
        self.graphs.clear()
        self.lanes = Lanes()
        self.firstFreeLane = 0

    def __sha1Url(self, sha1):
        sha1Url = ApplicationBase.instance().settings().commitUrl(
            ApplicationBase.instance().repoName())
        if not sha1Url:
            sha1Url = ApplicationBase.instance().settings().commitUrl(None)

        if not sha1Url:
            return sha1

        return '<a href="{0}{1}">{1}</a>'.format(sha1Url, sha1)

    def __filterBug(self, subject):
        text = htmlEscape(subject)

        sett = ApplicationBase.instance().settings()
        repoName = ApplicationBase.instance().repoName()

        def _toRe(pattern):
            if not pattern:
                return None

            if pattern[0] != '(' or pattern[-1] != ')':
                pattern = '(' + pattern + ')'
            return re.compile(pattern)

        def _replace(bugRe, url):
            if bugRe.groups == 1:
                return bugRe.sub('<a href="{0}\\1">\\1</a>'.format(
                    url), text)
            else:
                return bugRe.sub('<a href="{0}\\2">\\1</a>'.format(
                    url), text)

        def _toUrl(patterns):
            if not patterns:
                return None

            for pattern, url in patterns:
                if not pattern:
                    continue
                bugRe = _toRe(pattern)
                if bugRe:
                    newText = _replace(bugRe, url)
                    if newText != text:
                        return newText

            return None

        url = _toUrl(sett.bugPatterns(repoName))
        if not url and sett.fallbackGlobalLinks(repoName):
            url = _toUrl(sett.bugPatterns(None))

        return url or text

    def __mailTo(self, author, email):
        return '<a href="mailto:{0}">{1}</a>'.format(email, htmlEscape(author))

    def __linesPerPageF(self):
        h = self.viewport().height()
        return h / self.lineHeight

    def __linesPerPage(self):
        return int(self.__linesPerPageF())

    def __itemRect(self, index, needMargin = True):
        """@index the index of data"""

        # the row number in viewport
        row = (index - self.verticalScrollBar().value())

        offsetX = self.horizontalScrollBar().value()
        margin = self.lineSpace // 4 if needMargin else 0
        x = -offsetX
        y = row * self.lineHeight + margin
        w = self.viewport().width() - x
        h = self.lineHeight - margin

        rect = QRect(x, y, w, h)

        return rect

    def __drawTag(self, painter: QPainter, rect, color, text, bold=False, textColor=Qt.black):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, False)

        if bold:
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)

        flags = Qt.AlignLeft | Qt.AlignVCenter
        br = painter.boundingRect(rect, flags, text)
        br.adjust(0, -1, 4, 1)

        pen = QPen(ApplicationBase.instance().colorSchema().TagBorder)
        pen.setCosmetic(True)
        painter.setPen(pen)

        painter.fillRect(br, color)
        painter.drawRect(br)

        painter.setPen(textColor)
        painter.drawText(br, Qt.AlignCenter, text)

        painter.restore()
        rect.adjust(br.width(), 0, 0, 0)

    def __drawTriangleTag(self, painter: QPainter, rect: QRect, color, text, textColor=Qt.black):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        flags = Qt.AlignLeft | Qt.AlignVCenter
        br = painter.boundingRect(QRectF(rect), flags, text)
        br.adjust(0, -1, 4, 1)

        h = br.height()
        w = h / 2

        path = QPainterPath()
        path.moveTo(QPointF(br.x(), br.y() + h / 2))

        # move rect to right
        br.adjust(w, 0, w, 0)

        path.lineTo(br.topLeft())
        path.lineTo(br.topRight())
        path.lineTo(br.bottomRight())
        path.lineTo(br.bottomLeft())
        path.closeSubpath()

        painter.fillPath(path, color)
        painter.strokePath(path, QPen(
            ApplicationBase.instance().colorSchema().TagBorder))

        painter.setPen(textColor)
        painter.drawText(br, flags, text)

        painter.restore()
        rect.adjust(path.boundingRect().width(), 0, 0, 0)

    def __laneWidth(self):
        return int(self.lineHeight * 9 / 16)

    def __drawGraph(self, painter, graphPainter, rect, cid):
        commit = self.data[cid]
        if commit.sha1 not in self.graphs:
            self.__updateGraph(cid)

        lanes = self.graphs[commit.sha1]
        activeLane = 0
        for i in range(len(lanes)):
            if Lane.isActive(lanes[i]):
                activeLane = i
                break

        colorSchema = ApplicationBase.instance().colorSchema()
        totalColor = len(colorSchema.GraphColors)
        if commit.sha1 == Git.LUC_SHA1:
            activeColor = colorSchema.LucColor
        elif commit.sha1 == Git.LCC_SHA1:
            activeColor = colorSchema.LccColor
        else:
            activeColor = colorSchema.GraphColors[activeLane % totalColor]

        w = self.__laneWidth()
        isHead = (commit.sha1 == Git.REV_HEAD)
        firstCommit = (cid == 0)

        if graphPainter:
            maxW = graphPainter.device().width()
            x2 = 0

            graphPainter.save()
            graphPainter.translate(rect.topLeft())
            for i in range(len(lanes)):
                x1 = x2
                x2 += w

                lane = lanes[i]
                if lane == Lane.EMPTY:
                    continue

                if i == activeLane:
                    color = activeColor
                else:
                    color = colorSchema.GraphColors[i % totalColor]
                self.__drawGraphLane(graphPainter, lane, x1, x2,
                                     color, activeColor, isHead, firstCommit)

                if x2 > maxW:
                    break
            graphPainter.restore()

        # refs
        rc = QRect(rect)
        rc.moveTo(0, 0)
        preL = rc.left()

        painter.save()
        painter.translate(rect.topLeft())
        painter.setRenderHints(QPainter.Antialiasing)
        self.__drawGraphRef(painter, rc, commit)

        painter.restore()
        offset = rc.left() - preL
        if offset != 0:  # have refs
            # spaces after refs
            offset += int(w / 3)
            rect.adjust(offset, 0, 0, 0)

    def __drawGraphLane(self, painter: QPainter, lane, x1, x2, color, activeColor, isHead, firstCommit):
        h = int(self.lineHeight / 2) + self.lineSpace // 4
        m = int((x1 + x2) / 2)
        r = int((x2 - x1) * 0.35)
        d = int(2 * r)

        # points
        # TL(m-r, h-r), TR(m+r, h-r)
        ###########
        #         #
        #    #    #  center (m, h)
        #         #
        ###########
        # BL(m, h+r), BR(m+r, h+r)

        borderColor = ApplicationBase.instance().colorSchema().GraphBorder
        painter.save()
        lanePen = QPen(borderColor, 2)

        # arc
        if lane == Lane.JOIN or \
           lane == Lane.JOIN_R or \
           lane == Lane.HEAD or \
           lane == Lane.HEAD_R:
            gradient = QConicalGradient(x1, 2 * h, 225)
            gradient.setColorAt(0.375, color)
            gradient.setColorAt(0.625, activeColor)

            lanePen.setBrush(gradient)
            painter.setPen(lanePen)
            painter.drawArc(m, h, 2 * (x1 - m), 2 * h, 0 * 16, 90 * 16)

        elif lane == Lane.JOIN_L:
            gradient = QConicalGradient(x2, 2 * h, 315)
            gradient.setColorAt(0.375, activeColor)
            gradient.setColorAt(0.625, color)

            lanePen.setBrush(gradient)
            painter.setPen(lanePen)
            painter.drawArc(m, h, 2 * (x2 - m), 2 * h, 90 * 16, 90 * 16)

        elif lane == Lane.TAIL or \
                lane == Lane.TAIL_R:
            gradient = QConicalGradient(x1, 0, 135)
            gradient.setColorAt(0.375, activeColor)
            gradient.setColorAt(0.625, color)

            lanePen.setBrush(gradient)
            painter.setPen(lanePen)
            painter.drawArc(m, h, 2 * (x1 - m), 2 * -h, 270 * 16, 90 * 16)

        lanePen.setColor(color)
        painter.setPen(lanePen)

        # vertical line
        if lane == Lane.ACTIVE or \
                lane == Lane.NOT_ACTIVE or \
                lane == Lane.MERGE_FORK or \
                lane == Lane.MERGE_FORK_R or \
                lane == Lane.MERGE_FORK_L or \
                lane == Lane.CROSS or \
                Lane.isJoin(lane):
            if firstCommit:
                painter.drawLine(m, h, m, 2 * h)
            else:
                painter.drawLine(m, 0, m, 2 * h)

        elif lane == Lane.HEAD_L or \
                lane == Lane.BRANCH:
            painter.drawLine(m, h, m, 2 * h)

        elif lane == Lane.TAIL_L or \
                lane == Lane.INITIAL or \
                Lane.isBoundary(lane):
            painter.drawLine(m, 0, m, h)

        lanePen.setColor(activeColor)
        painter.setPen(lanePen)

        # horizontal line
        if lane == Lane.MERGE_FORK or \
                lane == Lane.JOIN or \
                lane == Lane.HEAD or \
                lane == Lane.TAIL or \
                lane == Lane.CROSS or \
                lane == Lane.CROSS_EMPTY or \
                lane == Lane.BOUNDARY_C:
            painter.drawLine(x1, h, x2, h)

        elif lane == Lane.MERGE_FORK_R or \
                lane == Lane.BOUNDARY_R:
            painter.drawLine(x1, h, m, h)

        elif lane == Lane.MERGE_FORK_L or \
                lane == Lane.HEAD_L or \
                lane == Lane.TAIL_L or \
                lane == Lane.BOUNDARY_L:
            painter.drawLine(m, h, x2, h)

        # circle
        if isHead:
            color = Qt.yellow
        if lane == Lane.ACTIVE or \
                lane == Lane.INITIAL or \
                lane == Lane.BRANCH:
            painter.setPen(borderColor)
            painter.setBrush(color)
            painter.drawEllipse(m - r, h - r, d, d)

        elif lane == Lane.MERGE_FORK or \
                lane == Lane.MERGE_FORK_R or \
                lane == Lane.MERGE_FORK_L:
            painter.setPen(borderColor)
            painter.setBrush(color)
            painter.drawRect(m - r, h - r, d, d)

        elif lane == Lane.UNAPPLIED:
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.red)
            painter.drawRect(m - r, h - 1, d, 2)

        elif lane == Lane.APPLIED:
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.darkGreen)
            painter.drawRect(m - r, h - 1, d, 2)
            painter.drawRect(m - 1, h - r, 2, d)

        elif lane == Lane.BOUNDARY:
            painter.setPen(borderColor)
            painter.setBrush(painter.background())
            painter.drawEllipse(m - r, h - r, d, d)

        elif lane == Lane.BOUNDARY_C or \
                lane == Lane.BOUNDARY_R or \
                lane == Lane.BOUNDARY_L:
            painter.setPen(borderColor)
            painter.setBrush(painter.background())
            painter.drawRect(m - r, h - r, d, d)

        painter.restore()

    def __drawGraphRef(self, painter, rc, commit):
        if not commit.sha1 in Git.REF_MAP:
            return

        refs: List[Ref] = Git.REF_MAP[commit.sha1]
        painter.save()

        isHead = commit.sha1 == Git.REV_HEAD
        maxWidth = rc.width() * 2 / 3

        for ref in refs:
            # tag
            bgColor = ApplicationBase.instance(
            ).colorSchema().TagColorsBg[ref.type]
            fgColor = ApplicationBase.instance(
            ).colorSchema().TagColorsFg[ref.type]

            br = painter.boundingRect(
                rc, Qt.AlignLeft | Qt.AlignVCenter, ref.name)
            if rc.width() - br.width() < maxWidth:
                self.__drawTag(painter, rc, bgColor, "...", False, fgColor)
                break
            elif ref.type == Ref.TAG:
                self.__drawTriangleTag(painter, rc, bgColor, ref.name, fgColor)
            else:
                bold = (ref.type == Ref.HEAD and isHead)
                self.__drawTag(painter, rc, bgColor, ref.name, bold, fgColor)

        painter.restore()

    def __updateGraph(self, cid):
        for i in range(self.firstFreeLane, len(self.data)):
            commit = self.data[i]
            if not commit.sha1 in self.graphs:
                self.__updateLanes(commit, self.lanes)

            if i == cid:
                break
        self.firstFreeLane = i + 1

    def __updateLanes(self, commit, lanes):
        if lanes.isEmpty():
            lanes.init(commit.sha1)

        isFork, isDiscontinuity = lanes.isFork(commit.sha1)
        isMerge = (len(commit.parents) > 1)
        isInitial = (not commit.parents)

        if isDiscontinuity:
            lanes.changeActiveLane(commit.sha1)

        lanes.setBoundary(False)  # TODO
        if isFork:
            lanes.setFork(commit.sha1)
        if isMerge:
            lanes.setMerge(commit.parents)
        if isInitial:
            lanes.setInitial()

        l = lanes.getLanes()
        self.graphs[commit.sha1] = l

        if isInitial:
            nextSha1 = ""
        else:
            nextSha1 = commit.parents[0]

        lanes.nextParent(nextSha1)

        # TODO: applied
        if isMerge:
            lanes.afterMerge()
        if isFork:
            lanes.afterFork()
        if lanes.isBranch():
            lanes.afterBranch()

    def __ensureChildren(self, index):
        commit = self.data[index]
        if commit.children != None:
            return

        commit.children = []
        for i in range(index - 1, -1, -1):
            child = self.data[i]
            if commit.sha1 in child.parents:
                commit.children.append(child)

    def invalidateItem(self, index):
        rect = self.__itemRect(index, False)
        # update if visible in the viewport
        if rect.y() >= 0:
            self.viewport().update(rect)

    def updateGeometries(self):
        hScrollBar = self.horizontalScrollBar()
        vScrollBar = self.verticalScrollBar()

        if not self.data:
            hScrollBar.setRange(0, 0)
            vScrollBar.setRange(0, 0)
            return

        linesPerPage = self.__linesPerPage()
        totalLines = len(self.data)

        vScrollBar.setRange(0, totalLines - linesPerPage)
        vScrollBar.setPageStep(linesPerPage)

    def findCommitAsync(self, findParam: FindParameter):
        # cancel the previous one if find changed
        needRun = False
        if self._finder.updateParameters(findParam, self.filterPath, self.fetcher._submodules):
            self.cancelFindCommit()
            needRun = True

        if not findParam.pattern:
            return False

        result = self._finder.nextResult()
        # found one or no more results
        if result != FIND_NOTFOUND or (not self._finder.isRunning() and not needRun):
            self.findFinished.emit(result)
            return False

        self.needUpdateFindResult = True

        # start to find if not running
        if needRun:
            return self._finder.findAsync()

        return True

    def findCommitSync(self, findPattern, findRange, findField):
        # only use for finding in comments, as it should pretty fast
        assert findField == FindField.Comments

        def findInCommit(commit):
            if findPattern.search(commit.comments):
                return True

            if findPattern.search(commit.author):
                return True

            if findPattern.search(commit.committer):
                return True

            if findPattern.search(commit.sha1):
                return True

            if findPattern.search(commit.authorDate):
                return True

            if findPattern.search(commit.committerDate):
                return True

            for p in commit.parents:
                if findPattern.search(p):
                    return True

            return False

        result = -1
        total = abs(findRange.stop - findRange.start)

        for i in findRange:
            if findInCommit(self.data[i]):
                result = i
                break

        return result

    def cancelFindCommit(self, forced=True):
        self.needUpdateFindResult = False

        # only terminate when forced
        # otherwise still load at background
        if self._finder.isRunning() and forced:
            self._finder.cancel()
            return True

        if self._finder.isRunning():
            self.findFinished.emit(FIND_CANCELED)

        return False

    def highlightKeyword(self, pattern):
        self.highlightPattern = pattern
        self.viewport().update()

    def clearFindData(self):
        self._finder.clearResult()

    def setFilterPath(self, path):
        self.filterPath = path

    def setLogGraph(self, logGraph):
        self.logGraph = logGraph

    def firstVisibleLine(self):
        return self.verticalScrollBar().value()

    def lineForPos(self, pos):
        if not self.data:
            return -1

        y = max(0, pos.y())
        n = int(y / self.lineHeight)
        n += self.firstVisibleLine()

        if n >= len(self.data):
            n = len(self.data) - 1

        return n

    def resizeEvent(self, event):
        super(LogView, self).resizeEvent(event)

        self.updateGeometries()

    def paintEvent(self, event):
        if not self.data:
            return

        painter = QPainter(self.viewport())
        painter.setClipRect(event.rect())

        eventRect = event.rect()

        if eventRect.isValid():
            startLine = self.lineForPos(eventRect.topLeft())
            endLine = self.lineForPos(eventRect.bottomRight()) + 1
        else:
            startLine = self.firstVisibleLine()
            endLine = startLine + self.__linesPerPage() + 1
            endLine = min(len(self.data), endLine)

        palette = self.palette()

        graphPainter = None
        graphImage = None
        if self.logGraph and not self.logGraph.size().isEmpty() and \
                eventRect.height() == self.viewport().height():
            ratio = painter.device().devicePixelRatioF()
            graphImage = QImage(self.logGraph.size() * ratio,
                                QImage.Format_ARGB32_Premultiplied)
            graphImage.setDevicePixelRatio(ratio)
            graphImage.fill(self.logGraph.palette().color(QPalette.Base))
            graphPainter = QPainter(graphImage)
            graphPainter.setRenderHints(QPainter.Antialiasing)

        isFullMessage = ApplicationBase.instance().settings().isFullCommitMessage()

        def makeMessage(commit):
            if isFullMessage:
                return commit.comments.replace('\n', ' ')
            return commit.comments.split('\n')[0]

        colorSchema = ApplicationBase.instance().colorSchema()

        painter.setFont(self.font)
        flags = Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine
        for i in range(startLine, endLine):
            rect = self.__itemRect(i)
            rect.adjust(2, 0, 0, 0)

            commit = self.data[i]

            # sub-repo name
            needMargin = False
            if commit.repoDir:
                text = makeRepoName(commit.repoDir)
                color = colorSchema.RepoTagBg
                textColor = colorSchema.RepoTagFg
                self.__drawTag(painter, rect, color, text, textColor=textColor)
                for subCommit in commit.subCommits:
                    text = makeRepoName(subCommit.repoDir)
                    self.__drawTag(painter, rect, color,
                                   text, textColor=textColor)
                needMargin = True
            else:
                self.__drawGraph(painter, graphPainter, rect, i)

            if not commit.sha1 in [Git.LCC_SHA1, Git.LUC_SHA1]:
                # author
                text = self.authorRe.sub("\\1", commit.author)
                color = colorSchema.AuthorTagBg
                self.__drawTag(painter, rect, color, text, textColor=colorSchema.AuthorTagFg)

                # date
                text = commit.authorDate.split(' ')[0]
                color = colorSchema.DateTagBg
                self.__drawTag(painter, rect, color, text, textColor=colorSchema.DateTagFg)
                needMargin = True

            if needMargin:
                rect.adjust(4, 0, 0, 0)

            # marker
            self.marker.draw(i, painter, rect)

            # subject
            painter.save()
            if i == self.curIdx:
                painter.fillRect(rect, colorSchema.SelectedItemBg)
                if self.hasFocus():
                    pen = QPen(colorSchema.FocusItemBorder)
                    pen.setCosmetic(True)
                    painter.setPen(pen)
                    borderRect = QRectF(rect)
                    borderRect.adjust(0, 0, -0.5, -0.5)
                    painter.drawRect(borderRect)
                painter.setPen(colorSchema.SelectedItemFg)
            elif i == self.hoverIdx:
                painter.fillRect(rect, colorSchema.HoverItemBg)
            else:
                painter.setPen(palette.color(QPalette.WindowText))

            content = makeMessage(commit)

            rect.adjust(4, 0, 0, 0)

            # bold find result
            # it seems that *in* already fast, so no bsearch
            if i in self._finder.findResult:
                font = painter.font()
                font.setBold(True)
                painter.setFont(font)

            if self.highlightPattern:
                matchs = self.highlightPattern.finditer(content)
                start = 0
                oldPen = painter.pen()
                for m in matchs:
                    if m.start() > start:
                        br = painter.drawText(
                            rect, flags, content[start:m.start()])
                        rect.adjust(br.width(), 0, 0, 0)

                    text = content[m.start():m.end()]
                    if i == self.curIdx:
                        painter.setPen(colorSchema.HighlightWordSelectedFg)
                    else:
                        br = painter.boundingRect(rect, flags, text)
                        painter.fillRect(br, colorSchema.HighlightWordBg)
                    br = painter.drawText(rect, flags, text)
                    rect.adjust(br.width(), 0, 0, 0)
                    start = m.end()
                    painter.setPen(oldPen)

                if start < len(content):
                    painter.drawText(rect, flags, content[start:])
            else:
                painter.drawText(rect, flags, content)
            painter.restore()

        if graphImage:
            del graphPainter
            self.logGraph.render(graphImage)

    def mousePressEvent(self, event: QMouseEvent):
        if not self.data:
            return

        index = self.lineForPos(event.position())

        mod = ApplicationBase.instance().keyboardModifiers()
        # no OR combination
        if mod == Qt.ShiftModifier:
            self.marker.mark(self.curIdx, index)
            self.viewport().update()
        else:
            self.setCurrentIndex(index)

    def mouseMoveEvent(self, event: QMouseEvent):
        self._updateHover(event.position())

    def wheelEvent(self, event):
        super().wheelEvent(event)
        pos = self.mapFromGlobal(QCursor.pos())
        self._updateHover(pos)

    def _updateHover(self, pos):
        index = self.lineForPos(pos)
        if index == -1:
            return

        if index == self.hoverIdx:
            return

        if self.hoverIdx != -1:
            self.invalidateItem(self.hoverIdx)

        self.hoverIdx = index
        self.invalidateItem(self.hoverIdx)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            if self.curIdx > 0:
                startLine = self.verticalScrollBar().value()
                self.curIdx -= 1
                self.__ensureChildren(self.curIdx)
                if self.curIdx >= startLine:
                    self.invalidateItem(self.curIdx + 1)
                    self.invalidateItem(self.curIdx)
                else:
                    self.verticalScrollBar().setValue(self.curIdx)

                self.currentIndexChanged.emit(self.curIdx)
        elif event.key() == Qt.Key_Down:
            if self.curIdx + 1 < len(self.data):
                endLineF = self.verticalScrollBar().value() + self.__linesPerPageF()
                self.curIdx += 1
                self.__ensureChildren(self.curIdx)
                if self.curIdx < int(endLineF) or \
                        (self.curIdx == int(endLineF)
                         and (endLineF - self.curIdx >= HALF_LINE_PERCENT)):
                    self.invalidateItem(self.curIdx - 1)
                    self.invalidateItem(self.curIdx)
                else:
                    v = self.verticalScrollBar().value()
                    self.verticalScrollBar().setValue(v + 1)

                self.currentIndexChanged.emit(self.curIdx)
        elif event.key() == Qt.Key_Home:
            self.verticalScrollBar().triggerAction(
                QScrollBar.SliderToMinimum)
        elif event.key() == Qt.Key_End:
            self.verticalScrollBar().triggerAction(
                QScrollBar.SliderToMaximum)
        else:
            super(LogView, self).keyPressEvent(event)

    def focusInEvent(self, event):
        self.invalidateItem(self.curIdx)

    def focusOutEvent(self, event):
        self.invalidateItem(self.curIdx)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.hoverIdx != -1 and self.hoverIdx != self.curIdx:
            self.invalidateItem(self.hoverIdx)
        self.hoverIdx = -1

    def copy(self):
        self.__onCopyCommitSummary()

    def queryClose(self):
        self.fetcher.cancel(True)
        self._finder.cancel()
        self.cancelFindCommit()

    def __onCompositeModeChanged(self):
        submodules = self.submodules()
        if not submodules:
            return

        self.clear()
        self._branchDir = Git.branchDir(self.curBranch)
        self.showLogs(self.curBranch, self._branchDir, self.args)

    def __onSubmoduleAvailable(self, isCache):
        # ignore cache, we will reload in later
        if isCache:
            return

        if ApplicationBase.instance().settings().isCompositeMode():
            self.__onCompositeModeChanged()

    def reloadLogs(self):
        self.clear()
        self.showLogs(self.curBranch, self._branchDir, self.args)

    def logWindow(self):
        return ApplicationBase.instance().getWindow(WindowType.LogWindow, False)
    
    def submodules(self):
        window = self.logWindow()
        return window.submodules() if window else []

    def setEditable(self, editable: bool):
        self._editable = editable
