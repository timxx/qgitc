# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QAbstractScrollArea,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter)
from PySide2.QtGui import (
    QPainter,
    QFontMetrics,
    QTextOption,
    QTextLayout,
    QTextFormat,
    QTextCursor,
    QColor,
    QPen)
from PySide2.QtCore import (
    Qt,
    Signal,
    QRect,
    QRectF,
    QSize,
    QPointF)

from datetime import datetime
from .datafetcher import DataFetcher
from .stylehelper import dpiScaled
from .sourceviewer import SourceViewer, SourcePanel
from .textline import TextLine
from .gitutils import Git

import sys
import re


__all__ = ["BlameView", "BlameWindow"]

line_begin_re = re.compile(rb"(^[a-z0-9]{40}) (\d+) (\d+)( (\d+))?$")
ABBREV_N = 8


class AuthorInfo:

    def __init__(self):
        self.name = None
        self.mail = None
        self.time = None

    def isValid(self):
        return self.name and \
            self.mail and \
            self.time


class BlameHeader:

    def __init__(self):
        self.sha1 = None
        self.oldLineNo = 0
        self.newLineNo = 0
        self.groupLines = 0
        self.author = AuthorInfo()
        self.committer = AuthorInfo()
        self.summary = None
        self.previous = None


class BlameLine:

    def __init__(self):
        self.header = BlameHeader()
        self.text = None


def _timeStr(data):
    dt = datetime.fromtimestamp(float(data))
    return "%d-%02d-%02d %02d:%02d:%02d" % (
        dt.year, dt.month, dt.day,
        dt.hour, dt.minute, dt.second)


def _decode(data):
    return data.decode("utf-8")


class BlameFetcher(DataFetcher):

    lineAvailable = Signal(BlameLine)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curLine = BlameLine()

    def parse(self, data):
        lines = data.split(self.separator)
        for line in lines:
            if line.startswith(b"\t"):
                self._curLine.text = _decode(line[1:])
                self.lineAvailable.emit(self._curLine)
                self._curLine = BlameLine()
            elif line.startswith(b"author "):
                self._curLine.header.author.name = _decode(line[7:])
            elif line.startswith(b"author-mail "):
                self._curLine.header.author.mail = _decode(line[12:])
            elif line.startswith(b"author-time "):
                self._curLine.header.author.time = _timeStr(line[12:])
            elif line.startswith(b"author-tz "):
                assert(self._curLine.header.author.time is not None)
                self._curLine.header.author.time += _decode(line[9:])
            elif line.startswith(b"committer "):
                self._curLine.header.committer.name = _decode(line[10:])
            elif line.startswith(b"committer-mail "):
                self._curLine.header.committer.mail = _decode(line[15:])
            elif line.startswith(b"committer-time "):
                self._curLine.header.committer.time = _timeStr(line[15:])
            elif line.startswith(b"committer-tz "):
                assert(self._curLine.header.committer.time is not None)
                self._curLine.header.committer.time += _decode(line[12:])
            elif line.startswith(b"summary "):
                self._curLine.header.summary = _decode(line[8:])
            elif line.startswith(b"previous "):
                self._curLine.header.previous = _decode(line.split(b' ')[1])
            elif line.startswith(b"filename "):
                pass
            else:
                m = line_begin_re.match(line)
                if m:
                    self._curLine.header.sha1 = _decode(m.group(1))
                    self._curLine.header.oldLineNo = int(m.group(2))
                    self._curLine.header.newLineNo = int(m.group(3))
                    if m.group(5):
                        self._curLine.groupLines = int(m.group(5))

    def makeArgs(self, args):
        file = args[0]
        sha1 = args[1]
        blameArgs = ["blame", "--porcelain", file]
        if sha1:
            blameArgs.append(sha1)

        return blameArgs

    def reset(self):
        self._curLine = BlameLine()


