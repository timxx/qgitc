# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QAbstractScrollArea,
    QWidget)
from PySide2.QtGui import (
    QPainter,
    QFontMetrics,
    QTextCharFormat,
    QTextOption,
    QBrush,
    QColor)
from PySide2.QtCore import (
    Qt,
    QRectF,
    QPointF,
    Signal)

from .textline import (
    TextLine,
    SourceTextLineBase,
    createFormatRange)
from .colorschema import ColorSchema


__all__ = ["SourceViewer", "SourcePanel"]


class SourceTextLine(SourceTextLineBase):

    def __init__(self, text, font, option):
        super().__init__(TextLine.Source, text,
                         font, option)

    def rehighlight(self):
        formats = self._commonHighlightFormats()
        if formats:
            self._layout.setAdditionalFormats(formats)


class SourcePanel(QWidget):

    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self._viewer = viewer

    def requestWidth(self, lineCount):
        return 0


class SourceViewer(QAbstractScrollArea):

    textLineClicked = Signal(TextLine)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines = []

        settings = qApp.settings()

        self._font = settings.diffViewFont()

        self._option = QTextOption()
        self._option.setWrapMode(QTextOption.NoWrap)

        fm = QFontMetrics(self._font)
        tabstopWidth = fm.width(' ') * settings.tabSize()
        self._option.setTabStop(tabstopWidth)

        if settings.showWhitespace():
            flags = self._option.flags()
            self._option.setFlags(flags | QTextOption.ShowTabsAndSpaces)

        self._lineHeight = fm.height()
        self._maxWidth = 0
        self._highlightLines = []

        self._panel = None

        self.verticalScrollBar().valueChanged.connect(
            self._onVScrollBarValueChanged)

    def appendLine(self, line):
        textLine = SourceTextLine(line, self._font, self._option)
        textLine.setLineNo(len(self._lines))
        self._lines.append(textLine)
        self._maxWidth = max(self._maxWidth,
                             textLine.boundingRect().width())

        if self._panel:
            self.setViewportMargins(
                self._panel.requestWidth(self.textLineCount()),
                0, 0, 0)

        self._adjustScrollbars()
        self.viewport().update()

    def clear(self):
        self._lines.clear()
        self._maxWidth = 0
        self._highlightLines.clear()
        self.viewport().update()

    def hasTextLines(self):
        return self.textLineCount() > 0

    def textLineCount(self):
        return len(self._lines)

    def textLineAt(self, n):
        return self._lines[n]

    def firstVisibleLine(self):
        return self.verticalScrollBar().value()

    def contentOffset(self):
        if not self.hasTextLines():
            return QPointF(0, 0)

        x = self.horizontalScrollBar().value()

        return QPointF(-x, -0)

    def setPanel(self, panel):
        self._panel = panel
        if panel:
            width = panel.requestWidth(self.textLineCount())
            self.setViewportMargins(width, 0, 0, 0)
            rc = self.viewport().rect()
            panel.setGeometry(rc.left(), rc.top(),
                              width, rc.height())
        else:
            self.setViewportMargins(0, 0, 0, 0)

    @property
    def lineHeight(self):
        return self._lineHeight

    def textLineForPos(self, pos):
        if not self.hasTextLines():
            return None

        n = int(pos.y() / self.lineHeight)
        n += self.firstVisibleLine()

        if n >= self.textLineCount():
            n = self.textLineCount() - 1

        return self._lines[n]

    def highlightLines(self, lines):
        self._highlightLines = lines

        self.viewport().update()

    def _linesPerPage(self):
        return int(self.viewport().height() / self._lineHeight)

    def _adjustScrollbars(self):
        vScrollBar = self.verticalScrollBar()
        hScrollBar = self.horizontalScrollBar()
        if not self.hasTextLines():
            vScrollBar.setRange(0, 0)
            hScrollBar.setRange(0, 0)
            return

        hScrollBar.setRange(0, self._maxWidth - self.viewport().width())
        hScrollBar.setPageStep(self.viewport().width())

        linesPerPage = self._linesPerPage()
        totalLines = self.textLineCount()

        vScrollBar.setRange(0, totalLines - linesPerPage)
        vScrollBar.setPageStep(linesPerPage)

    def _onVScrollBarValueChanged(self, value):
        if self._panel:
            self._panel.update()

    def paintEvent(self, event):
        if not self._lines:
            return

        painter = QPainter(self.viewport())

        startLine = self.firstVisibleLine()
        endLine = startLine + self._linesPerPage() + 1
        endLine = min(self.textLineCount(), endLine)

        offset = self.contentOffset()
        viewportRect = self.viewport().rect()
        eventRect = event.rect()

        painter.setClipRect(eventRect)

        for i in range(startLine, endLine):
            textLine = self._lines[i]

            br = textLine.boundingRect()
            r = br.translated(offset)

            if i in self._highlightLines:
                fr = QRectF(br)
                fr.moveTop(fr.top() + r.top())
                fr.setLeft(0)
                fr.setRight(viewportRect.width() - offset.x())
                painter.fillRect(fr, QColor(192, 237, 197))

            formats = []

            textLine.draw(painter, offset, formats, QRectF(eventRect))

            offset.setY(offset.y() + r.height())

            if (offset.y() > viewportRect.height()):
                break

    def resizeEvent(self, event):
        if self._panel:
            rc = self.viewport().rect()
            width = self._panel.requestWidth(self.textLineCount())
            self._panel.setGeometry(rc.left(), rc.top(),
                                    width, rc.height())
        self._adjustScrollbars()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self.hasTextLines():
            return

        textLine = self.textLineForPos(event.pos())
        if not textLine:
            return

        self.textLineClicked.emit(textLine)
