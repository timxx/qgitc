# -*- coding: utf-8 -*-

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QPainter, QPen

from qgitc.applicationbase import ApplicationBase
from qgitc.blameline import BlameLine
from qgitc.common import decodeFileData
from qgitc.events import BlameEvent, ShowCommitEvent
from qgitc.revisionpanel import RevisionPanel
from qgitc.sourceviewer import SourceViewer


class BlameSourceViewer(SourceViewer):

    revisionActivated = Signal(BlameLine)
    currentLineChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPanel(RevisionPanel(self))

        self._panel.revisionActivated.connect(
            self.revisionActivated)
        self._panel.linkActivated.connect(
            self.linkActivated)

        self._curIndexForMenu = -1
        self._preferEncoding = "utf-8"
        self._detected = False
        self.repoDir: str = None

    def clear(self):
        super().clear()
        self._panel.clear()
        self._detected = False

    def beginReading(self):
        super().beginReading()
        self._panel.beginReading()

    def endReading(self):
        super().endReading()
        self._panel.endReading()

    def toTextLine(self, data):
        if not self._detected:
            self._preferEncoding = self._detectEncoding(data)
            self._detected = True

        text, encoding = decodeFileData(data, self._preferEncoding)
        if encoding:
            self._preferEncoding = encoding
        return super().toTextLine(text)

    def createContextMenu(self):
        menu = super().createContextMenu()
        menu.addSeparator()
        menu.addAction(
            self.tr("Show commit log"),
            self._onMenuShowCommitLog)
        self._acBlamePrev = menu.addAction(
            self.tr("Blame previous commit"),
            self._onMenuBlamePrevCommit)
        return menu

    def updateContextMenu(self, pos):
        super().updateContextMenu(pos)

        enabled = False
        textLine = self.textLineForPos(pos)
        if textLine:
            self._curIndexForMenu = textLine.lineNo()
            rev = self._panel.revisions[textLine.lineNo()]
            enabled = rev.previous is not None
        else:
            self._curIndexForMenu = -1
        self._acBlamePrev.setEnabled(enabled)

    def appendBlameLines(self, lines):
        texts = []
        for line in lines:
            texts.append(line.text)
            # to save memory as revision panel no need text
            line.text = None

        self._panel.appendRevisions(lines)
        self.appendLines(texts)

    def _onMenuShowCommitLog(self):
        if self._curIndexForMenu == -1:
            return

        rev = self._panel.revisions[self._curIndexForMenu]
        event = ShowCommitEvent(rev.sha1)
        ApplicationBase.instance().postEvent(ApplicationBase.instance(), event)

    def _onMenuBlamePrevCommit(self):
        if self._curIndexForMenu == -1:
            return

        rev = self._panel.revisions[self._curIndexForMenu]
        if rev.previous:
            pass

        file = self._panel.getFileBySHA1(rev.previous)
        event = BlameEvent(file, rev.previous, rev.oldLineNo, self.repoDir)
        ApplicationBase.instance().postEvent(ApplicationBase.instance(), event)

    def _lineRect(self, lineNo):
        firstLine = self.firstVisibleLine()
        if lineNo < firstLine:
            return QRect()
        if lineNo > firstLine + self._linesPerPage():
            return QRect()

        offset = self.contentOffset()
        offset.setY(offset.y() + (lineNo - firstLine) * self._lineHeight)

        textLine = self.textLineAt(self._cursor.beginLine())
        lineRect = textLine.boundingRect()
        lineRect.translate(offset)
        lineRect.setRight(self.viewport().rect().width()
                          - offset.x()
                          - 1)

        return lineRect.toRect()

    def _detectEncoding(self, data):
        if len(data) < 4:
            return "utf-8"

        b1 = data[0]
        b2 = data[1]
        b3 = data[2]
        b4 = data[3]
        if b1 == 0xFE and b2 == 0xFF:
            return "utf-16be"
        elif b1 == 0xFF and b2 == 0xFE:
            return "utf-16le"
        elif b1 == 0xEF and b2 == 0xBB and b3 == 0xBF:
            return "utf-8"
        elif b1 == 0x00 and b2 == 0x00 and b3 == 0xFE and b4 == 0xFF:
            return "utf-32be"
        elif b1 == 0xFF and b2 == 0xFE and b3 == 0x00 and b4 == 0x00:
            return "utf-32le"

        return "utf-8"

    def mousePressEvent(self, event):
        oldLine = self._cursor.beginLine()
        super().mousePressEvent(event)
        if not self._cursor.isValid():
            return
        if self._cursor.hasSelection():
            return

        newLine = self._cursor.endLine()
        if newLine == oldLine:
            return
        r = self._lineRect(oldLine)
        # if line contains invalid char
        # offset <= 2 is not working as the paintEvent rect
        # is not high enough for repaint
        # even if the update rect seems OK LoL
        offset = 3
        self.viewport().update(r.adjusted(-offset, -offset, offset, offset))
        r = self._lineRect(newLine)
        offset = 1
        self.viewport().update(r.adjusted(-offset, -offset, offset, offset))

        self.currentLineChanged.emit(newLine)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._cursor.isValid() and \
                not self._cursor.hasSelection():
            lineNo = self._cursor.beginLine()
            lineRect = self._lineRect(lineNo)
            if not lineRect.isValid():
                return

            painter = QPainter(self.viewport())
            pen = QPen(Qt.gray)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawRect(lineRect.adjusted(1, 0, 0, 0))