class RevisionPanel(SourcePanel):

    revisionActivated = Signal(BlameHeader)

    def __init__(self, viewer):
        super().__init__(viewer, viewer)
        self._lines = []
        self._revs = []
        self._font = qApp.settings().diffViewFont()
        self._option = QTextOption()
        self._option.setWrapMode(QTextOption.NoWrap)

        fm = QFontMetrics(self._font)
        self._sha1Width = fm.horizontalAdvance('a') * ABBREV_N
        self._space = fm.horizontalAdvance(' ')
        self._digitWidth = fm.horizontalAdvance('9')

        self._activeRev = None

        viewer.textLineClicked.connect(
            self._onTextLineClicked)

    def appendRevision(self, rev):
        if rev.author.isValid():
            text = rev.sha1[:ABBREV_N]
            textLine = TextLine(TextLine.Parent, text,
                                self._font, self._option)
        else:
            textLine = None
        self._revs.append(rev)
        self._lines.append(textLine)
        self.update()

    def clear(self):
        self._revs.clear()
        self._lines.clear()
        self._activeRev = None
        self.update()

    def requestWidth(self, lineCount):
        width = self._sha1Width + self._space * 3
        width += self._digitWidth * len(str(lineCount + 1))

        return width

    def _onTextLineClicked(self, textLine):
        rev = self._revs[textLine.lineNo()]
        sha1 = rev.sha1
        if sha1 == self._activeRev:
            return

        self._activeRev = sha1

        lines = []
        for i in range(len(self._revs)):
            if self._revs[i].sha1 == sha1:
                if self._revs[i].author.isValid():
                    rev = self._revs[i]
                lines.append(i)

        self._viewer.highlightLines(lines)
        self.update()

        self.revisionActivated.emit(rev)

    def _drawActiveRev(self, painter, lineNo, y):
        if self._activeRev and self._revs[lineNo].sha1 == self._activeRev:
            line = self._lines[lineNo]
            br = line.boundingRect()
            fr = QRectF(br)
            fr.moveTop(fr.top() + y)
            fr.setLeft(0)
            painter.fillRect(fr, QColor(192, 237, 197))

    def paintEvent(self, event):
        if not self._lines:
            return

        painter = QPainter(self)
        onePixel = dpiScaled(1)
        painter.fillRect(self.rect().adjusted(onePixel, onePixel, 0, 0),
                         QColor(250, 250, 250))

        eventRect = event.rect()
        painter.setClipRect(eventRect)
        painter.setFont(self._font)

        startLine = self._viewer.firstVisibleLine()

        y = 0
        width = self.width()
        ascent = QFontMetrics(self._font).ascent()

        x = width - len(str(len(self._lines))) * \
            self._digitWidth - self._space * 2
        pen = QPen(Qt.darkGray)
        oldPen = painter.pen()
        painter.setPen(pen)
        painter.drawLine(x, y, x, self.height())
        painter.setPen(oldPen)

        for i in range(startLine, len(self._lines)):
            line = self._lines[i]
            if line:
                self._drawActiveRev(painter, i, y)
                line.draw(painter, QPointF(0, y))

            lineNumber = str(i + 1)
            x = width - len(lineNumber) * self._digitWidth - self._space
            painter.setPen(pen)
            painter.drawText(x, y + ascent, lineNumber)
            painter.setPen(oldPen)

            y += self._viewer.lineHeight
            if y > self.height():
                break


class CommitPanel(QPlainTextEdit):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)

        self._bodyCache = {}

    def showRevision(self, rev):
        self.clear()
        text = self.tr("Commit: ") + rev.sha1
        self.appendPlainText(text)

        text = self.tr("Author: ") + rev.author.name + " " + \
            rev.author.mail + " " + rev.author.time
        self.appendPlainText(text)

        text = self.tr("Committer: ") + rev.committer.name + " " + \
            rev.committer.mail + " " + rev.committer.time
        self.appendPlainText(text)

        self.appendPlainText("")
        self.appendPlainText(rev.summary)

        if rev.sha1 in self._bodyCache:
            text = self._bodyCache[rev.sha1]
        else:
            args = ["show", "-s", "--pretty=format:%b", rev.sha1]
            data = Git.checkOutput(args)
            text = _decode(data) if data else None
            self._bodyCache[rev.sha1] = text
        if text:
            self.appendPlainText("")
            self.appendPlainText(text)

        self.moveCursor(QTextCursor.Start)

    def clearCache(self):
        self._bodyCache.clear()


class BlameView(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        mainLayout = QVBoxLayout(self)
        mainLayout.setMargin(0)

        sourceWidget = QWidget(self)
        layout = QVBoxLayout(sourceWidget)
        layout.setMargin(0)

        hdrLayout = QHBoxLayout()
        self._lbHeader = QLabel(self)
        hdrLayout.addWidget(self._lbHeader)
        layout.addLayout(hdrLayout)

        self._viewer = SourceViewer(self)
        self._revPanel = RevisionPanel(self._viewer)
        self._viewer.setPanel(self._revPanel)
        layout.addWidget(self._viewer)

        self._commitPanel = CommitPanel(self)

        vSplitter = QSplitter(Qt.Vertical, self)
        vSplitter.addWidget(sourceWidget)
        vSplitter.addWidget(self._commitPanel)

        height = vSplitter.sizeHint().height()
        sizes = [height * 4 / 5, height * 1 / 5]
        vSplitter.setSizes(sizes)

        mainLayout.addWidget(vSplitter)

        self._fetcher = BlameFetcher(self)
        self._fetcher.lineAvailable.connect(
            self.appendLine)

        self._revPanel.revisionActivated.connect(
            self._commitPanel.showRevision)

    def appendLine(self, line):
        self._revPanel.appendRevision(line.header)
        self._viewer.appendLine(line.text)

    def clear(self):
        self._revPanel.clear()
        self._viewer.clear()
        self._commitPanel.clearCache()

    def blame(self, file, sha1=None):
        self.clear()
        self._fetcher.fetch(file, sha1)
        text = file
        if sha1:
            text += " --- " + sha1
        self._lbHeader.setText(text)


class BlameWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("QGitc Blame"))

        centralWidget = QWidget(self)
        layout = QVBoxLayout(centralWidget)
        margin = dpiScaled(5)
        layout.setContentsMargins(margin, margin, margin, margin)

        self._view = BlameView(self)
        layout.addWidget(self._view)

        self.setCentralWidget(centralWidget)

    def blame(self, file, sha1=None):
        self._view.blame(file, sha1)
