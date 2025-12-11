# -*- coding: utf-8 -*-

import json
import os
import re
import tempfile
from typing import List

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEventLoop,
    QMimeData,
    QPointF,
    QProcess,
    QProcessEnvironment,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QConicalGradient,
    QCursor,
    QDrag,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QCheckBox,
    QFileDialog,
    QFrame,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QScrollBar,
    QWidget,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.changeauthordialog import ChangeAuthorDialog
from qgitc.commitsource import CommitSource
from qgitc.common import *
from qgitc.difffinder import DiffFinder
from qgitc.events import CodeReviewEvent, CopyConflictCommit
from qgitc.gitutils import *
from qgitc.logsfetcher import LogsFetcher
from qgitc.windowtype import WindowType

HALF_LINE_PERCENT = 0.76


class MarkType:
    """Types of marks that can be applied to commits"""
    NORMAL = 0      # Regular selection mark
    PICKED = 1      # Successfully cherry-picked
    FAILED = 2      # Cherry-pick failed


class MarkRange:
    """Represents a range of marked commits with a specific type"""

    def __init__(self, begin, end, markType=MarkType.NORMAL):
        self.begin = min(begin, end)
        self.end = max(begin, end)
        self.markType = markType


class Marker():
    CHAR_MARK = chr(0x2713)
    CHAR_PICKED = chr(0x2192)  # Right arrow
    CHAR_FAILED = chr(0x2716)  # Heavy multiplication X

    def __init__(self, changedCallback=None):
        self._ranges: List[MarkRange] = []
        self._sorted = True  # Track if ranges are sorted
        self._changedCallback = changedCallback

    def mark(self, begin, end, markType=MarkType.NORMAL):
        """Mark a range of commits with a specific type"""
        markRange = MarkRange(begin, end, markType)
        # Remove any overlapping ranges first
        self._ranges = [
            r for r in self._ranges if not self._overlaps(r, markRange)]
        self._ranges.append(markRange)
        self._sorted = False
        if self._changedCallback:
            self._changedCallback()

    def _overlaps(self, r1: MarkRange, r2: MarkRange):
        """Check if two ranges overlap"""
        return not (r1.end < r2.begin or r2.end < r1.begin)

    def _ensureSorted(self):
        """Ensure ranges are sorted by begin index for efficient lookup"""
        if not self._sorted:
            self._ranges.sort(key=lambda r: r.begin)
            self._sorted = True

    def clear(self):
        """Clear all marks"""
        if self._ranges:  # Only notify if there were marks
            self._ranges.clear()
            self._sorted = True
            if self._changedCallback:
                self._changedCallback()

    def clearType(self, markType):
        """Clear all marks of a specific type"""
        oldCount = len(self._ranges)
        self._ranges = [r for r in self._ranges if r.markType != markType]
        # Sorting state remains unchanged
        if oldCount != len(self._ranges) and self._changedCallback:
            self._changedCallback()

    def hasMark(self):
        """Check if there are any marks"""
        return len(self._ranges) > 0

    def begin(self):
        """Get the beginning of the first range (for compatibility)"""
        if not self._ranges:
            return -1
        return min(r.begin for r in self._ranges)

    def end(self):
        """Get the end of the first range (for compatibility)"""
        if not self._ranges:
            return -1
        return max(r.end for r in self._ranges)

    def isMarked(self, index):
        """Check if an index is marked with any type"""
        self._ensureSorted()
        # Binary search for efficiency with many ranges
        left, right = 0, len(self._ranges) - 1
        while left <= right:
            mid = (left + right) // 2
            r = self._ranges[mid]
            if r.begin <= index <= r.end:
                return True
            elif index < r.begin:
                right = mid - 1
            else:
                left = mid + 1
        return False

    def getMarkType(self, index):
        """Get the mark type for an index, or None if not marked"""
        self._ensureSorted()
        # Binary search for efficiency
        left, right = 0, len(self._ranges) - 1
        while left <= right:
            mid = (left + right) // 2
            r = self._ranges[mid]
            if r.begin <= index <= r.end:
                return r.markType
            elif index < r.begin:
                right = mid - 1
            else:
                left = mid + 1
        return None

    def toggle(self, index, markType=MarkType.NORMAL):
        """Toggle mark at a single index. Returns True if now marked, False if unmarked."""
        if self.isMarked(index):
            self.unmark(index)
            return False
        else:
            self.mark(index, index, markType)
            return True

    def unmark(self, begin, end=None):
        """
        Efficiently unmark a single index or range without rebuilding everything.
        If end is None, unmaks only the single index at begin.
        """
        if end is None:
            end = begin

        # Normalize range
        if begin > end:
            begin, end = end, begin

        newRanges = []
        for r in self._ranges:
            # No overlap - keep the range as is
            if r.end < begin or r.begin > end:
                newRanges.append(r)
            else:
                # There's overlap - we may need to split the range
                # Case 1: Range before the unmark region
                if r.begin < begin:
                    newRanges.append(MarkRange(r.begin, begin - 1, r.markType))

                # Case 2: Range after the unmark region
                if r.end > end:
                    newRanges.append(MarkRange(end + 1, r.end, r.markType))

        self._ranges = newRanges
        self._sorted = False
        if self._changedCallback:
            self._changedCallback()

    def countMarked(self):
        """Efficiently count total number of marked commits"""
        return sum(r.end - r.begin + 1 for r in self._ranges)

    def getMarkedIndices(self):
        """Get a sorted list of all marked indices (for iteration)"""
        self._ensureSorted()
        indices = []
        for r in self._ranges:
            indices.extend(range(r.begin, r.end + 1))
        return indices

    def draw(self, index, painter: QPainter, rect: QRect):
        markType = self.getMarkType(index)
        if markType is None:
            return

        painter.save()

        # Choose character and color based on mark type
        if markType == MarkType.PICKED:
            char = Marker.CHAR_PICKED
            color = ApplicationBase.instance().colorSchema().ResolvedFg
        elif markType == MarkType.FAILED:
            char = Marker.CHAR_FAILED
            color = ApplicationBase.instance().colorSchema().ConflictFg
        else:  # MarkType.NORMAL
            char = Marker.CHAR_MARK
            color = ApplicationBase.instance().colorSchema().Mark

        painter.setPen(QPen(color))
        br = painter.drawText(rect, Qt.AlignVCenter, char)
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
    markerChanged = Signal()

    beginFetch = Signal()
    endFetch = Signal()

    def __init__(self, parent=None):
        QAbstractScrollArea.__init__(self, parent)
        CommitSource.__init__(self)

        self.setFocusPolicy(Qt.StrongFocus)
        self.setFrameStyle(QFrame.NoFrame)
        self.setMouseTracking(True)
        self.setViewportMargins(1, 3, 3, 3)

        # Enable drag and drop
        self.setAcceptDrops(True)

        self.data: List[Commit] = []
        self.fetcher = LogsFetcher(self)
        self.curIdx = -1
        self.hoverIdx = -1
        self.selectedIndices = set()  # Track multiple selected items
        self.selectionAnchor = -1  # Track where shift-selection started
        self.branchA = True
        self.curBranch = ""
        self.args = None
        self.preferSha1 = None
        self.delayVisible = False
        self.delayUpdateParents = False

        # Drag and drop state
        self._dragStartPos = None
        self._dropIndicatorLine = -1
        self._dropIndicatorAlpha = 0.0  # For animation
        self._dropIndicatorAnimation = None
        # Vertical offset animation for items (0.0 to 1.0)
        self._dropIndicatorOffset = 0.0
        self._dropIndicatorOffsetAnimation = None

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
        self.marker = Marker(changedCallback=lambda: self.markerChanged.emit())

        self.filterPath = None
        self.menu = None
        self._branchDir = None

        self._editable = True
        self._showNoDataTips = True
        self._selectOnFetch = True
        self._standalone = True

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
        self.fetcher.fetchTooSlow.connect(
            self.__onFetchTooSlow)

        self.updateSettings()

        app = ApplicationBase.instance()
        app.settings().logViewFontChanged.connect(self.updateSettings)
        app.settings().compositeModeChanged.connect(self.__onCompositeModeChanged)

        logWindow = self.logWindow()
        if logWindow:
            app.submoduleAvailable.connect(self.__onSubmoduleAvailable)

        self._finder.resultAvailable.connect(
            self.__onFindResultAvailable)
        self._finder.findFinished.connect(
            self.__onFindFinished)

    def _getDropIndicatorAlpha(self):
        return self._dropIndicatorAlpha

    def _setDropIndicatorAlpha(self, value):
        self._dropIndicatorAlpha = value
        self.viewport().update()

    dropIndicatorAlpha = Property(
        float, _getDropIndicatorAlpha, _setDropIndicatorAlpha)

    def _getDropIndicatorOffset(self):
        return self._dropIndicatorOffset

    def _setDropIndicatorOffset(self, value):
        self._dropIndicatorOffset = value
        self.viewport().update()

    dropIndicatorOffset = Property(
        float, _getDropIndicatorOffset, _setDropIndicatorOffset)

    def _startDropIndicatorAnimation(self):
        """Start the drop indicator animation"""
        # Stop any existing animation
        self._stopDropIndicatorAnimation()

        # Create fade-in animation for alpha (always from current value)
        self._dropIndicatorAnimation = QPropertyAnimation(
            self, b"dropIndicatorAlpha")
        self._dropIndicatorAnimation.setDuration(200)  # 200ms
        self._dropIndicatorAnimation.setStartValue(self._dropIndicatorAlpha)
        self._dropIndicatorAnimation.setEndValue(1.0)
        self._dropIndicatorAnimation.setEasingCurve(QEasingCurve.OutCubic)
        self._dropIndicatorAnimation.start()

        # Create offset animation to move items down (from current value)
        self._dropIndicatorOffsetAnimation = QPropertyAnimation(
            self, b"dropIndicatorOffset")
        self._dropIndicatorOffsetAnimation.setDuration(200)  # 200ms
        self._dropIndicatorOffsetAnimation.setStartValue(
            self._dropIndicatorOffset)
        self._dropIndicatorOffsetAnimation.setEndValue(1.0)
        self._dropIndicatorOffsetAnimation.setEasingCurve(
            QEasingCurve.OutCubic)
        self._dropIndicatorOffsetAnimation.start()

    def _stopDropIndicatorAnimation(self):
        """Stop the drop indicator animation"""
        if self._dropIndicatorAnimation:
            self._dropIndicatorAnimation.stop()
            self._dropIndicatorAnimation = None

        if self._dropIndicatorOffsetAnimation:
            self._dropIndicatorOffsetAnimation.stop()
            self._dropIndicatorOffsetAnimation = None

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

        self.menu.addAction(self.tr("&Toggle marker"),
                            self.__onMarkCommit)
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
                self.tr("Re&vert commit(s)"),
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
            self.acChangeAuthor = self.menu.addAction(
                self.tr("Change &Author..."),
                self.__onChangeAuthor)

        self.menu.addSeparator()
        self.acCodeReview = self.menu.addAction(
            self.tr("&Code Review"), self.__onCodeReview)

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
        app = ApplicationBase.instance()
        if self._standalone and app.settings().isCompositeMode():
            submodules = app.submodules
        self.fetcher.setSubmodules(submodules)

        self.fetcher.fetch(branch, args, branchDir=self._branchDir)
        self.beginFetch.emit()
        self.viewport().update()

    def clear(self):
        self.data.clear()
        self.curIdx = -1
        self.selectedIndices.clear()
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

    def getSelectedIndices(self):
        """Get all selected indices as a sorted list"""
        return sorted(self.selectedIndices)

    def getSelectedCommits(self) -> List[Commit]:
        """Get all selected commits"""
        indices = self.getSelectedIndices()
        return [self.data[i] for i in indices if i < len(self.data)]

    def ensureVisible(self, index: int):
        if index == -1:
            return

        startLine = self.verticalScrollBar().value()
        endLineF = startLine + self.__linesPerPageF()

        if (index < startLine) or (index > int(endLineF)):
            self.verticalScrollBar().setValue(index)
        elif index == int(endLineF):
            # allow the last line not full visible
            if (endLineF - index) < HALF_LINE_PERCENT:
                self.verticalScrollBar().setValue(startLine + 1)

    def setCurrentIndex(self, index, clearSelection=True):
        self.preferSha1 = None
        if index == self.curIdx and not clearSelection:
            return

        self.curIdx = index

        # Update selection based on clearSelection flag
        if clearSelection:
            self.selectedIndices.clear()
            self.selectedIndices.add(index)
            self.selectionAnchor = -1  # Reset anchor on new selection

        if index >= 0 and index < len(self.data):
            self.ensureVisible(self.curIdx)
            self.__ensureChildren(index)

        self.viewport().update()
        self.currentIndexChanged.emit(index)

    def switchToCommit(self, sha1, delay=False):
        # ignore if sha1 same as current's
        if self.curIdx != -1 and self.curIdx < len(self.data):
            commit = self.data[self.curIdx]
            if commit and commit.sha1.startswith(sha1):
                self.ensureVisible(self.curIdx)
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

        # Check if multiple items are selected
        indices = self.getSelectedIndices()
        multipleSelected = len(indices) > 1

        # Check if all selected commits are committed (not local changes)
        allCommitted = True
        if multipleSelected:
            if 0 in indices and self.data[0].sha1 in [Git.LUC_SHA1, Git.LCC_SHA1]:
                allCommitted = False
            elif 1 in indices and self.data[1].sha1 in [Git.LCC_SHA1]:
                allCommitted = False
        else:
            allCommitted = self.isCurrentCommitted()

        # Operations that work with multiple selection
        self.acCopySummary.setEnabled(allCommitted)
        self.acGenPatch.setEnabled(allCommitted)
        self.acCopyAbbrevCommit.setEnabled(allCommitted)

        logWindow = self.logWindow()
        w = logWindow.mergeWidget if logWindow else None
        visible = w is not None
        self.acCopyToLog.setVisible(visible)
        if visible:
            # Only allow copy to log for single selection
            self.acCopyToLog.setEnabled(
                allCommitted and w.isResolving() and not multipleSelected)

        if self._editable:
            # Revert supports multiple selection
            enabled = allCommitted and not not self._branchDir
            self.acRevert.setEnabled(enabled)

            # Reset only works for single selection
            enabled = enabled and not multipleSelected
            # to avoid bad reset on each repo
            app = ApplicationBase.instance()
            if enabled and app.settings().isCompositeMode():
                # disable only if have submodules
                enabled = not app.submodules
            self.resetMenu.setEnabled(enabled)

            # Change author only works for single selection
            self.acChangeAuthor.setEnabled(
                allCommitted and not multipleSelected and not not self._branchDir)

        # Code review only works for single selection
        self.acCodeReview.setEnabled(allCommitted and not multipleSelected)

        hasMark = self.marker.hasMark()
        self.acClearMarks.setVisible(hasMark)

        globalPos = self.mapToGlobal(pos)
        self.menu.exec(globalPos)

    def updateSettings(self):
        settings = ApplicationBase.instance().settings()
        self.setFont(settings.logViewFont())

        self.lineHeight = self.fontMetrics().height() + self.lineSpace

        self.updateGeometries()
        self.updateView()

    def updateView(self):
        return self.viewport().update()

    def _createProgressDialog(self, label: str, maxValue: int):
        progress = QProgressDialog(
            label,
            self.tr("Cancel"),
            0, maxValue, self)
        progress.setWindowTitle(self.window().windowTitle())
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(2000)
        return progress

    def __onCopyCommitSummary(self):
        if self.curIdx == -1:
            return

        # Get selected commits
        commits = self.getSelectedCommits()
        if not commits:
            return

        app = ApplicationBase.instance()
        clipboard = app.clipboard()

        htmlText = '<html>\n'
        htmlText += '<head>\n'
        htmlText += '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>\n'
        htmlText += '</head>\n'
        htmlText += '<body>\n'
        htmlText += '<div>\n'

        plainTexts = []

        progress = self._createProgressDialog(
            self.tr("Copying Commit Summaries"), len(commits))

        for idx, commitData in enumerate(commits):
            progress.setValue(idx)
            if progress.wasCanceled():
                break

            repoDir = commitRepoDir(commitData)
            commit = Git.commitSummary(commitData.sha1, repoDir)
            if not commit:
                continue

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

            plainTexts.append('{0} ("{1}", {2}, {3})'.format(
                commit["sha1"],
                commit["subject"],
                commit["author"],
                commit["date"]))

        progress.setValue(len(commits))

        htmlText += '</div>\n'
        htmlText += '</body>\n'
        htmlText += '</html>\n'

        mimeData = QMimeData()
        mimeData.setHtml(htmlText)
        mimeData.setText('\n'.join(plainTexts))

        clipboard.setMimeData(mimeData)

        app.trackFeatureUsage("menu.copy_commit_summary", {
            "count": len(commits)
        })

    def __onCopyAbbrevCommit(self):
        if self.curIdx == -1:
            return

        # Get selected commits
        commits = self.getSelectedCommits()
        if not commits:
            return

        abbrevs = []

        progress = self._createProgressDialog(
            self.tr("Copying Commit Hashes"), len(commits))

        for idx, commit in enumerate(commits):
            progress.setValue(idx)
            if progress.wasCanceled():
                break

            abbrev = Git.abbrevCommit(commit.sha1)
            abbrevs.append(abbrev)

        progress.setValue(len(commits))

        mimeData = QMimeData()
        mimeData.setText('\n'.join(abbrevs))

        app = ApplicationBase.instance()
        clipboard = app.clipboard()
        clipboard.setMimeData(mimeData)

        app.trackFeatureUsage("menu.copy_abbrev_commit", {
            "count": len(commits)
        })

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

        # Toggle markers for all selected commits
        if len(self.selectedIndices) > 1:
            # Multiple selection: toggle each commit
            for idx in self.selectedIndices:
                self.marker.toggle(idx)
        else:
            # Single selection: toggle current commit
            self.marker.toggle(self.curIdx)

        # TODO: update marked lines only
        self.viewport().update()

    def __onClearMarks(self):
        self.marker.clear()
        # TODO: update marked lines only
        self.viewport().update()

    def __onGeneratePatch(self):
        if self.curIdx == -1:
            return

        # Get selected commits
        commits = self.getSelectedCommits()
        if not commits:
            return

        f, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Patch"))
        if f:
            patch = b''

            progress = self._createProgressDialog(
                self.tr("Generating Patches"), len(commits))

            # Generate patches for all selected commits
            for idx, commit in enumerate(commits):
                progress.setValue(idx)
                if progress.wasCanceled():
                    break

                repoDir = commitRepoDir(commit)
                commitPatch = Git.commitRawPatch(commit.sha1, repoDir)
                if commitPatch:
                    if patch:
                        patch += b'\n'
                    patch += commitPatch

                for subCommit in commit.subCommits:
                    repoDir = commitRepoDir(subCommit)
                    subPatch = Git.commitRawPatch(subCommit.sha1, repoDir)
                    if subPatch:
                        patch += b'\n' + subPatch

            progress.setValue(len(commits))

            if patch:
                with open(f, "wb+") as h:
                    h.write(patch)

        app = ApplicationBase.instance()
        app.trackFeatureUsage("menu.generate_patch", {
            "count": len(commits)
        })

    def __onGenerateDiff(self):
        if self.curIdx == -1:
            return

        # Get selected commits
        commits = self.getSelectedCommits()
        if not commits:
            return

        f, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Diff"))
        if f:
            diff = b''

            progress = self._createProgressDialog(
                self.tr("Generating Diffs"), len(commits))

            # Generate diffs for all selected commits
            for idx, commit in enumerate(commits):
                progress.setValue(idx)
                if progress.wasCanceled():
                    break

                repoDir = commitRepoDir(commit)
                commitDiff = Git.commitRawDiff(commit.sha1, repoDir=repoDir)
                if commitDiff:
                    if diff:
                        diff += b'\n'
                    diff += commitDiff

                for subCommit in commit.subCommits:
                    repoDir = commitRepoDir(subCommit)
                    subDiff = Git.commitRawDiff(
                        subCommit.sha1, repoDir=repoDir)
                    if subDiff:
                        diff += b'\n' + subDiff

            progress.setValue(len(commits))

            if diff:
                with open(f, "wb+") as h:
                    h.write(diff)

        app = ApplicationBase.instance()
        app.trackFeatureUsage("menu.generate_diff", {
            "count": len(commits)
        })

    def __onRevertCommit(self):
        if self.curIdx == -1:
            return

        # Get selected commits
        commits = self.getSelectedCommits()
        if not commits:
            return

        # Confirm revert for multiple commits
        if len(commits) > 1:
            reply = QMessageBox.question(
                self, self.window().windowTitle(),
                self.tr("Are you sure you want to revert {0} commits?").format(
                    len(commits)),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)
            if reply != QMessageBox.Yes:
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

        progress = self._createProgressDialog(
            self.tr("Reverting Commits"), len(commits))

        for idx, commit in enumerate(commits):
            progress.setValue(idx)
            if progress.wasCanceled():
                break

            repoDir = commitRepoDir(commit)
            if not _doRevert(commit.sha1, repoDir):
                break

            for subCommit in commit.subCommits:
                repoDir = commitRepoDir(subCommit)
                if not _doRevert(subCommit.sha1, repoDir):
                    break

        progress.setValue(len(commits))

        # FIXME: fetch the new one only?
        self.clear()
        self.showLogs(self.curBranch, self._branchDir, self.args)

        app = ApplicationBase.instance()
        app.trackFeatureUsage("menu.revert_commit", {
            "count": len(commits)
        })

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

        app = ApplicationBase.instance()
        app.trackFeatureUsage("menu.reset_commit", {
            "method": method
        })

    def __onResetSoft(self):
        self.__resetToCurCommit("soft")

    def __onResetMixed(self):
        self.__resetToCurCommit("mixed")

    def __onResetHard(self):
        self.__resetToCurCommit("hard")

    def changeAuthor(self):
        """Change the author of the currently selected commit"""
        if self.curIdx == -1:
            return
        commit = self.data[self.curIdx]
        if not commit:
            return

        # Don't allow changing author for local changes
        if commit.sha1 in [Git.LUC_SHA1, Git.LCC_SHA1]:
            QMessageBox.warning(
                self, self.window().windowTitle(),
                self.tr("Cannot change author for uncommitted changes."))
            return

        dialog = ChangeAuthorDialog(self)
        if dialog.exec() != ChangeAuthorDialog.Accepted:
            return

        authorName = dialog.authorName
        authorEmail = dialog.authorEmail

        if not authorName or not authorEmail:
            QMessageBox.warning(
                self, self.window().windowTitle(),
                self.tr("Author name and email cannot be empty."))
            return

        # Confirm the action
        isHead = self.curIdx == 0 or (self.curIdx == 1 and self.data[0].sha1 in [
                                      Git.LUC_SHA1, Git.LCC_SHA1])
        message = self.tr(
            "Are you sure you want to change the author of this commit to:\n\n"
            "{0} <{1}>\n\n").format(authorName, authorEmail)

        if not isHead:
            message += self.tr(
                "Warning: This will rewrite commit history from this commit onwards.\n"
                "Make sure you understand the implications before proceeding.")

        reply = QMessageBox.question(
            self, self.window().windowTitle(),
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        repoDir = commitRepoDir(commit)
        ret, error = Git.changeCommitAuthor(
            self.curBranch, commit.sha1, authorName, authorEmail, repoDir)

        if ret != 0:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                self.tr("Failed to change commit author:\n{0}").format(error))
        else:
            # Reload logs to show updated information
            self.reloadLogs()

        app = ApplicationBase.instance()
        app.trackFeatureUsage("menu.change_commit_author")

    def __onChangeAuthor(self):
        self.changeAuthor()

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
            elif self._selectOnFetch:
                self.setCurrentIndex(0)

        self.updateGeometries()

    def __onFetchFinished(self, exitCode):
        if self.delayVisible:
            self.ensureVisible(self.curIdx)
            self.delayVisible = False
        elif self.curIdx == -1 and self.data and self._selectOnFetch:
            self.setCurrentIndex(0)

        self.endFetch.emit()
        self.viewport().update()

        if exitCode != 0 and self.fetcher.errorData:
            QMessageBox.critical(self, self.window().windowTitle(),
                                 self.fetcher.errorData.decode("utf-8"))

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

    def __onFetchTooSlow(self, seconds: int):
        settings = ApplicationBase.instance().settings()
        if not settings.showFetchSlowAlert():
            return

        msgBox = QMessageBox(self)
        msgBox.setIcon(QMessageBox.Question)
        msgBox.setWindowTitle(self.tr("Performance Issue Detected"))
        text = self.tr(
            "Git log retrieval is taking longer than expected ({0} seconds).").format(seconds)
        text += "\n\n"
        text += self.tr("Disabling 'Detect Local Changes' can significantly improve performance. ")
        text += self.tr("This feature checks for uncommitted changes, which can be slow in large repositories.")
        text += "\n\n" + self.tr("Would you like to disable this feature now?")
        msgBox.setText(text)

        details = self.tr(
            "About this setting:\n"
            "- When enabled, Git checks for local changes that haven't been committed\n"
            "- This allows you to see uncommitted changes in the log view\n"
            "- Disabling it will make log loading faster but won't show uncommitted changes\n\n"
            "You can change this setting later in:\n"
            "Settings → Commit → Detect Local Changes"
        )
        msgBox.setDetailedText(details)

        cb = QCheckBox(self.tr("Don't show this message again"), self)
        msgBox.setCheckBox(cb)
        msgBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msgBox.setDefaultButton(QMessageBox.No)

        r = msgBox.exec()
        if r == QMessageBox.Yes:
            settings.setDetectLocalChanges(False)

        if cb.isChecked():
            settings = ApplicationBase.instance().settings()
            settings.setShowFetchSlowAlert(False)

        logger = ApplicationBase.instance().telemetry().logger()
        logger.info("Slow fetch alert", extra={
            "seconds": seconds,
            "disabled": r == QMessageBox.Yes,
            "dont_show": cb.isChecked()
        })

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

    def itemRect(self, index, needMargin=True):
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

    def __drawGraph(self, painter, graphPainter: QPainter, rect, cid):
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
            # Check if this commit is just before the drop indicator
            isBeforeDropLine = (self._dropIndicatorLine >= 0 and
                                cid == self._dropIndicatorLine - 1 and
                                self._dropIndicatorOffset > 0)
            extendLineBy = 0
            if isBeforeDropLine:
                maxOffset = self.lineHeight * 0.5
                extendLineBy = int(maxOffset * self._dropIndicatorOffset)

            # Apply drop indicator offset if this commit is at or below drop line
            if self._dropIndicatorLine >= 0 and cid >= self._dropIndicatorLine and self._dropIndicatorOffset > 0:
                maxOffset = self.lineHeight * 0.5
                dropOffset = int(maxOffset * self._dropIndicatorOffset)
                graphPainter.translate(0, dropOffset)

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
                                     color, activeColor, isHead, firstCommit, extendLineBy)

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

    def __drawGraphLane(self, painter: QPainter, lane, x1, x2, color, activeColor, isHead, firstCommit, extendLineBy: int = 0):
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
                painter.drawLine(m, h, m, 2 * h + extendLineBy)
            else:
                painter.drawLine(m, 0, m, 2 * h + extendLineBy)

        elif lane == Lane.HEAD_L or \
                lane == Lane.BRANCH:
            painter.drawLine(m, h, m, 2 * h + extendLineBy)

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
        rect = self.itemRect(index, False)
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
        self.cancelFindCommit()

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

    def _drawNoDataTips(self, painter: QPainter):
        if not self._showNoDataTips:
            return

        if not Git.REPO_DIR:
            return

        settings = ApplicationBase.instance().settings()
        if self.fetcher.isLoading():
            tips = self.tr("Loading commits, please wait...")
        elif self.args:
            tips = self.tr(
                "No commits found for the current filter. Try adjusting your filter criteria.")
        elif settings.isCompositeMode() and \
                settings.maxCompositeCommitsSince() != 0 and \
                self.fetcher._submodules:
            tips = self.tr(
                'No commits found. You may need to increase the "Max Commits" setting or disable "Composite Mode".')
        else:
            return

        painter.drawText(self.viewport().rect(), Qt.AlignCenter, tips)

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setClipRect(event.rect())

        if not self.data:
            self._drawNoDataTips(painter)
            return

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

        app = ApplicationBase.instance()
        isFullMessage = app.settings().isFullCommitMessage()

        def makeMessage(commit):
            if isFullMessage:
                return commit.comments.replace('\n', ' ')
            return commit.comments.split('\n')[0]

        colorSchema = app.colorSchema()

        painter.setFont(self.font())
        flags = Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine

        # Calculate drop indicator offset for items
        dropOffset = 0
        if self._dropIndicatorLine >= 0 and self._dropIndicatorOffset > 0:
            maxOffset = self.lineHeight * 0.5
            dropOffset = int(maxOffset * self._dropIndicatorOffset)

        for i in range(startLine, endLine):
            # Apply translation for items at or below drop indicator
            if self._dropIndicatorLine >= 0 and i >= self._dropIndicatorLine and dropOffset > 0:
                painter.save()
                painter.translate(0, dropOffset)

            # Get full item rect without margin for selection background
            fullRect = self.itemRect(i, needMargin=False)

            # Distinguish between selected items and active/current item
            isSelected = i in self.selectedIndices
            isCurrent = i == self.curIdx

            # Get rect with margin for content drawing
            rect = self.itemRect(i)
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
                self.__drawTag(painter, rect, color, text,
                               textColor=colorSchema.AuthorTagFg)

                # date
                text = commit.authorDate.split(' ')[0]
                color = colorSchema.DateTagBg
                self.__drawTag(painter, rect, color, text,
                               textColor=colorSchema.DateTagFg)
                needMargin = True

            if needMargin:
                rect.adjust(4, 0, 0, 0)

            # Draw selection/hover background only after tags
            selectionRect = QRect(fullRect)
            selectionRect.setLeft(rect.left())
            if isSelected:
                painter.fillRect(selectionRect, colorSchema.SelectedItemBg)
            elif i == self.hoverIdx:
                painter.fillRect(selectionRect, colorSchema.HoverItemBg)

            # marker
            self.marker.draw(i, painter, rect)

            # subject
            painter.save()

            # Set text color based on selection state
            if isSelected:
                painter.setPen(colorSchema.SelectedItemFg)

            # Set text color based on selection state
            if isSelected:
                painter.setPen(colorSchema.SelectedItemFg)
            else:
                painter.setPen(palette.color(QPalette.WindowText))

            # Draw focus/active border for current item (drawn over selection)
            if isCurrent and app.applicationState() == Qt.ApplicationActive:
                pen = QPen(colorSchema.FocusItemBorder)
                pen.setCosmetic(True)
                painter.setPen(pen)
                borderRect = QRectF(selectionRect)
                borderRect.adjust(0.5, 0.5, -0.5, -0.5)
                painter.drawRect(borderRect)
                # Restore text color
                if isSelected:
                    painter.setPen(colorSchema.SelectedItemFg)
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
                    if isSelected:
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

            # Restore translation if applied
            if self._dropIndicatorLine >= 0 and i >= self._dropIndicatorLine and dropOffset > 0:
                painter.restore()

        if graphImage:
            del graphPainter
            self.logGraph.render(graphImage)

        # Draw drop indicator with animation
        if self._dropIndicatorLine >= 0 and self._dropIndicatorAlpha > 0:
            self.__drawDropIndicator(painter, self._dropIndicatorLine)

    def __drawDropIndicator(self, painter: QPainter, line: int):
        """Draw an animated drop indicator with glowing effect"""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.itemRect(line, needMargin=False)
        maxOffset = self.lineHeight * 0.5
        centerOffset = int(maxOffset * self._dropIndicatorOffset * 0.5)
        y = rect.top() + centerOffset
        width = self.viewport().width()
        alpha = int(self._dropIndicatorAlpha * 255)

        colorSchema = ApplicationBase.instance().colorSchema()
        baseColor = colorSchema.FocusItemBorder

        # Draw expanding glow effect
        glowLevels = 3
        for i in range(glowLevels, 0, -1):
            glowAlpha = int(alpha * 0.3 * (glowLevels - i + 1) / glowLevels)
            pen = QPen(baseColor)
            pen.setWidth(i * 2)
            color = baseColor
            color.setAlpha(glowAlpha)
            pen.setColor(color)
            painter.setPen(pen)
            painter.drawLine(0, y, width, y)

        # Draw main indicator line
        pen = QPen(baseColor)
        pen.setWidth(2)
        color = baseColor
        color.setAlpha(alpha)
        pen.setColor(color)
        painter.setPen(pen)
        painter.drawLine(0, y, width, y)

        # Draw arrow indicators on both sides
        arrowSize = 8
        arrowAlpha = alpha

        # Left arrow
        path = QPainterPath()
        path.moveTo(arrowSize, y)
        path.lineTo(0, y - arrowSize // 2)
        path.lineTo(0, y + arrowSize // 2)
        path.closeSubpath()

        color = baseColor
        color.setAlpha(arrowAlpha)
        painter.fillPath(path, color)

        # Right arrow
        path = QPainterPath()
        path.moveTo(width - arrowSize, y)
        path.lineTo(width, y - arrowSize // 2)
        path.lineTo(width, y + arrowSize // 2)
        path.closeSubpath()

        color = baseColor
        color.setAlpha(arrowAlpha)
        painter.fillPath(path, color)

        painter.restore()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self.data:
            return

        if event.button() == Qt.RightButton:
            index = self.lineForPos(event.position())
            if index >= 0 and index != self.curIdx:
                self.setCurrentIndex(index, clearSelection=False)
            return

        if event.button() != Qt.LeftButton:
            return

        index = self.lineForPos(event.position())
        mod = event.modifiers()

        if mod == Qt.AltModifier:
            if index >= 0:
                self.marker.toggle(index)
                self.viewport().update()
            return

        # Handle multi-selection with keyboard modifiers
        if mod == Qt.ControlModifier:
            # Toggle selection for clicked item
            if index in self.selectedIndices:
                self.selectedIndices.remove(index)
            else:
                self.selectedIndices.add(index)

            # Update current index but keep other selections
            oldIdx = self.curIdx
            self.curIdx = index
            self.__ensureChildren(index)
            self.selectionAnchor = -1  # Reset anchor on Ctrl+click

            # Update only affected items
            if oldIdx != -1:
                self.invalidateItem(oldIdx)
            self.invalidateItem(index)
            self.currentIndexChanged.emit(self.curIdx)

        elif mod == Qt.ShiftModifier:
            # Range selection from anchor (or curIdx if no anchor) to clicked index
            if self.curIdx == -1:
                # No current index, just select clicked item
                self.setCurrentIndex(index)
            else:
                # Set anchor if not already set
                if self.selectionAnchor == -1:
                    self.selectionAnchor = self.curIdx
                # Select range from anchor to clicked index
                start = min(self.selectionAnchor, index)
                end = max(self.selectionAnchor, index)
                self.selectedIndices.clear()
                self.selectedIndices.update(range(start, end + 1))
                self.setCurrentIndex(index, clearSelection=False)
        else:
            # Normal click - clear previous selections and select clicked item
            needUpdate = index == self.curIdx and len(
                self.selectedIndices) > 0 and index not in self.selectedIndices
            self.setCurrentIndex(index)

            if needUpdate:
                self.viewport().update()

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press to prepare for potential drag"""
        if event.button() == Qt.LeftButton and self.data:
            index = self.lineForPos(event.position())
            if index >= 0:
                # Store drag start position and index
                self._dragStartPos = event.position()
                return

        # Reset drag state for non-drag scenarios
        self._dragStartPos = None

    def mouseMoveEvent(self, event: QMouseEvent):
        # Check if we should start dragging
        if (event.buttons() & Qt.LeftButton) and self._dragStartPos is not None:
            if (event.position() - self._dragStartPos).manhattanLength() >= 10:
                # Determine what to drag
                dragIndex = self.lineForPos(self._dragStartPos)
                if dragIndex >= 0 and dragIndex not in self.selectedIndices:
                    # Dragging unselected item - drag only this item
                    dragIndices = [dragIndex]
                else:
                    # Dragging selected item(s) - drag all selected items
                    dragIndices = sorted(list(self.selectedIndices))

                self._startDrag(dragIndices)
                return

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
        mod = ApplicationBase.instance().keyboardModifiers()

        # Handle Ctrl+A for select all
        if event.key() == Qt.Key_A and mod == Qt.ControlModifier:
            if self.data:
                self.selectedIndices.clear()
                self.selectedIndices.update(range(len(self.data)))
                self.viewport().update()
            return

        # Handle Space to toggle selection of current item
        if event.key() == Qt.Key_Space:
            if self.curIdx >= 0:
                if self.curIdx in self.selectedIndices:
                    self.selectedIndices.remove(self.curIdx)
                else:
                    self.selectedIndices.add(self.curIdx)
                self.invalidateItem(self.curIdx)
            return

        if event.key() == Qt.Key_Up:
            if self.curIdx > 0:
                startLine = self.verticalScrollBar().value()
                oldIdx = self.curIdx
                self.curIdx -= 1
                self.__ensureChildren(self.curIdx)

                # Handle multi-selection with modifiers
                if mod == Qt.ShiftModifier:
                    # Shift+Up: Range selection from anchor
                    if self.selectionAnchor == -1:
                        self.selectionAnchor = oldIdx
                    start = min(self.selectionAnchor, self.curIdx)
                    end = max(self.selectionAnchor, self.curIdx)
                    self.selectedIndices.clear()
                    self.selectedIndices.update(range(start, end + 1))
                else:
                    # Reset anchor when not using Shift
                    self.selectionAnchor = -1

                if self.curIdx < startLine:
                    self.verticalScrollBar().setValue(self.curIdx)
                self.viewport().update()

                self.currentIndexChanged.emit(self.curIdx)

        elif event.key() == Qt.Key_Down:
            if self.curIdx + 1 < len(self.data):
                endLineF = self.verticalScrollBar().value() + self.__linesPerPageF()
                oldIdx = self.curIdx
                self.curIdx += 1
                self.__ensureChildren(self.curIdx)

                # Handle multi-selection with modifiers
                if mod == Qt.ShiftModifier:
                    # Shift+Down: Range selection from anchor
                    if self.selectionAnchor == -1:
                        self.selectionAnchor = oldIdx
                    start = min(self.selectionAnchor, self.curIdx)
                    end = max(self.selectionAnchor, self.curIdx)
                    self.selectedIndices.clear()
                    self.selectedIndices.update(range(start, end + 1))
                else:
                    # Reset anchor when not using Shift
                    self.selectionAnchor = -1

                if self.curIdx < int(endLineF) or \
                        (self.curIdx == int(endLineF)
                         and (endLineF - self.curIdx >= HALF_LINE_PERCENT)):
                    pass
                else:
                    v = self.verticalScrollBar().value()
                    self.verticalScrollBar().setValue(v + 1)
                self.viewport().update()

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
        # Redraw current item to show focus border
        self.invalidateItem(self.curIdx)

    def focusOutEvent(self, event):
        # Redraw current item to hide focus border
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
        if not self._standalone:
            return

        submodules = ApplicationBase.instance().submodules
        if not submodules:
            self.viewport().update()
            return

        self.clear()
        self._branchDir = Git.branchDir(self.curBranch)
        self.showLogs(self.curBranch, self._branchDir, self.args)

    def __onSubmoduleAvailable(self, submodules, isCache):
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

    def setEditable(self, editable: bool):
        self._editable = editable
        self.setAcceptDrops(self._standalone and self._editable)

    def codeReviewOnCurrent(self):
        self.__onCodeReview()

    def setShowNoDataTips(self, show: bool):
        self._showNoDataTips = show
        self.viewport().update()

    def setAllowSelectOnFetch(self, allow: bool):
        self._selectOnFetch = allow

    def setStandalone(self, standalone: bool):
        self._standalone = standalone
        self.setAcceptDrops(standalone and self._editable)

    def _createDragPreview(self, commits: List[Commit]) -> QPixmap:
        """Create a preview pixmap for dragging commits"""
        if not commits:
            return None

        # Configuration
        maxVisibleCommits = 2
        padding = 8
        lineSpacing = 4
        maxTextWidth = 400
        iconSize = 16
        margin = 4

        # Get color scheme
        colorSchema = ApplicationBase.instance().colorSchema()
        bgColor = self.palette().color(QPalette.Base)
        textColor = self.palette().color(QPalette.WindowText)
        borderColor = colorSchema.FocusItemBorder

        # Prepare font
        fm = self.fontMetrics()
        lineHeight = fm.height()

        # Helper function to get short sha1 and summary
        def getCommitText(commit: Commit) -> str:
            shortSha = commit.sha1[:7]
            summary = commit.comments.split('\n')[0]
            return f"{shortSha} {summary}"

        # Calculate lines to draw
        lines = []
        maxWidth = 0

        def _addElidedText(text: str):
            nonlocal maxWidth
            text = fm.elidedText(
                text, Qt.ElideRight, maxTextWidth - iconSize - padding * 2 - margin)
            textWidth = fm.horizontalAdvance(text)
            maxWidth = max(maxWidth, textWidth)
            lines.append(text)

        for i in range(min(len(commits), maxVisibleCommits)):
            text = getCommitText(commits[i])
            _addElidedText(text)

        # Add count indicator if more than maxVisibleCommits
        extraCount = len(commits) - maxVisibleCommits
        if extraCount == 1:
            _addElidedText(getCommitText(commits[maxVisibleCommits]))
            maxVisibleCommits = 3
        elif extraCount > 1:
            text = self.tr("... and {0} more commits").format(extraCount)
            _addElidedText(text)

        # Clamp width
        maxWidth = min(maxWidth, maxTextWidth)

        width = maxWidth + 2 * padding + iconSize + margin
        height = len(lines) * (lineHeight + lineSpacing) - \
            lineSpacing + 2 * padding

        # Create pixmap with transparency
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(width * ratio, height * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(self.font())

        # Draw background with rounded corners
        bgRect = QRectF(0, 0, width, height)
        painter.setPen(borderColor)
        painter.setBrush(bgColor)
        painter.drawRoundedRect(bgRect.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)

        # Draw text
        textX = padding + iconSize + margin
        textY = padding

        painter.setPen(textColor)
        for i, line in enumerate(lines):
            if i >= maxVisibleCommits:
                # Draw extra count in a lighter color
                painter.save()
                font = painter.font()
                font.setItalic(True)
                painter.setFont(font)
                painter.setPen(colorSchema.Whitespace)
            else:
                # Draw commit icon
                painter.save()
                iconCenterX = padding + iconSize // 2
                iconCenterY = textY + lineHeight // 2

                circleRadius = iconSize // 5

                # Draw horizontal lines (left and right of circle)
                lineY = iconCenterY
                painter.setPen(QPen(textColor))
                # Left line
                painter.drawLine(
                    padding, lineY, iconCenterX - circleRadius, lineY)
                # Right line
                painter.drawLine(iconCenterX + circleRadius,
                                 lineY, padding + iconSize, lineY)

                # Draw circle
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(iconCenterX - circleRadius, iconCenterY - circleRadius,
                                    circleRadius * 2, circleRadius * 2)
                painter.restore()

            textRect = QRect(textX, textY, maxWidth, lineHeight)
            painter.drawText(textRect, Qt.AlignLeft |
                             Qt.AlignVCenter | Qt.TextSingleLine, line)

            if i >= maxVisibleCommits:
                painter.restore()

            textY += lineHeight + lineSpacing

        painter.end()

        return pixmap

    def _startDrag(self, dragIndices: List[int]):
        """Start drag operation with specified commit indices"""
        if not dragIndices:
            return

        # Get commits for the specified indices
        commits = [self.data[i] for i in dragIndices if i < len(self.data)]
        if not commits:
            return

        # Get repo URL for validation
        repoUrl = Git.repoUrl()

        # Serialize commits with minimal data (sha1, repoDir, subCommits)
        serializedCommits = []
        for commit in commits:
            commitData = {
                "sha1": commit.sha1,
                "repoDir": commit.repoDir if commit.repoDir else "."
            }
            # Serialize subCommits with same minimal data
            if commit.subCommits:
                commitData["subCommits"] = [
                    {
                        "sha1": sc.sha1,
                        "repoDir": sc.repoDir if sc.repoDir else "."
                    }
                    for sc in commit.subCommits
                ]
            serializedCommits.append(commitData)

        dragData = {
            "repoUrl": repoUrl,
            "repoDir": self._branchDir or Git.REPO_DIR,
            "branch": self.curBranch,
            "commits": serializedCommits
        }

        # Create drag data
        drag = QDrag(self)
        mimeData = QMimeData()

        sha1List = [c.sha1 for c in commits]
        mimeData.setText("\n".join(sha1List))
        mimeData.setData("application/x-qgitc-commits",
                         json.dumps(dragData).encode("utf-8"))

        drag.setMimeData(mimeData)

        # Create drag preview image
        pixmap = self._createDragPreview(commits)
        if pixmap:
            drag.setPixmap(pixmap)

        # Start drag
        drag.exec(Qt.CopyAction)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept drag if it contains commits from another logview or another app"""
        if event.mimeData().hasFormat("application/x-qgitc-commits"):
            source = event.source()
            # Accept if:
            # 1. From different logview in same app, OR
            # 2. From another app (source is None)
            if (source is None) or (isinstance(source, LogView) and source != self):
                # Initialize drop indicator state
                self._dropIndicatorAlpha = 0.0
                self._dropIndicatorOffset = 0.0
                event.acceptProposedAction()
            else:
                event.ignore()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        """Update drop indicator as drag moves"""
        if event.mimeData().hasFormat("application/x-qgitc-commits"):
            pos = event.position()
            line = self._findDropPosition(pos)
            if line >= 0:
                # Show drop indicator with animation if line changed
                if self._dropIndicatorLine != line:
                    self._dropIndicatorLine = line
                    # Continue animation from current value, don't reset
                    self._startDropIndicatorAnimation()
                event.acceptProposedAction()
                return
        event.ignore()

    def _findDropPosition(self, pos) -> int:
        """Find drop line index for given position"""

        # FIXME: we only support drop before HEAD for now
        # FIXME: if we are dropping local changes, we should allow dropping before LUC too
        for i in range(len(self.data)):
            sha1 = self.data[i].sha1
            if sha1 == Git.LCC_SHA1:
                return i + 1
            if sha1 == Git.LUC_SHA1:
                if (i + 1) < len(self.data) and self.data[i + 1].sha1 == Git.LCC_SHA1:
                    return i + 2
                return i + 1
            return 0

        return -1

    def dragLeaveEvent(self, event):
        """Clear drop indicator when drag leaves"""
        self._stopDropIndicatorAnimation()
        self._dropIndicatorLine = -1
        self._dropIndicatorAlpha = 0.0
        self._dropIndicatorOffset = 0.0
        self.viewport().update()

    def dropEvent(self, event: QDropEvent):
        """Handle drop of commits for cherry-picking"""
        self._stopDropIndicatorAnimation()
        self._dropIndicatorLine = -1
        self._dropIndicatorAlpha = 0.0
        self._dropIndicatorOffset = 0.0
        self.viewport().update()

        if not event.mimeData().hasFormat("application/x-qgitc-commits"):
            event.ignore()
            return

        # Get source widget
        sourceView = event.source()

        # Deserialize drag data
        try:
            dragDataBytes = event.mimeData().data("application/x-qgitc-commits").data()
            dragData: Dict = json.loads(dragDataBytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as e:
            QMessageBox.critical(
                self, self.tr("Cherry-pick Failed"),
                self.tr("Invalid drag data format."))
            event.ignore()
            return

        # Validation 0: Check repo URL matches
        sourceRepoUrl = dragData.get("repoUrl", "")
        targetRepoUrl = Git.repoUrl()
        if sourceRepoUrl != targetRepoUrl:
            QMessageBox.warning(
                self, self.tr("Cherry-pick Failed"),
                self.tr("Cannot cherry-pick commits from a different repository.\n\n"
                        "Source: {0}\nTarget: {1}").format(sourceRepoUrl or "<unknown>", targetRepoUrl or "<unknown>"))
            event.ignore()
            return

        commits = dragData.get("commits", [])
        if not commits:
            event.ignore()
            return

        # Get source branch from MIME data
        sourceBranch = dragData.get("branch", "")
        sourceRepoDir = dragData.get("repoDir", "")
        targetRepoDir = self._branchDir or Git.REPO_DIR
        isSameRepo = os.path.normcase(os.path.normpath(
            sourceRepoDir)) == os.path.normcase(os.path.normpath(targetRepoDir))

        # Validation 1: Check if same branch (ignore remotes/origin/ prefix)
        def normalizeBranch(branch: str) -> str:
            """Remove remotes/origin/ prefix for comparison"""
            if branch and branch.startswith("remotes/origin/"):
                return branch[15:]  # len("remotes/origin/") = 15
            return branch

        # Allow same branch if from different repo dir
        if isSameRepo and sourceBranch and normalizeBranch(sourceBranch) == normalizeBranch(self.curBranch):
            QMessageBox.warning(
                self, self.tr("Cherry-pick Failed"),
                self.tr("Cannot cherry-pick commits to the same branch."))
            event.ignore()
            return

        # Validation 2: Check if target branch is checked out
        if not self._branchDir or not os.path.exists(self._branchDir):
            QMessageBox.warning(
                self, self.tr("Cherry-pick Failed"),
                self.tr("The target branch '{0}' is not checked out.\n\n"
                        "Please checkout the branch first.").format(self.curBranch))
            event.ignore()
            return

        # TODO: Determine drop position
        dropBeforeSha1 = None

        app = ApplicationBase.instance()
        app.trackFeatureUsage("cherry_pick", {
            "commits": len(commits),
            "in_app": True if sourceView else False,
            "same_repo": isSameRepo
        })

        # Execute cherry-pick
        self._executeCherryPick(
            commits, sourceView, sourceRepoDir, dropBeforeSha1)

        event.acceptProposedAction()

    def _executeCherryPick(self, commits: List[dict], sourceView: 'LogView', sourceRepoDir: str, dropBeforeSha1: str = None):
        """Execute cherry-pick operation"""
        if not commits:
            return

        # Reverse the list to pick from oldest to newest
        # (commits are ordered newest first in the log view)
        commits = list(reversed(commits))

        # TODO: If dropBeforeSha1 is specified, we need to rebase
        # For now, just cherry-pick to HEAD

        # Cherry-pick commits one by one
        needReload = False

        app = ApplicationBase.instance()
        recordOrigin = app.settings().recordOrigin()

        progress = self._createProgressDialog(
            self.tr("Cherry-picking commits..."), len(commits))
        # avoid block the messagebox
        progress.setWindowModality(Qt.NonModal)

        for i, commit in enumerate(commits):
            progress.setValue(i)
            app.processEvents()
            if progress.wasCanceled():
                break

            sha1 = commit.get("sha1", "")
            subRepoDir = commit.get("repoDir", None)
            fullTargetRepoDir = fullRepoDir(subRepoDir, self._branchDir)
            fullSourceRepoDir = fullRepoDir(subRepoDir, sourceRepoDir)
            if self.doCherryPick(fullTargetRepoDir, sha1, fullSourceRepoDir, sourceView, recordOrigin):
                needReload = True
            else:
                # Stop processing remaining commits
                break

            subCommits = commit.get("subCommits", [])
            for subCommit in subCommits:
                sha1 = subCommit.get("sha1", "")
                subRepoDir = subCommit.get("repoDir", None)
                fullTargetRepoDir = fullRepoDir(subRepoDir, self._branchDir)
                fullSourceRepoDir = fullRepoDir(subRepoDir, sourceRepoDir)
                if self.doCherryPick(fullTargetRepoDir, sha1, fullSourceRepoDir, sourceView):
                    needReload = True
                else:
                    # Stop processing remaining commits
                    break

        progress.setValue(len(commits))
        # Reload logs to show new commits
        if needReload:
            self.reloadLogs()

    def doCherryPick(self, repoDir: str, sha1: str, sourceRepoDir: str, sourceView: 'LogView', recordOrigin=True) -> bool:
        """Perform cherry-pick of a single commit"""
        if sha1 in [Git.LUC_SHA1, Git.LCC_SHA1]:
            return self._applyLocalChanges(repoDir, sha1, sourceRepoDir, sourceView)

        ret, error, _ = Git.cherryPick(
            [sha1], recordOrigin=recordOrigin, repoDir=repoDir)
        if ret != 0:
            # Check if it's an empty commit (already applied)
            if self._handleEmptyCherryPick(repoDir, sha1, error, sourceView):
                return True
            # Check if it's a conflict
            if error and ("conflict" in error.lower() or Git.isCherryPicking(repoDir)):
                if self._resolveCherryPickConflict(repoDir, sha1, error, sourceView):
                    return True
            elif not sourceView and error and f"fatal: bad object {sha1}" in error:
                if self._pickFromAnotherRepo(repoDir, sourceRepoDir, sha1):
                    return True
            else:
                # Other error
                QMessageBox.critical(
                    self, self.tr("Cherry-pick Failed"),
                    self.tr("Cherry-pick of commit {0} failed:\n\n{1}").format(
                        sha1[:7], error if error else self.tr("Unknown error")))
            return False

        LogView._markPickStatus(sourceView, sha1, MarkType.PICKED)
        return True

    @staticmethod
    def _markPickStatus(sourceView: 'LogView', sha1: str, state: MarkType):
        # Only mark picks if sourceView exists (same app)
        if not sourceView:
            return
        # Find index in source logview
        for idx, commit in enumerate(sourceView.data):
            if commit.sha1 == sha1:
                sourceView.marker.mark(idx, idx, state)
                break
        sourceView.viewport().update()

    def _resolveCherryPickConflict(self, repoDir: str, sha1: str, error: str, sourceView: 'LogView') -> bool:
        """Resolve cherry-pick conflict"""
        process, ok = self._runMergeTool(
            repoDir, sha1, error, sourceView, True)
        if not ok:
            return False
        # User merge by external tool
        if not process:
            return True
        if process:
            ret = process.exitCode()
            if ret == 0:
                # Continue cherry-pick
                ret, error = Git.cherryPickContinue(repoDir)
                if ret == 0:
                    LogView._markPickStatus(
                        sourceView, sha1, MarkType.PICKED)
                    return True
                # After resolved, it can be empty commit
                if self._handleEmptyCherryPick(repoDir, sha1, error, sourceView):
                    return True
                QMessageBox.critical(
                    self, self.tr("Cherry-pick Failed"),
                    self.tr("Cherry-pick of commit {0} failed:\n\n{1}").format(
                        sha1[:7], error if error else self.tr("Unknown error")))
            else:
                error = process.readAllStandardError().data().decode("utf-8").rstrip()
                QMessageBox.critical(self, self.tr("Merge Tool Failed"), self.tr(
                    "Merge tool failed with error:\n\n{0}").format(error if error else self.tr("Unknown error")))

        # Abort cherry-pick
        Git.cherryPickAbort(repoDir)

        # Mark this commit as failed in source if source exists
        LogView._markPickStatus(sourceView, sha1, MarkType.FAILED)

        return False

    def _handleEmptyCherryPick(self, repoDir: str, sha1: str, error: str, sourceView: 'LogView') -> bool:
        if error and "git commit --allow-empty" in error:
            reply = QMessageBox.question(
                self, self.tr("Empty Cherry-pick"),
                self.tr("Commit {0} results in an empty commit (possibly already applied).\n\n"
                        "Do you want to skip it?").format(sha1[:7]),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes)

            if reply == QMessageBox.Yes:
                Git.cherryPickSkip(repoDir)
                return True

            if reply == QMessageBox.No:
                ret, error = Git.cherryPickAllowEmpty(repoDir)
                if ret == 0:
                    LogView._markPickStatus(
                        sourceView, sha1, MarkType.PICKED)
                    return True

                QMessageBox.critical(
                    self, self.tr("Cherry-pick Failed"),
                    self.tr("Cherry-pick of commit {0} failed:\n\n{1}").format(
                        sha1[:7], error if error else self.tr("Unknown error")))
                return False

        return False

    def _applyLocalChanges(self, targetRepoDir: str, sha1: str, sourceRepoDir: str, sourceView: 'LogView') -> bool:
        """Apply local uncommitted or cached changes using git diff and apply"""
        # Get the diff for the local changes
        diff = Git.commitRawDiff(sha1, repoDir=sourceRepoDir)
        if not diff:
            QMessageBox.warning(
                self, self.tr("Apply Changes Failed"),
                self.tr("No changes found to apply."))
            return False

        # Create a temporary patch file
        patchFile = None
        try:
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.patch', delete=False) as f:
                patchFile = f.name
                f.write(diff)

            args = ["apply", patchFile]
            if sha1 == Git.LCC_SHA1:
                args.insert(1, "--index")
            process = Git.run(args, repoDir=targetRepoDir, text=True)
            _, error = process.communicate()
            if process.returncode != 0:
                errorMsg = error if error else self.tr("Unknown error")
                QMessageBox.critical(
                    self, self.tr("Apply Changes Failed"),
                    self.tr("Failed to apply local changes:\n\n{0}").format(errorMsg))
                LogView._markPickStatus(
                    sourceView, sha1, MarkType.FAILED)
                return False

            LogView._markPickStatus(sourceView, sha1, MarkType.PICKED)
            return True

        except Exception as e:
            QMessageBox.critical(
                self, self.tr("Apply Changes Failed"),
                self.tr("Failed to apply local changes:\n\n{0}").format(str(e)))
            LogView._markPickStatus(sourceView, sha1, MarkType.FAILED)
            return False
        finally:
            if patchFile:
                os.remove(patchFile)

    def _pickFromAnotherRepo(self, repoDir: str, sourceRepoDir: str, sha1: str) -> bool:
        """Pick commits from another repository by generating and applying patch"""
        # Generate patch from source repo
        args = ["format-patch", "-1", "--stdout", sha1]
        process = Git.run(args, repoDir=sourceRepoDir, text=True)
        patchContent, error = process.communicate()

        if process.returncode != 0:
            errorMsg = error if error else self.tr("Unknown error")
            QMessageBox.critical(
                self, self.tr("Cherry-pick Failed"),
                self.tr("Failed to generate patch from source repository:\n\n{0}").format(errorMsg))
            return False

        if not patchContent:
            QMessageBox.warning(
                self, self.tr("Cherry-pick Failed"),
                self.tr("No patch content generated for commit {0}.").format(sha1[:7]))
            return False

        # Create a temporary patch file
        patchFile = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False, encoding='utf-8') as f:
                patchFile = f.name
                f.write(patchContent)

            # Apply patch to target repo
            args = ["am", "--3way", "--ignore-space-change", patchFile]
            process = Git.run(args, repoDir=repoDir, text=True)
            _, error = process.communicate()

            if process.returncode != 0:
                errorMsg = error if error else self.tr("Unknown error")

                # Check if it's a conflict
                if error and ("conflict" in error.lower() or Git.isApplying(repoDir)):
                    process, ok = self._runMergeTool(
                        repoDir, sha1, error, None, False)
                    if not ok:
                        return False
                    if not process:
                        return True
                    if process:
                        ret = process.exitCode()
                        if ret == 0:
                            # Continue applying
                            ret, error = Git.amContinue(repoDir)
                            if ret == 0:
                                return True
                            if self._handleEmptyCherryPick(repoDir, sha1, error, None):
                                return True
                            QMessageBox.critical(
                                self, self.tr("Cherry-pick Failed"),
                                self.tr("Cherry-pick of commit {0} failed:\n\n{1}").format(
                                    sha1[:7], error if error else self.tr("Unknown error")))
                        else:
                            error = process.readAllStandardError().data().decode("utf-8").rstrip()
                            QMessageBox.critical(
                                self, self.tr("Merge Tool Failed"),
                                self.tr("Merge tool failed with error:\n\n{0}").format(
                                    error if error else self.tr("Unknown error")))

                    # Abort applying
                    Git.amAbort(repoDir)
                    return False
                else:
                    QMessageBox.critical(
                        self, self.tr("Cherry-pick Failed"),
                        self.tr("Failed to apply patch to target repository:\n\n{0}").format(errorMsg))
                    return False

            return True

        except Exception as e:
            QMessageBox.critical(
                self, self.tr("Cherry-pick Failed"),
                self.tr("Failed to apply patch from another repository:\n\n{0}").format(str(e)))
            return False
        finally:
            if patchFile and os.path.exists(patchFile):
                os.remove(patchFile)

    def _runMergeTool(self, repoDir: str, sha1: str, error: str, sourceView: 'LogView', isPick: bool):
        msgBox = QMessageBox(self)
        msgBox.setWindowTitle(self.tr("Cherry-pick Conflict"))
        msgBox.setText(
            self.tr("Cherry-pick of commit {0} failed with conflicts:\n\n{1}\n\n"
                    "Do you want to resolve the conflicts using mergetool?").format(
                sha1[:7], error))
        msgBox.setIcon(QMessageBox.Question)

        yesBtn = msgBox.addButton(QMessageBox.Yes)
        msgBox.addButton(QMessageBox.Abort)
        resolvedBtn = msgBox.addButton(
            self.tr("Already Resolved"), QMessageBox.ActionRole)
        msgBox.setDefaultButton(yesBtn)

        msgBox.exec()
        clickedBtn = msgBox.clickedButton()

        if clickedBtn == resolvedBtn:
            # User already resolved externally (trust user choice)
            LogView._markPickStatus(sourceView, sha1, MarkType.PICKED)
            return None, True

        if clickedBtn == yesBtn:
            # Check if merge tool is configured
            toolName = ApplicationBase.instance().settings().mergeToolName()
            if not toolName:
                # Check if git has a default merge.tool configured
                gitMergeTool = Git.getConfigValue("merge.tool", False)
                if not gitMergeTool:
                    QMessageBox.warning(
                        self, self.tr("Merge Tool Not Configured"),
                        self.tr("No merge tool is configured.\n\n"
                                "Please configure a merge tool in:\n"
                                "- Git global config: git config --global merge.tool <tool-name>\n"
                                "- Or in Preferences > Tools tab"))
                    if isPick:
                        Git.cherryPickAbort(repoDir)
                    else:
                        Git.amAbort(repoDir)

                    LogView._markPickStatus(
                        sourceView, sha1, MarkType.FAILED)
                    return None, False

            # Run git mergetool using QProcess with event loop
            process = QProcess()
            process.setWorkingDirectory(repoDir)

            env = QProcessEnvironment.systemEnvironment()
            env.insert("LANGUAGE", "en_US")
            process.setProcessEnvironment(env)

            args = ["mergetool", "--no-prompt"]
            if toolName:
                args.append("--tool=%s" % toolName)

            # Use event loop to wait for process to finish without blocking UI
            loop = QEventLoop()
            process.finished.connect(loop.quit)
            process.start(GitProcess.GIT_BIN, args)
            loop.exec()

            return process, True

        if isPick:
            Git.cherryPickAbort(repoDir)
        else:
            Git.amAbort(repoDir)

        LogView._markPickStatus(sourceView, sha1, MarkType.FAILED)
        return None, False
