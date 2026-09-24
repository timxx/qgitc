# -*- coding: utf-8 -*-

from typing import Dict

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QDesktopServices,
    QFont,
    QFontMetricsF,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPen,
    QTextCharFormat,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.blockmodel import Block
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
        indent = QFontMetricsF(self._font).averageCharWidth() * \
            self._indent
        if self._wrap and self._wrapWidth:
            # stacked wrapped rows, indented like the single line case
            self._layout.beginLayout()
            y = 0
            while True:
                line = self._layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(max(1, self._wrapWidth - indent))
                line.setPosition(QPointF(indent, y))
                y += line.height()
            self._layout.endLayout()
            return

        self._layout.beginLayout()
        line = self._layout.createLine()
        line.setPosition(QPointF(indent, 0))
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
    # carries the file path owning the top visible line, or None over the
    # commit header/message region
    fileChanged = Signal(object)
    requestCommit = Signal(str, bool, bool)
    requestBlame = Signal(str, bool, Commit)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.highlightPattern = None
        self.highlightField = FindField.Comments

        self.curIndexFound = False

        self._parentCount = 1

        # File sections are the blocks registered around each DiffType.File
        # marker, so a path and a viewer line each resolve to the other
        # without scanning the document or the file list. Only file blocks
        # are indexed; the commit header/message block is not.
        self._fileBlocks: Dict[str, Block] = {}
        self._openFilePath: str = None

        self.verticalScrollBar().valueChanged.connect(
            self._onVScollBarValueChanged)
        self.linkActivated.connect(self._onLinkActivated)

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
        textLine.setWrap(True)
        self.appendTextLine(textLine)

    def addSHA1Line(self, content, isParent):
        textLine = Sha1TextLine(self, content, isParent)
        textLine.setWrap(True)
        self.appendTextLine(textLine)

    def addNormalTextLine(self, text, useBuiltinPatterns=True):
        textLine = TextLine(text, self._font)
        textLine.useBuiltinPatterns = useBuiltinPatterns
        textLine.setWrap(True)
        self.appendTextLine(textLine)

    def addSummaryTextLine(self, text):
        textLine = SummaryTextLine(text, self._font)
        textLine.useBuiltinPatterns = True
        textLine.setWrap(True)
        self.appendTextLine(textLine)

    def isFileMarker(self, item):
        """True for the DiffType.File tuple that opens a file's section."""
        return isinstance(item, (tuple, list)) and len(item) == 2 and \
            item[0] == DiffType.File

    def appendLines(self, items):
        # One foldable block per file section: the marker line anchors the
        # block and stays visible, the rest of the section folds away.
        # Done here rather than at the call sites so every PatchViewer
        # user (commit window, branch compare, diff view) gets it.
        start = 0
        for i, item in enumerate(items):
            if not self.isFileMarker(item):
                continue
            if i > start:
                super().appendLines(items[start:i])
            self.beginBlock(self._fileBlockMeta(item))
            start = i

        if start < len(items):
            super().appendLines(items[start:])

    def endReading(self):
        # the last file's section has no following marker to close it;
        # close it before the base class re-runs a live find, so the
        # results are scrolled against the final geometry
        self.endBlock()
        super().endReading()

    def insertFileSection(self, position, items):
        """Insert one file's complete diff at `position`.

        `items` is a whole section: the DiffType.File marker followed by
        every line of that file's diff. Its foldable block is registered
        around it, which lets a caller keep the view in name order while
        the diff is still arriving.
        """
        if not items:
            return

        # a section that was still streaming belongs before the insert
        self.endBlock()
        self.insertLines(position, items)

        if self.isFileMarker(items[0]):
            self.addBlock(position, position + len(items) - 1,
                          meta=self._fileBlockMeta(items[0]))

    def _fileBlockMeta(self, item):
        path = item[1]
        if isinstance(path, bytes):
            path = path.decode(diff_encoding, errors="replace")
        return {"kind": "file", "path": path, "title": path}

    @staticmethod
    def _fileMetaPath(meta):
        """The file path a block's meta carries, or None for other blocks."""
        if not isinstance(meta, dict) or meta.get("kind") != "file":
            return None
        return meta.get("path")

    # -- file sections -----------------------------------------------------

    def beginBlock(self, meta=None):
        # every file section ends up here or in insertFileSection, so the
        # open one is remembered by path to keep it addressable while it
        # is still streaming and has no block of its own yet
        super().beginBlock(meta)
        self._openFilePath = self._fileMetaPath(meta)

    def endBlock(self):
        super().endBlock()
        self._openFilePath = None

    def addBlock(self, startLine, endLine, meta=None):
        block = super().addBlock(startLine, endLine, meta=meta)
        path = self._fileMetaPath(meta)
        if block is not None and path is not None:
            self._fileBlocks[path] = block
        return block

    def clear(self):
        self._fileBlocks.clear()
        self._openFilePath = None
        super().clear()

    def fileLineForPath(self, path):
        """Viewer line of `path`'s DiffType.File marker, or None.

        Every line-indexed consumer can ask this instead of keeping its
        own copy of the line numbers: the block keeps its anchor correct
        while earlier sections are inserted above it.
        """
        block = self._fileBlocks.get(path)
        if block is not None:
            return block.startLine
        if path is not None and path == self._openFilePath:
            return self._openBlockStart
        return None

    def filePathAtLine(self, lineNo):
        """Path of the file section owning `lineNo`, or None.

        None means the line is outside every file section -- the commit
        header and message, or a gap between sections.
        """
        block = self._blockModel.blockAtLine(lineNo)
        if block is None:
            return None
        return self._fileMetaPath(block.meta)

    def currentFilePath(self):
        """Path of the file section the first visible line is in, or None."""
        return self.filePathAtLine(self.firstVisibleLine())

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
        self._acCopy.setShortcut(QKeySequence(Qt.ControlModifier | Qt.ShiftModifier | Qt.Key_C))
        action = QAction(self.tr("Copy Plain &Text"), self,
                         shortcut=QKeySequence.Copy)
        action.triggered.connect(self.copyPlainText)
        menu.insertAction(self._acCopy, action)
        menu.removeAction(self._acCopy)
        menu.insertAction(action, self._acCopy)

        menu.addSeparator()

        self._acOpenCommit = menu.addAction(
            self.tr("&Open commit in browser"), self._onOpenCommit)

        return menu

    def updateContextMenu(self, pos):
        # keep base state (copy enablement, fold entries) up to date
        super().updateContextMenu(pos)

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

        # the file section owning the top visible line is one block
        # lookup, not a walk back over the document's text lines
        self.fileChanged.emit(self.currentFilePath())

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

    def copyPlainText(self):
        text = self._cursor.selectedText()
        if not text:
            return

        hasTrailingNewline = text.endswith('\n')
        lines = text.split('\n')
        if hasTrailingNewline and lines and lines[-1] == '':
            lines = lines[:-1]
        result = []
        for line in lines:
            if line and line[0] in ['+', '-', ' ']:
                result.append(line[1:])
            else:
                result.append(line)
        newText = '\n'.join(result)
        if hasTrailingNewline:
            newText += '\n'

        clipboard = ApplicationBase.instance().clipboard()
        clipboard.setText(newText)

        app = ApplicationBase.instance()
        app.trackFeatureUsage("viwer.copy_plain_text")

    def keyPressEvent(self, event: QKeyEvent):
        if event.matches(QKeySequence.Copy):
            self.copyPlainText()
        elif event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier) and event.key() == Qt.Key_C:
            self.copy()
        else:
            super().keyPressEvent(event)
