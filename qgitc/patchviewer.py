# -*- coding: utf-8 -*-

from PySide6.QtCore import QRectF
from PySide6.QtGui import (
    QDesktopServices,
    QTextCharFormat,
    QBrush,
    QAction,
    QPainter,
    QFont,
    QFontMetricsF,
    QPen)
from PySide6.QtWidgets import (
    QApplication)
from PySide6.QtCore import (
    Signal,
    QUrl,
    QMimeData,
    QPointF)

from .common import Commit, FindField, decodeFileData
from .diffutils import *
from .events import OpenLinkEvent
from .findwidget import FindWidget
from .sourceviewer import SourceViewer
from .textline import Link, LinkTextLine, SourceTextLineBase, TextLine, createFormatRange
from .textviewer import FindPart


class DiffTextLine(SourceTextLineBase):

    def __init__(self, viewer, text, parentCount):
        super().__init__(text, viewer._font, viewer._option)
        self._parentCount = parentCount

    def rehighlight(self):
        text = self.text()

        formats = self._commonHighlightFormats()
        tcFormat = QTextCharFormat()
        if not text:
            pass
        elif text[0] == "+":
            if len(text) >= 2 and text[1] == "+":
                tcFormat.setFontWeight(QFont.Bold)
            else:
                tcFormat.setForeground(qApp.colorSchema().Adding)
        elif text[0] == "-":
            tcFormat.setForeground(qApp.colorSchema().Deletion)
        elif text[0] == " " and len(text) >= 2:
            # TODO: only if in submodule changes
            if text.startswith("  > "):
                tcFormat.setForeground(qApp.colorSchema().Submodule)
            elif text.startswith("  < "):
                tcFormat.setForeground(qApp.colorSchema().Submodule2)
            elif self._parentCount > 1 and len(text) >= self._parentCount:
                index = self._parentCount - 1
                if text[index] == "+":
                    tcFormat.setFontWeight(QFont.Bold)
                    tcFormat.setForeground(qApp.colorSchema().Adding)
                elif text[index] == "-":
                    tcFormat.setFontWeight(QFont.Bold)
                    tcFormat.setForeground(qApp.colorSchema().Deletion)
        elif diff_begin_re.search(text) or text.startswith(r"\ No newline "):
            tcFormat.setForeground(qApp.colorSchema().Newline)

        if tcFormat.isValid():
            formats.append(createFormatRange(0, len(text), tcFormat))

        if formats:
            self._layout.setFormats(formats)


class InfoTextLine(TextLine):

    def __init__(self, viewer, type, text):
        super(InfoTextLine, self).__init__(
            text, viewer._font)
        self._type = type
        self.useBuiltinPatterns = False

    def _findLinks(self, patterns):
        # do nothing
        pass

    def isFileInfo(self):
        return self._type == DiffType.FileInfo

    def isFile(self):
        return self._type == DiffType.File

    def rehighlight(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold)
        fmtRg = createFormatRange(0, len(self.text()), fmt)

        formats = []
        formats.append(fmtRg)

        self._layout.setFormats(formats)

    def _relayout(self):
        self._layout.beginLayout()
        line = self._layout.createLine()
        line.setPosition(QPointF(1, 0))
        self._layout.endLayout()

    def boundingRect(self):
        self.ensureLayout()
        br = self._layout.boundingRect()
        br.setWidth(br.width() + br.left())
        return br


class AuthorTextLine(LinkTextLine):

    def __init__(self, viewer, text):
        super().__init__(text, viewer._font, Link.Email)


class Sha1TextLine(LinkTextLine):

    def __init__(self, viewer, text, isParent):
        super().__init__(text, viewer._font, Link.Sha1)
        self._isParent = isParent

    def isParent(self):
        return self._isParent


class SummaryTextLine(TextLine):

    def __init__(self, text, font, option=None):
        super().__init__(text, font, option)

    def _relayout(self):
        self._layout.beginLayout()
        line = self._layout.createLine()
        width = QFontMetricsF(self._font).averageCharWidth() * 4
        line.setPosition(QPointF(width, 0))
        self._layout.endLayout()

    def boundingRect(self):
        self.ensureLayout()
        br = self._layout.boundingRect()
        # since we adjust the line position
        # we need to adjust the bounding rect too
        br.setWidth(br.width() + br.left())
        return br

    def rehighlight(self):
        super().rehighlight()

        ranges = []
        text: str = self.text()
        start = 0
        while start < len(text):
            start = text.find('`', start)
            if start == -1:
                break

            end = text.find('`', start + 1)
            if end == -1:
                break

            ranges.append((start, end - start + 1))
            start = end + 1

        if not ranges:
            return

        formats = self._layout.formats()
        fmt = QTextCharFormat()
        fmt.setForeground(qApp.colorSchema().InlineCode)
        for start, length in ranges:
            fmtRg = createFormatRange(start, length, fmt)
            formats.append(fmtRg)

        self._layout.setFormats(formats)


