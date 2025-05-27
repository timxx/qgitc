# -*- coding: utf-8 -*-

from PySide6.QtCore import QMimeData, QPointF, QRectF, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QDesktopServices,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
    QTextCharFormat,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.common import Commit, FindField, decodeFileData, findInlineSpans
from qgitc.diffutils import *
from qgitc.events import OpenLinkEvent
from qgitc.sourceviewer import SourceViewer
from qgitc.textline import (
    Link,
    LinkTextLine,
    SourceTextLineBase,
    TextLine,
    createFormatRange,
)


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
                tcFormat.setForeground(
                    ApplicationBase.instance().colorSchema().Adding)
        elif text[0] == "-":
            tcFormat.setForeground(
                ApplicationBase.instance().colorSchema().Deletion)
        elif text[0] == " " and len(text) >= 2:
            # TODO: only if in submodule changes
            if text.startswith("  > "):
                tcFormat.setForeground(
                    ApplicationBase.instance().colorSchema().Submodule)
            elif text.startswith("  < "):
                tcFormat.setForeground(
                    ApplicationBase.instance().colorSchema().Submodule2)
            elif self._parentCount > 1 and len(text) >= self._parentCount:
                index = self._parentCount - 1
                if text[index] == "+":
                    tcFormat.setFontWeight(QFont.Bold)
                    tcFormat.setForeground(
                        ApplicationBase.instance().colorSchema().Adding)
                elif text[index] == "-":
                    tcFormat.setFontWeight(QFont.Bold)
                    tcFormat.setForeground(
                        ApplicationBase.instance().colorSchema().Deletion)
        elif diff_begin_re.search(text) or text.startswith(r"\ No newline "):
            tcFormat.setForeground(
                ApplicationBase.instance().colorSchema().Newline)

        if tcFormat.isValid():
            formats.append(createFormatRange(0, self.utf16Length(), tcFormat))

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
        fmtRg = createFormatRange(0, self.utf16Length(), fmt)

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

    def __init__(self, text, font, option=None, indent=4):
        super().__init__(text, font, option)
        self._indent = indent

    def _relayout(self):
        self._layout.beginLayout()
        line = self._layout.createLine()
        width = QFontMetricsF(self._font).averageCharWidth() * self._indent
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

        formats = self._layout.formats()
        text: str = self.text()
        fmt = QTextCharFormat()
        fmt.setForeground(ApplicationBase.instance().colorSchema().InlineCode)

        for start, length in findInlineSpans(text):
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

        self.curIndexFound = False

        self._parentCount = 1

        self.verticalScrollBar().valueChanged.connect(
            self._onVScollBarValueChanged)
        self.linkActivated.connect(self._onLinkActivated)
        self.findResultAvailable.connect(self._onFindResultAvailable)

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
            painter.fillRect(
                lineRect, ApplicationBase.instance().colorSchema().InfoBg)

    def canDrawLineBorder(self, textLine):
        return isinstance(textLine, InfoTextLine)

    def drawLinesBorder(self, painter: QPainter, rect: QRectF):
        oldPen = painter.pen()
        pen = QPen(ApplicationBase.instance().colorSchema().InfoBorder)
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
            fmt.setForeground(
                QBrush(ApplicationBase.instance().colorSchema().InfoFg))
            formats.append(createFormatRange(0, textLine.utf16Length(), fmt))
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

    def setParentCount(self, n):
        self._parentCount = n

    def _highlightFormatRange(self, textLine: TextLine):
        formats = []
        if self.highlightPattern:
            matchs = self.highlightPattern.finditer(textLine.text())
            fmt = QTextCharFormat()
            fmt.setBackground(
                QBrush(ApplicationBase.instance().colorSchema().HighlightWordBg))
            for m in matchs:
                start = textLine.mapToUtf16(m.start())
                end = textLine.mapToUtf16(m.end())
                rg = createFormatRange(start, end - start, fmt)
                formats.append(rg)
        return formats

    def _createCommentsFormats(self, textLine):
        if self.highlightField == FindField.Comments or \
                self.highlightField == FindField.All:
            return self._highlightFormatRange(textLine)

        return None

    def _createDiffFormats(self, textLine):
        if self.highlightField == FindField.All:
            return self._highlightFormatRange(textLine)
        elif FindField.isDiff(self.highlightField):
            text = textLine.text().lstrip()
            if text.startswith('+') or text.startswith('-'):
                return self._highlightFormatRange(textLine)

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
        sett = ApplicationBase.instance().settings()
        repoName = ApplicationBase.instance().repoName()
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
            ApplicationBase.instance().postEvent(
                ApplicationBase.instance(), OpenLinkEvent(link))

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

        clipboard = ApplicationBase.instance().clipboard()
        mimeData = QMimeData()
        mimeData.setText(newText)
        clipboard.setMimeData(mimeData)
