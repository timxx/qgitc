# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QAbstractScrollArea,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSplitter,
    QToolButton,
    QSpacerItem,
    QSizePolicy,
    QMenu)
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
    QDesktopServices,
    QCursor)
from PySide2.QtCore import (
    Qt,
    Signal,
    QRect,
    QRectF,
    QPointF,
    QPoint,
    QUrl)

from datetime import datetime
from .datafetcher import DataFetcher
from .stylehelper import dpiScaled
from .sourceviewer import SourceViewer
from .textline import TextLine, Link
from .gitutils import Git
from .colorschema import ColorSchema
from .events import BlameEvent, ShowCommitEvent
from .waitingspinnerwidget import QtWaitingSpinner
from .textviewer import TextViewer

import sys
import re


__all__ = ["BlameView"]

ABBREV_N = 4


class BlameLine:

    def __init__(self):
        self.sha1 = None
        self.oldLineNo = 0
        self.newLineNo = 0
        self.groupLines = 0

        self.author = None
        self.authorMail = None
        self.authorTime = None

        self.committer = None
        self.committerMail = None
        self.committerTime = None

        self.summary = None
        self.previous = None
        self.prevFileName = None
        self.filename = None
        self.text = None


def _timeStr(data):
    dt = datetime.fromtimestamp(float(data))
    return "%d-%02d-%02d %02d:%02d:%02d" % (
        dt.year, dt.month, dt.day,
        dt.hour, dt.minute, dt.second)


def _decode(data):
    return data.decode("utf-8")


class BlameFetcher(DataFetcher):

    dataAvailable = Signal(BlameLine)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curLine = BlameLine()

    def parse(self, data):
        results = []
        lines = data.rstrip(self.separator).split(self.separator)
        for line in lines:
            if line[0] == 9:  # \t
                self._curLine.text = _decode(line[1:])
                results.append(self._curLine)
                self._curLine = BlameLine()
            elif line[0] == 97 and line[1] == 117:  # author
                if line[6] == 32:  # "author "
                    self._curLine.author = _decode(line[7:])
                elif line[7] == 109:  # "author-mail "
                    self._curLine.authorMail = _decode(line[12:])
                elif line[8] == 105:  # "author-time "
                    self._curLine.authorTime = _timeStr(line[12:])
                elif line[8] == 122:  # "author-tz "
                    assert(self._curLine.authorTime is not None)
                    self._curLine.authorTime += _decode(line[9:])
                else:
                    print("Invalid line:", line)
            elif line[0] == 99 and line[1] == 111:  # committer
                if line[9] == 32:  # "committer "
                    self._curLine.committer = _decode(line[10:])
                elif line[10] == 109:  # "committer-mail "
                    self._curLine.committerMail = _decode(line[15:])
                elif line[11] == 105:  # "committer-time "
                    self._curLine.committerTime = _timeStr(line[15:])
                elif line[11] == 122:  # "committer-tz "
                    assert(self._curLine.committerTime is not None)
                    self._curLine.committerTime += _decode(line[12:])
                else:
                    print("Invalid line:", line)
            elif line[0] == 115:  # "summary "
                self._curLine.summary = _decode(line[8:])
            elif line[0] == 112:  # "previous "
                parts = line.split(b' ')
                self._curLine.previous = _decode(parts[1])
                self._curLine.prevFileName = _decode(parts[2])
            elif line[0] == 102 and line[1] == 105:  # "filename "
                self._curLine.filename = _decode(line[9:])
            elif line[0] == 98 and line[1] == 111:  # boundary
                pass
            else:
                parts = line.split(b' ')
                if len(parts) < 3 or len(parts) > 4:
                    print("Invalid line:", line)
                else:
                    self._curLine.sha1 = _decode(parts[0])
                    self._curLine.oldLineNo = int(parts[1])
                    self._curLine.newLineNo = int(parts[2])
                    if len(parts) == 4:
                        self._curLine.groupLines = int(parts[3])

        self.dataAvailable.emit(results)

    def makeArgs(self, args):
        file = args[0]
        sha1 = args[1]
        blameArgs = ["blame", "--line-porcelain", file]
        if sha1:
            blameArgs.append(sha1)

        return blameArgs

    def reset(self):
        self._curLine = BlameLine()