class PatchViewer(SourceViewer):
    fileRowChanged = Signal(int)
    requestCommit = Signal(str, bool, bool)
    requestBlame = Signal(str, bool, Commit)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.highlightPattern = None
        self.highlightField = FindField.Comments

        self.findWidget = None
        self.curIndexFound = False

        self._parentCount = 1

        self.verticalScrollBar().valueChanged.connect(
            self._onVScollBarValueChanged)
        self.linkActivated.connect(self._onLinkActivated)
        self.findResultAvailable.connect(self._onFindResultAvailable)

    def endReading(self):
        super().endReading()
        if self.findWidget and self.findWidget.isVisible():
            # redo a find
            self._onFind(self.findWidget.text, self.findWidget.flags)

    def toTextLine(self, item):
        type, content = item

        # alloc too many objects at the same time is too slow
        # so delay construct TextLine and decode bytes here
        if type == DiffType.Diff:
            text, _ = decodeFileData(content, diff_encoding)
            # FIXME: The git may generate some patch with \x00 char (such as: b'- \x00')
            # The origin file is a normal text file and not Unicode encoding
            textLine = DiffTextLine(self, text.replace(
                '\x00', ''), self._parentCount)
        elif type == DiffType.File or \
                type == DiffType.FileInfo:
            textLine = InfoTextLine(self, type, content.decode(diff_encoding))
        else:
            assert (False)

        return textLine

    def addAuthorLine(self, name):
        textLine = AuthorTextLine(self, name)
        self.appendTextLine(textLine)

    def addSHA1Line(self, content, isParent):
        textLine = Sha1TextLine(self, content, isParent)
        self.appendTextLine(textLine)

    def addNormalTextLine(self, text, useBuiltinPatterns=True):
        textLine = TextLine(text, self._font)
        textLine.useBuiltinPatterns = useBuiltinPatterns
        self.appendTextLine(textLine)

    def addSummaryTextLine(self, text):
        textLine = SummaryTextLine(text, self._font)
        textLine.useBuiltinPatterns = True
        self.appendTextLine(textLine)

    def drawLineBackground(self, painter: QPainter, textLine, lineRect):
        if isinstance(textLine, InfoTextLine):
            painter.fillRect(lineRect, qApp.colorSchema().InfoBg)

    def canDrawLineBorder(self, textLine):
        return isinstance(textLine, InfoTextLine)

    def drawLinesBorder(self, painter: QPainter, rect: QRectF):
        oldPen = painter.pen()
        pen = QPen(qApp.colorSchema().InfoBorder)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(rect.adjusted(0.5, 0, -0.5, -0.5))
        painter.setPen(oldPen)

    def textLineFormatRange(self, textLine):
        formats = []

        if isinstance(textLine, DiffTextLine):
            fmt = self._createDiffFormats(textLine)
            if fmt:
                formats.extend(fmt)
        elif isinstance(textLine, InfoTextLine):
            fmt = QTextCharFormat()
            fmt.setForeground(QBrush(qApp.colorSchema().InfoFg))
            formats.append(createFormatRange(0, len(textLine.text()), fmt))
        else:
            fmt = self._createCommentsFormats(textLine)
            if fmt:
                formats.extend(fmt)

        return formats

    def createContextMenu(self):
        menu = super().createContextMenu()
        action = QAction(self.tr("Copy Plain &Text"), self)
        action.triggered.connect(self.copyPlainText)
        menu.insertAction(self._acCopy, action)
        menu.removeAction(self._acCopy)
        menu.insertAction(action, self._acCopy)

        menu.addSeparator()

        self._acOpenCommit = menu.addAction(
            self.tr("&Open commit in browser"), self._onOpenCommit)

        return menu

    def updateContextMenu(self, pos):
        enabled = False
        if self._link is not None:
            enabled = self._link.type == Link.Sha1

        self._acOpenCommit.setEnabled(enabled)

    def updateLinkData(self, link, lineNo):
        if link.type == Link.Sha1:
            textLine = self.textLineAt(lineNo)
            if isinstance(textLine, Sha1TextLine):
                if not isinstance(link.data, tuple):
                    link.data = (link.data, textLine.isParent())

    def highlightKeyword(self, pattern, field):
        self.highlightPattern = pattern
        self.highlightField = field
        self.viewport().update()

    def hasSelection(self):
        return self._cursor.hasSelection()

    def executeFind(self):
        if not self.findWidget:
            self.findWidget = FindWidget(self.viewport(), self)
            self.findWidget.find.connect(self._onFind)
            self.findWidget.cursorChanged.connect(
                self._onFindCursorChanged)
            self.findWidget.afterHidden.connect(
                self._onFindHidden)
            self.findFinished.connect(
                self.findWidget.findFinished)

        text = self.selectedText
        if text:
            # first line only
            text = text.lstrip('\n')
            index = text.find('\n')
            if index != -1:
                text = text[:index]
            self.findWidget.setText(text)
        self.findWidget.showAnimate()

    def setParentCount(self, n):
        self._parentCount = n

    def _highlightFormatRange(self, text):
        formats = []
        if self.highlightPattern:
            matchs = self.highlightPattern.finditer(text)
            fmt = QTextCharFormat()
            fmt.setBackground(QBrush(qApp.colorSchema().HighlightWordBg))
            for m in matchs:
                rg = createFormatRange(m.start(), m.end() - m.start(), fmt)
                formats.append(rg)
        return formats

    def _createCommentsFormats(self, textLine):
        if self.highlightField == FindField.Comments or \
                self.highlightField == FindField.All:
            return self._highlightFormatRange(textLine.text())

        return None

    def _createDiffFormats(self, textLine):
        if self.highlightField == FindField.All:
            return self._highlightFormatRange(textLine.text())
        elif FindField.isDiff(self.highlightField):
            text = textLine.text().lstrip()
            if text.startswith('+') or text.startswith('-'):
                return self._highlightFormatRange(textLine.text())

        return None

    def _onVScollBarValueChanged(self, value):
        if not self.hasTextLines():
            return

        # TODO: improve
        for i in range(value, -1, -1):
            textLine = self.textLineAt(i)
            if isinstance(textLine, InfoTextLine) and textLine.isFile():
                self.fileRowChanged.emit(i)
                break
            elif isinstance(textLine, AuthorTextLine) or \
                    (isinstance(textLine, Sha1TextLine) and textLine.isParent()):
                self.fileRowChanged.emit(0)
                break

    def _onOpenCommit(self):
        sett = qApp.settings()
        repoName = qApp.repoName()
        url = sett.commitUrl(repoName)
        if not url and sett.fallbackGlobalLinks(repoName):
            url = sett.commitUrl(None)
        if not url:
            return

        if isinstance(self._link.data, tuple):
            url += self._link.data[0]
        else:
            url += self._link.data
        QDesktopServices.openUrl(QUrl(url))

    def _onFind(self, text, flags):
        self.findWidget.updateFindResult([])
        self.highlightFindResult([])

        if self.textLineCount() > 3000:
            self.curIndexFound = False
            if self.findAllAsync(text, flags):
                self.findWidget.findStarted()
        else:
            findResult = self.findAll(text, flags)
            if findResult:
                self._onFindResultAvailable(findResult, FindPart.All)

    def _onFindCursorChanged(self, cursor):
        self.select(cursor)

    def _onFindHidden(self):
        self.highlightFindResult([])
        self.cancelFind()

    def _onLinkActivated(self, link):
        if link.type == Link.Sha1:
            data = link.data
            isNear = isinstance(data, tuple)
            goNext = False
            if isNear:
                goNext = data[1]
                data = data[0]
            self.requestCommit.emit(data, isNear, goNext)
        else:
            qApp.postEvent(qApp, OpenLinkEvent(link))

    def _onFindResultAvailable(self, result, findPart):
        curFindIndex = 0 if findPart == FindPart.All else -1

        if findPart in [FindPart.CurrentPage, FindPart.All]:
            textCursor = self.textCursor
            if textCursor.isValid() and textCursor.hasSelection() \
                    and not textCursor.hasMultiLines():
                for i in range(0, len(result)):
                    r = result[i]
                    if r == textCursor:
                        curFindIndex = i
                        break
            else:
                curFindIndex = 0
        elif not self.curIndexFound:
            curFindIndex = 0

        if curFindIndex >= 0:
            self.curIndexFound = True

        self.highlightFindResult(result, findPart)
        if curFindIndex >= 0:
            self.select(result[curFindIndex])

        self.findWidget.updateFindResult(result, curFindIndex, findPart)

    def currentFileRow(self):
        row = self.verticalScrollBar().value()
        # TODO: cache the file row to improve performance?
        for i in range(row, -1, -1):
            textLine = self.textLineAt(i)
            if isinstance(textLine, InfoTextLine) and textLine.isFile():
                return i
            elif isinstance(textLine, AuthorTextLine) or \
                    (isinstance(textLine, Sha1TextLine) and textLine.isParent()):
                return 0

        return 0

    def closeFindWidget(self):
        if self.findWidget and self.findWidget.isVisible():
            self.findWidget.hideAnimate()
            return True
        return False

    def canFindNext(self):
        if not self.findWidget:
            return False
        return self.findWidget.isVisible() and self.findWidget.canFindNext()

    def canFindPrevious(self):
        if not self.findWidget:
            return False
        return self.findWidget.isVisible() and self.findWidget.canFindPrevious()

    def findNext(self):
        if self.findWidget:
            self.findWidget.findNext()

    def findPrevious(self):
        if self.findWidget:
            self.findWidget.findPrevious()

    def copyPlainText(self):
        text = self._cursor.selectedText()
        if not text:
            return

        lines = text.split('\n')
        newText = ""
        for line in lines:
            if line and line[0] in ['+', '-', ' ']:
                newText += line[1:] + '\n'
            else:
                newText += line + '\n'

        clipboard = QApplication.clipboard()
        mimeData = QMimeData()
        mimeData.setText(newText)
        clipboard.setMimeData(mimeData)
