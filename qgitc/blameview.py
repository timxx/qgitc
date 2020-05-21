# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QAbstractScrollArea,
    QMainWindow,
    QWidget,
    QVBoxLayout)
from PySide2.QtGui import (
    QPainter,
    QFontMetrics)
from PySide2.QtCore import (
    Signal)

from datetime import datetime
from .datafetcher import DataFetcher
from .stylehelper import dpiScaled

import sys
import re


__all__ = ["BlameView", "BlameWindow"]

line_begin_re = re.compile(rb"(^[a-z0-9]{40}) (\d+) (\d+)( (\d+))?$")


class BlameLine:

    def __init__(self):
        self.sha1 = None
        self.oldLineNo = 0
        self.newLineNo = 0
        self.groupLines = 0
        self.text = None


class AuthorInfo:

    def __init__(self):
        self.name = None
        self.mail = None
        self.time = None

    def isValid(self):
        return self.name and \
            self.mail and \
            self.time

class BlameCommit:

    def __init__(self):
        self.author = AuthorInfo()
        self.committer = AuthorInfo()
        self.summary = None
        self.previous = None


def _timeStr(data):
    dt = datetime.fromtimestamp(float(data))
    return "%d-%02d-%02d %02d:%02d:%02d" % (
        dt.year, dt.month, dt.day,
        dt.hour, dt.minute, dt.second)


class BlameFetcher(DataFetcher):

    lineAvailable = Signal(BlameLine)
    commitAvailable = Signal(str, BlameCommit)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curLine = BlameLine()
        self._curCommit = BlameCommit()

    def parse(self, data):
        lines = data.split(self.separator)
        for line in lines:
            if line.startswith(b"\t"):
                self._curLine.text = line[1:].decode("utf-8")
                self.lineAvailable.emit(self._curLine)

                if self._curCommit.author.isValid():
                    self.commitAvailable.emit(
                        self._curLine.sha1,
                        self._curCommit)

                self._curLine = BlameLine()
                self._curCommit = BlameCommit()
            elif line.startswith(b"author "):
                self._curCommit.author.name = line[7:].decode("utf-8")
            elif line.startswith(b"author-mail "):
                self._curCommit.author.mail = line[12:].decode("utf-8")
            elif line.startswith(b"author-time "):
                self._curCommit.author.time = _timeStr(line[12:])
            elif line.startswith(b"author-tz "):
                assert(self._curCommit.author.time is not None)
                self._curCommit.author.time += line[9:].decode("utf-8")
            elif line.startswith(b"committer "):
                self._curCommit.committer.name = line[10:].decode("utf-8")
            elif line.startswith(b"committer-mail "):
                self._curCommit.committer.mail = line[15:].decode("utf-8")
            elif line.startswith(b"committer-time "):
                self._curCommit.committer.time = _timeStr(line[15:])
            elif line.startswith(b"committer-tz "):
                assert(self._curCommit.committer.time is not None)
                self._curCommit.committer.time += line[12:].decode("utf-8")
            elif line.startswith(b"summary "):
                self._curCommit.summary = line[8:].decode("utf-8")
            elif line.startswith(b"previous "):
                self._curCommit.previous = line.split(b' ')[1].decode("utf-8")
            elif line.startswith(b"filename "):
                pass
            else:
                m = line_begin_re.match(line)
                if m:
                    self._curLine.sha1 = m.group(1).decode("utf-8")
                    self._curLine.oldLineNo = int(m.group(2))
                    self._curLine.newLineNo = int(m.group(3))
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
        self._curCommit = BlameCommit()


class BlameView(QAbstractScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines = []
        self._commits = {}

    def appendLine(self, line):
        self._lines.append(line)
        self.viewport().update()

    def addCommit(self, sha1, info):
        self._commits[sha1] = info

    def clear(self):
        self._lines.clear()
        self._commits.clear()
        self.viewport().update()

    def paintEvent(self, event):
        if not self._lines:
            return

        painter = QPainter(self.viewport())

        # TEMP CODE
        fm = QFontMetrics(painter.font())
        y = fm.height()
        for line in self._lines:
            painter.drawText(0, y, line.text)
            y += fm.height()


class BlameWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("QGitc Blame"))

        self._view = BlameView(self)
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.addWidget(self._view)
        margin = dpiScaled(5)
        layout.setContentsMargins(margin, margin, margin, margin)
        self.setCentralWidget(widget)

        self._fetcher = BlameFetcher(self)
        self._fetcher.lineAvailable.connect(
            self._view.appendLine)
        self._fetcher.commitAvailable.connect(
            self._view.addCommit)

    def blame(self, file, sha1=None):
        self._view.clear()
        self._fetcher.fetch(file, sha1)