class RevisionPanel(QWidget):

    revisionActivated = Signal(BlameLine)
    linkActivated = Signal(Link)

    def __init__(self, viewer):
        super().__init__(viewer)
        self._viewer = viewer
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
        self._maxNameWidth = 12 * fm.horizontalAdvance('W')

        width = self._sha1Width + self._space * 6
        width += self._dateWidth
        width += self._maxNameWidth
        width += self._digitWidth * 6
        self.resize(width, viewer.height())

        self._activeRev = None
        self._sha1Pattern = re.compile(r"^[a-f0-9]{%s}" % ABBREV_N)

        self._mousePressedPos = QPoint()
        self._clickOnLink = False
        self._link = None

        self._hoveredLine = -1

        self._menu = None

        self.setMouseTracking(True)

        viewer.textLineClicked.connect(
            self._onTextLineClicked)

    def appendRevision(self, rev):
        text = rev.sha1[:ABBREV_N]
        if not self._revs or self._revs[len(self._revs) - 1].sha1 != rev.sha1:
            text += " " + rev.authorTime.split(" ")[0]
            text += " " + rev.author

        textLine = TextLine(TextLine.Text, text,
                            self._font, self._option)
        textLine.setLineNo(len(self._lines))
        textLine.setCustomLinkPatterns({Link.Sha1: self._sha1Pattern})

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
            line = self._lines[lineNo]
            br = line.boundingRect()
            fr = QRectF(br)
            fr.moveTop(fr.top() + y)
            fr.moveLeft(x)
            painter.fillRect(fr, QColor(192, 237, 197))

    def _lineNoForPosition(self, pos):
        if not self._lines:
            return -1

        n = int(pos.y() / self._viewer.lineHeight)
        n += self._viewer.firstVisibleLine()
        if n >= len(self._lines):
            n = len(self._lines) - 1

        return n

    def _lineForPosition(self, pos):
        lineNo = self._lineNoForPosition(pos)
        if lineNo != -1:
            return self._lines[lineNo]
        return None

    def _linkForPosition(self, pos):
        # left margin
        if pos.x() < self._space:
            return None

        line = self._lineForPosition(pos)
        if not line:
            return None

        relPos = QPoint(pos.x() - self._space, pos.y())
        br = line.boundingRect()
        if br.right() < relPos.x():
            return None

        offset = line.offsetForPos(relPos)
        link = line.hitTest(offset)
        if link:
            link.setData(self._revs[line.lineNo()].sha1)
        return link

    def _onMenuShowCommitLog(self):
        if self._hoveredLine == -1:
            return

        rev = self._revs[self._hoveredLine]
        event = ShowCommitEvent(rev.sha1)
        qApp.postEvent(qApp, event)

    def _onMenuBlamePrevCommit(self):
        if self._hoveredLine == -1:
            return

        rev = self._revs[self._hoveredLine]
        if rev.previous:
            pass

        file = self.getFileBySHA1(rev.previous)
        event = BlameEvent(file, rev.previous, rev.oldLineNo)
        qApp.postEvent(qApp, event)

    def paintEvent(self, event):
        painter = QPainter(self)

        eventRect = event.rect()
        painter.setClipRect(eventRect)
        painter.setFont(self._font)

        onePixel = dpiScaled(1)
        painter.fillRect(self.rect().adjusted(onePixel, onePixel, 0, 0),
                         QColor(250, 250, 250))

        y = 0
        width = self.width()

        digitCount = max(3, len(str(len(self._lines))))
        x = width - digitCount * self._digitWidth - self._space * 2
        pen = QPen(Qt.darkGray)
        oldPen = painter.pen()
        painter.setPen(pen)
        painter.drawLine(x, y, x, self.height())
        painter.setPen(oldPen)

        maxLineWidth = x - self._space

        if not self._lines:
            return

        startLine = self._viewer.firstVisibleLine()
        ascent = QFontMetrics(self._font).ascent()

        for i in range(startLine, len(self._lines)):
            line = self._lines[i]

            lineClipRect = QRectF(0, y, maxLineWidth, self._viewer.lineHeight)
            painter.save()
            painter.setClipRect(lineClipRect)

            self._drawActiveRev(painter, i, self._space, y)
            line.draw(painter, QPointF(self._space, y))

            painter.restore()

            lineNumber = str(i + 1)
            x = width - len(lineNumber) * self._digitWidth - self._space
            painter.setPen(pen)
            painter.drawText(x, y + ascent, lineNumber)
            painter.setPen(oldPen)

            y += self._viewer.lineHeight
            if y > self.height():
                break

    def mouseMoveEvent(self, event):
        self._link = self._linkForPosition(event.pos())

        # Buggy tooltip cause mouseMove
        if event.pos() != self._mousePressedPos:
            self._mousePressedPos = QPoint()
            self._clickOnLink = False

        cursorShape = Qt.PointingHandCursor if self._link \
            else Qt.ArrowCursor
        self.setCursor(cursorShape)

        if event.button() == Qt.NoButton:
            lineNo = self._lineNoForPosition(event.pos())
            if lineNo != self._hoveredLine:
                self._hoveredLine = lineNo

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._clickOnLink = self._link is not None

        self._mousePressedPos = event.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._link and self._clickOnLink:
                self.linkActivated.emit(self._link)
            elif not self._mousePressedPos.isNull():
                lineNo = self._lineNoForPosition(event.pos())
                if lineNo != -1:
                    self._updateActiveRev(lineNo)

        self._clickOnLink = False
        self._mousePressedPos = QPoint()
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self._hoveredLine == -1:
            return

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
        self._menu.exec_(event.globalPos())


