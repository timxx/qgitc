# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QAbstractScrollArea,
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
    QTextFormat,
    QTextCursor,
    QColor,
    QPen,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextBlockUserData,
    QDesktopServices)
from PySide2.QtCore import (
    Qt,
    Signal,
    QRect,
    QRectF,
    QPointF,
    QUrl)

from datetime import datetime
from .datafetcher import DataFetcher
from .stylehelper import dpiScaled
from .sourceviewer import SourceViewer, SourcePanel
from .textline import TextLine, Link
from .gitutils import Git
from .colorschema import ColorSchema

import sys
import re


__all__ = ["BlameView"]

line_begin_re = re.compile(rb"(^[a-z0-9]{40}) (\d+) (\d+)( (\d+))?$")
ABBREV_N = 4


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
        self.prevFileName = None
        self.filename = None


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
                parts = line.split(b' ')
                self._curLine.header.previous = _decode(parts[1])
                self._curLine.header.prevFileName = _decode(parts[2])
            elif line.startswith(b"filename "):
                self._curLine.header.filename = _decode(line[9:])
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
        self._dateWidth = fm.horizontalAdvance("2020-05-27")
        self._space = fm.horizontalAdvance(' ')
        self._digitWidth = fm.horizontalAdvance('9')
        self._nameWidth = 0

        self._activeRev = None
        self._sha1Pattern = re.compile(r"^[a-f0-9]{%s}" % ABBREV_N)

        viewer.textLineClicked.connect(
            self._onTextLineClicked)

    def appendRevision(self, rev):
        if not self._revs or self._revs[len(self._revs) - 1].sha1 != rev.sha1:
            text = rev.sha1[:ABBREV_N] + " "
            if rev.author.isValid():
                text += rev.author.time.split(" ")[0]
                text += " " + rev.author.name

                fm = QFontMetrics(self._font)
                width = fm.horizontalAdvance(rev.author.name)
                self._nameWidth = max(width, self._nameWidth)
            else:
                # Get from the previous
                for i in range(len(self._revs), 0, -1):
                    r = self._revs[i - 1]
                    if r.sha1 == rev.sha1 and r.author.isValid():
                        text += r.author.time.split(" ")[0]
                        text += " " + r.author.name
                        break

            textLine = TextLine(TextLine.Parent, text,
                                self._font, self._option)
            textLine.setCustomLinkPatterns({Link.Sha1: self._sha1Pattern})
        else:
            textLine = None

        self._revs.append(rev)
        self._lines.append(textLine)
        self.update()

    @property
    def revisions(self):
        return self._revs

    def clear(self):
        self._revs.clear()
        self._lines.clear()
        self._activeRev = None
        self._nameWidth = 0
        self.update()

    def requestWidth(self, lineCount):
        width = self._sha1Width + self._space * 6
        width += self._dateWidth
        width += self._nameWidth
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

    def _drawActiveRev(self, painter, lineNo, x, y):
        if self._activeRev and self._revs[lineNo].sha1 == self._activeRev:
            line = self._lines[lineNo]
            br = line.boundingRect()
            fr = QRectF(br)
            fr.moveTop(fr.top() + y)
            fr.moveLeft(x)
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

        x_hline = (self._space + self._sha1Width) / 2
        for i in range(startLine, len(self._lines)):
            line = self._lines[i]
            if line:
                self._drawActiveRev(painter, i, self._space, y)
                line.draw(painter, QPointF(self._space, y))
            else:
                if self._activeRev and self._revs[i].sha1 == self._activeRev:
                    painter.setPen(Qt.darkGreen)
                else:
                    painter.setPen(pen)
                painter.drawLine(x_hline, y, x_hline, y + self._viewer.lineHeight)
                painter.setPen(oldPen)

            lineNumber = str(i + 1)
            x = width - len(lineNumber) * self._digitWidth - self._space
            painter.setPen(pen)
            painter.drawText(x, y + ascent, lineNumber)
            painter.setPen(oldPen)

            y += self._viewer.lineHeight
            if y > self.height():
                break


class CommitBlockData(QTextBlockUserData):

    def __init__(self, links):
        super().__init__()
        self.links = links


class CommitSyntaxHighlighter(QSyntaxHighlighter):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._linkFmt = QTextCharFormat()
        self._linkFmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        self._linkFmt.setForeground(ColorSchema.Link)

        self._patterns = TextLine.builtinPatterns()

    def highlightBlock(self, text):
        if not text:
            return

        links = TextLine.findLinks(text, self._patterns)
        for link in links:
            self.setFormat(link.start, link.end - link.start, self._linkFmt)
        if links:
            self.setCurrentBlockUserData(CommitBlockData(links))

class CommitPanel(QPlainTextEdit):

    linkActivated = Signal(Link)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(qApp.settings().diffViewFont())
        self.viewport().setMouseTracking(True)

        self._highlighter = CommitSyntaxHighlighter(self.document())
        self._bodyCache = {}
        self._clickOnLink = False

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

        if rev.previous:
            text = self.tr("Previous: ") + rev.previous
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

    def clear(self):
        super().clear()
        self._bodyCache.clear()

    def _linkForPosition(self, pos):
        cursor = self.cursorForPosition(pos)
        if cursor.isNull():
            return None

        if cursor.atBlockEnd():
            rc = self.cursorRect(cursor)
            if pos.x() > rc.right():
                return None

        block = cursor.block()
        blockData = block.userData()
        if not blockData:
            return None

        pos = cursor.position() - block.position()
        for link in blockData.links:
            if link.hitTest(pos):
                return link

        return None

    def mouseMoveEvent(self, event):
        self._link = self._linkForPosition(event.pos())
        self._clickOnLink = False

        cursorShape = Qt.PointingHandCursor if self._link \
            else Qt.IBeamCursor
        self.viewport().setCursor(cursorShape)

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._clickOnLink = self._link is not None

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and \
                self._link and self._clickOnLink:
            self.linkActivated.emit(self._link)

        self._clickOnLink = False
        super().mouseReleaseEvent(event)


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

        self._file = None
        self._sha1 = None

        self._fetcher = BlameFetcher(self)
        self._fetcher.lineAvailable.connect(
            self.appendLine)

        self._revPanel.revisionActivated.connect(
            self._commitPanel.showRevision)
        self._commitPanel.linkActivated.connect(
            self._onLinkActivated)

    def _onLinkActivated(self, link):
        url = None
        if link.type == Link.Sha1:
            if self._sha1 != link.data:
                file = self._findFileBySHA1(link.data)
                self.blame(file, link.data)
        elif link.type == Link.Email:
            url = "mailto:" + link.data
        elif link.type == Link.BugId:
            pass
        else:
            url = link.data

        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _findFileBySHA1(self, sha1):
        if not sha1:
            return self._file

        for rev in self._revPanel.revisions:
            if rev.filename and rev.sha1 == sha1:
                return rev.filename
            if rev.prevFileName and rev.previous == sha1:
                return rev.prevFileName
        return self._file

    def appendLine(self, line):
        self._revPanel.appendRevision(line.header)
        self._viewer.appendLine(line.text)

    def clear(self):
        self._revPanel.clear()
        self._viewer.clear()
        self._commitPanel.clear()

    def blame(self, file, sha1=None):
        self.clear()
        self._fetcher.fetch(file, sha1)
        text = file
        if sha1:
            text += " --- " + sha1
        self._lbHeader.setText(text)

        self._file = file
        self._sha1 = sha1

    @property
    def viewer(self):
        return self._viewer
