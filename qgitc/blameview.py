# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QAbstractScrollArea,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit)
from PySide2.QtGui import (
    QPainter,
    QFontMetrics,
    QTextOption,
    QTextLayout,
    QTextFormat,
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
                self._curLine.header.previous = _decode(line.split(b' ')[1][:ABBREV_N])
            elif line.startswith(b"filename "):
                pass
            else:
                m = line_begin_re.match(line)
                if m:
                    self._curLine.header.sha1 = _decode(m.group(1)[:ABBREV_N])
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

    def __init__(self, viewer):
        super().__init__(viewer, viewer)
        self._lines = []
        self._font = qApp.settings().diffViewFont()
        self._option = QTextOption()
        self._option.setWrapMode(QTextOption.NoWrap)

        fm = QFontMetrics(self._font)
        self._sha1Width = fm.horizontalAdvance('a') * ABBREV_N
        self._space = fm.horizontalAdvance(' ')
        self._digitWidth = fm.horizontalAdvance('9')

    def appendRevision(self, rev):
        if rev.author.isValid():
            text = rev.sha1
            textLine = TextLine(TextLine.Parent, text,
                                self._font, self._option)
        else:
            textLine = None
        self._lines.append(textLine)
        self.update()

    def clear(self):
        self._lines.clear()
        self.update()

    def requestWidth(self, lineCount):
        width = self._sha1Width + self._space * 3
        width += self._digitWidth * len(str(lineCount + 1))

        return width

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
                line.draw(painter, QPointF(0, y))

            lineNumber = str(i + 1)
            x = width - len(lineNumber) * self._digitWidth - self._space
            painter.setPen(pen)
            painter.drawText(x, y + ascent, lineNumber)
            painter.setPen(oldPen)

            y += self._viewer.lineHeight
            if y > self.height():
                break


class BlameView(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines = []
        self._commits = {}

        layout = QHBoxLayout(self)
        layout.setMargin(0)

        self._viewer = SourceViewer(self)
        self._revPanel = RevisionPanel(self._viewer)
        self._viewer.setPanel(self._revPanel)

        layout.addWidget(self._viewer)

    def appendLine(self, line):
        self._lines.append(line)
        self._revPanel.appendRevision(line.header)
        self._viewer.appendLine(line.text)

    def clear(self):
        self._lines.clear()
        self._commits.clear()

        self._revPanel.update()
        self._viewer.update()


class BlameWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("QGitc Blame"))

        self._view = BlameView(self)
        self.setCentralWidget(self._view)

        self._fetcher = BlameFetcher(self)
        self._fetcher.lineAvailable.connect(
            self._view.appendLine)

    def blame(self, file, sha1=None):
        self._view.clear()
        self._fetcher.fetch(file, sha1)