class CommitPanel(TextViewer):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.updateFont(qApp.settings().diffViewFont())
        self._bodyCache = {}

    def showRevision(self, rev):
        super().clear()

        text = self.tr("Commit: ") + rev.sha1
        self.appendLine(text)

        text = self.tr("Author: ") + rev.author + " " + \
            rev.authorMail + " " + rev.authorTime
        self.appendLine(text)

        text = self.tr("Committer: ") + rev.committer + " " + \
            rev.committerMail + " " + rev.committerTime
        self.appendLine(text)

        if rev.previous:
            text = self.tr("Previous: ") + rev.previous
            self.appendLine(text)

        self.appendLine("")
        self.appendLine(rev.summary)

        if rev.sha1 in self._bodyCache:
            text = self._bodyCache[rev.sha1]
        else:
            args = ["show", "-s", "--pretty=format:%b", rev.sha1]
            data = Git.checkOutput(args)
            text = _decode(data) if data else None
            self._bodyCache[rev.sha1] = text
        if text:
            self.appendLine("")
            text = text.rstrip('\n')
            for line in text.split('\n'):
                self.appendLine(line)

    def clear(self):
        super().clear()
        self._bodyCache.clear()


class HeaderWidget(QWidget):

    def __init__(self, view=None):
        super().__init__(view)

        self._view = view
        self._histories = []
        self._curIndex = 0
        self._blockAdd = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._btnPrev = QToolButton(self)
        layout.addWidget(self._btnPrev)

        self._btnNext = QToolButton(self)
        layout.addWidget(self._btnNext)

        self._waitingSpinner = QtWaitingSpinner(self)
        layout.addWidget(self._waitingSpinner)

        self._lbFile = QLabel(self)
        layout.addWidget(self._lbFile)

        self._lbSHA1 = QLabel(self)
        layout.addWidget(self._lbSHA1)
        layout.addSpacerItem(QSpacerItem(
            0, 0,
            QSizePolicy.Expanding,
            QSizePolicy.Fixed))

        self._btnPrev.setText("🡰")
        self._btnNext.setText("🡲")

        self._btnPrev.clicked.connect(
            self._onPrevious)
        self._btnNext.clicked.connect(
            self._onNext)

        height = self._lbFile.height() // 6
        self._waitingSpinner.setLineLength(height)
        self._waitingSpinner.setInnerRadius(height)
        self._waitingSpinner.setNumberOfLines(14)

        self._updateInfo()

    def _updateInfo(self):
        if not self._histories:
            file = ""
            sha1 = ""
        else:
            file, sha1 = self._histories[self._curIndex]
            if sha1 is None:
                sha1 = ""

        self._lbSHA1.setText(sha1)
        self._lbFile.setText(file)

        enablePrev = False
        enableNext = False

        total = len(self._histories)
        if total > 1:
            if self._curIndex != 0:
                enablePrev = True
            if self._curIndex != total - 1:
                enableNext = True
        self._btnPrev.setEnabled(enablePrev)
        self._btnNext.setEnabled(enableNext)

    def _blameCurrent(self):
        self._blockAdd = True
        file, sha1 = self._histories[self._curIndex]
        self._view.blame(file, sha1)
        self._blockAdd = False

    def _onPrevious(self):
        self._curIndex -= 1
        self._updateInfo()
        self._blameCurrent()

    def _onNext(self):
        self._curIndex += 1
        self._updateInfo()
        self._blameCurrent()

    def clear(self):
        self._histories.clear()
        self._updateInfo()

    def addBlameInfo(self, file, sha1):
        if self._blockAdd:
            return

        self._curIndex = len(self._histories)
        self._histories.append((file, sha1))
        self._updateInfo()

    def notifyFecthingStarted(self):
        self._waitingSpinner.start()

    def notifyFecthingFinished(self):
        self._waitingSpinner.stop()


