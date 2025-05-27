# -*- coding: utf-8 -*-

import re
from typing import List

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QFrame, QMenu

from qgitc.applicationbase import ApplicationBase
from qgitc.blameline import BlameLine
from qgitc.events import BlameEvent, ShowCommitEvent
from qgitc.textline import Link
from qgitc.textviewer import TextViewer

ABBREV_N = 4


class RevisionPanel(TextViewer):

    revisionActivated = Signal(BlameLine)

    def __init__(self, viewer):
        self._viewer = viewer
        self._revs: List[BlameLine] = []

        super().__init__(viewer)

        self._activeRev = None
        self._sha1Pattern = re.compile(r"^[a-f0-9]{%s}" % ABBREV_N)

        self._hoveredLine = -1
        self._menu = None

        viewer.textLineClicked.connect(
            self._onTextLineClicked)
        self.textLineClicked.connect(
            self._onTextLineClicked)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)

        settings = ApplicationBase.instance().settings()
        settings.diffViewFontChanged.connect(self.delayUpdateSettings)

    def toTextLine(self, text):
        textLine = super().toTextLine(text)
        textLine.useBuiltinPatterns = False
        textLine.setCustomLinkPatterns([(Link.Sha1, self._sha1Pattern, None)])
        return textLine

    def reloadSettings(self):
        self.updateFont(ApplicationBase.instance().settings().diffViewFont())

        fm = QFontMetrics(self._font)
        self._sha1Width = fm.horizontalAdvance('a') * ABBREV_N
        self._dateWidth = fm.horizontalAdvance("2020-05-27")
        self._space = fm.horizontalAdvance(' ')
        self._digitWidth = fm.horizontalAdvance('9')
        self._maxNameWidth = 12 * fm.horizontalAdvance('W')

        width = self._sha1Width + self._space * 6
        width += self._dateWidth
        width += self._maxNameWidth
        width += self._digitWidth * 6 + self.textMargins()
        self.resize(width, self._viewer.height())

    def appendRevisions(self, revs: List[BlameLine]):
        texts = []
        for rev in revs:
            text = rev.sha1[:ABBREV_N]
            self._fix_rev(rev)
            if not self._revs or self._revs[len(self._revs) - 1].sha1 != rev.sha1:
                text += " " + rev.authorTime.split(" ")[0]
                text += " " + rev.author

            texts.append(text)
            self._revs.append(rev)

        self.appendLines(texts)
        self.update()

    def updateLinkData(self, link, lineNo):
        link.setData(self._revs[lineNo].sha1)

    def firstVisibleLine(self):
        return self._viewer.firstVisibleLine()

    @property
    def revisions(self):
        return self._revs

    def clear(self):
        super().clear()
        self._revs.clear()
        self._activeRev = None
        self.update()

    def getFileBySHA1(self, sha1):
        if not sha1:
            return None

        for rev in self._revs:
            if rev.filename and rev.sha1 == sha1:
                return rev.filename
            if rev.prevFileName and rev.previous == sha1:
                return rev.prevFileName
        return None

    def setActiveRevByLineNumber(self, lineNo):
        if lineNo >= 0 and lineNo < len(self._revs):
            self._updateActiveRev(lineNo)

    def setActiveRevBySha1(self, sha1: str):
        for i, rev in enumerate(self._revs):
            if rev.sha1 == sha1:
                self._updateActiveRev(i)
                self._viewer.ensureLineVisible(i)
                return i

        # no rev found
        self._viewer.highlightLines([])
        self._activeRev = None
        self.update()

        return -1

    def _onTextLineClicked(self, textLine):
        self._updateActiveRev(textLine.lineNo())

    def _updateActiveRev(self, lineNo):
        rev = self._revs[lineNo]
        sha1 = rev.sha1
        if sha1 == self._activeRev:
            return

        self._activeRev = sha1

        lines = []
        for i in range(len(self._revs)):
            if self._revs[i].sha1 == sha1:
                lines.append(i)

        self._viewer.highlightLines(lines)
        self.update()

        self.revisionActivated.emit(rev)

    def _drawActiveRev(self, painter, lineNo, x, y):
        if self._activeRev and self._revs[lineNo].sha1 == self._activeRev:
            line = self.textLineAt(lineNo)
            br = line.boundingRect()
            fr = QRectF(br)
            fr.moveTop(fr.top() + y)
            fr.moveLeft(x)
            painter.fillRect(
                fr, ApplicationBase.instance().colorSchema().HighlightLineBg)

    def _reloadTextLine(self, textLine):
        textLine.setFont(self._font)

    def _fix_rev(self, rev):
        if rev.author:
            return
        for i in range(len(self._revs) - 1, -1, -1):
            r = self._revs[i]
            if r.sha1 == rev.sha1:
                rev.author = r.author
                rev.authorMail = r.authorMail
                rev.authorTime = r.authorTime
                rev.committer = r.committer
                rev.committerMail = r.committerMail
                rev.committerTime = r.committerTime
                rev.previous = r.previous
                rev.prevFileName = r.prevFileName
                rev.filename = r.filename
                break

    def _onMenuShowCommitLog(self):
        if self._hoveredLine == -1:
            return

        rev = self._revs[self._hoveredLine]
        event = ShowCommitEvent(rev.sha1)
        ApplicationBase.instance().postEvent(ApplicationBase.instance(), event)

    def _onMenuBlamePrevCommit(self):
        if self._hoveredLine == -1:
            return

        rev = self._revs[self._hoveredLine]
        if rev.previous:
            pass

        file = self.getFileBySHA1(rev.previous)
        event = BlameEvent(file, rev.previous,
                           rev.oldLineNo, self._viewer.repoDir)
        ApplicationBase.instance().postEvent(ApplicationBase.instance(), event)

    def paintEvent(self, event):
        painter = QPainter(self.viewport())

        eventRect = event.rect()
        painter.setClipRect(eventRect)
        painter.setFont(self._font)

        y = 0
        width = self.width()
        margin = self.textMargins()

        colorSchema = ApplicationBase.instance().colorSchema()

        textLineCount = self.textLineCount()
        digitCount = max(3, len(str(textLineCount)))
        x = width - digitCount * self._digitWidth - self._space * 2
        oldPen = painter.pen()
        painter.setPen(colorSchema.Splitter)
        painter.drawLine(x, y, x, self.height())
        painter.setPen(oldPen)

        maxLineWidth = x - self._space - margin

        if not self.hasTextLines():
            return

        startLine = self.firstVisibleLine()
        ascent = QFontMetrics(self._font).ascent()

        for i in range(startLine, textLineCount):
            line = self.textLineAt(i)

            lineClipRect = QRectF(0, y, maxLineWidth, self._viewer.lineHeight)
            painter.save()
            painter.setClipRect(lineClipRect)

            self._drawActiveRev(painter, i, 0, y)
            line.draw(painter, QPointF(0, y))

            painter.restore()

            lineNumber = str(i + 1)
            rect = QRect(x + self._space, y, width -
                         self._space * 2 - x, self._viewer.lineHeight)
            painter.setPen(colorSchema.LineNumber)
            painter.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, lineNumber)
            painter.setPen(oldPen)

            y += self._viewer.lineHeight
            if y > self.height():
                break

    def contextMenuEvent(self, event):
        textLine = self.textLineForPos(event.pos())
        if not textLine:
            return

        self._hoveredLine = textLine.lineNo()

        if not self._menu:
            self._menu = QMenu(self)
            self._menu.addAction(
                self.tr("Show commit log"),
                self._onMenuShowCommitLog)
            action = self._menu.addAction(
                self.tr("Blame previous commit"),
                self._onMenuBlamePrevCommit)
            self._acBlamePrevCommit = action

        rev = self._revs[self._hoveredLine]
        self._acBlamePrevCommit.setEnabled(rev.previous is not None)
        self._menu.exec(event.globalPos())

    def update(self):
        self.viewport().update()
        super().update()