class BlameView(QWidget):

    blameFileAboutToChange = Signal(str)
    blameFileChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        mainLayout = QVBoxLayout(self)
        mainLayout.setMargin(0)

        sourceWidget = QWidget(self)
        layout = QVBoxLayout(sourceWidget)
        layout.setMargin(0)

        self._headerWidget = HeaderWidget(self)
        layout.addWidget(self._headerWidget)

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
        self._lineNo = -1
        self._bugUrl = qApp.settings().bugUrl()

        self._fetcher = BlameFetcher(self)
        self._fetcher.dataAvailable.connect(
            self._onFetchDataAvailable)
        self._fetcher.fetchFinished.connect(
            self._onFetchFinished)

        self._revPanel.revisionActivated.connect(
            self._commitPanel.showRevision)
        self._commitPanel.linkActivated.connect(
            self._onLinkActivated)
        self._revPanel.linkActivated.connect(
            self._onLinkActivated)
        self._viewer.linkActivated.connect(
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
            if self._bugUrl:
                url = self._bugUrl + link.data
        else:
            url = link.data

        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _onFetchDataAvailable(self, lines):
        texts = []
        for line in lines:
            texts.append(line.text)
            # to save memory as revision panel no need text
            line.text = None
            self._revPanel.appendRevision(line)

        self._viewer.appendLines(texts)

    def _onFetchFinished(self):
        self.blameFileChanged.emit(self._file)
        self._headerWidget.notifyFecthingFinished()
        if self._lineNo > 0:
            self._viewer.gotoLine(self._lineNo - 1)
            self._lineNo = -1
        self._viewer.endReading()

    def _findFileBySHA1(self, sha1):
        file = self._revPanel.getFileBySHA1(sha1)
        return file if file else self._file

    def clear(self):
        self._revPanel.clear()
        self._viewer.clear()
        self._commitPanel.clear()

    def blame(self, file, sha1=None, lineNo=0):
        self._headerWidget.notifyFecthingStarted()
        self.blameFileAboutToChange.emit(file)
        self.clear()
        self._viewer.beginReading()
        self._fetcher.fetch(file, sha1)

        self._file = file
        self._sha1 = sha1
        self._lineNo = lineNo

        self._headerWidget.addBlameInfo(file, sha1)

    @property
    def viewer(self):
        return self._viewer
