# -*- coding: utf-8 -*-

from PySide2.QtWidgets import (
    QAbstractScrollArea,
    QWidget,
    QApplication,
    QMenu)
from PySide2.QtGui import (
    QPainter,
    QFontMetrics,
    QTextCharFormat,
    QTextOption,
    QBrush,
    QColor,
    QKeySequence)
from PySide2.QtCore import (
    Qt,
    QRect,
    QRectF,
    QPoint,
    QPointF,
    Signal,
    QElapsedTimer,
    QTimer,
    QMimeData)

from .textline import (
    TextLine,
    createFormatRange,
    Link)
from .colorschema import ColorSchema
from .textcursor import TextCursor

import re


__all__ = ["TextViewer", "FindFlags"]


class FindFlags:

    Backward = 0x01
    CaseSenitively = 0x02
    WholeWords = 0x04
    UseRegExp = 0x08


class TextViewer(QAbstractScrollArea):

    textLineClicked = Signal(TextLine)
    linkActivated = Signal(Link)

    def __init__(self, parent=None):
        super().__init__(parent)
        # raw text lines
        self._lines = None
        # TextLine instances
        self._textLines = {}
        self._inReading = False

        self._convertIndex = 0
        self._convertTimer = QTimer(self)
        self._convertTimer.timeout.connect(self._onConvertEvent)

        self._option = QTextOption()
        self._option.setWrapMode(QTextOption.NoWrap)

        self.updateFont(self.font())

        self._maxWidth = 0
        self._highlightLines = []
        self._highlightFind = []

        self._cursor = TextCursor(self)
        self._clickTimer = QElapsedTimer()

        self.viewport().setMouseTracking(True)

        self._clickOnLink = False
        self._link = None

        pattern = qApp.settings().bugPattern()
        self._bugPattern = re.compile(pattern) if pattern else None

        self._contextMenu = None

    def updateFont(self, font):
        self._font = font
        fm = QFontMetrics(self._font)
        self._lineHeight = fm.height()

    def toTextLine(self, text):
        return TextLine(TextLine.Text, text, self._font, self._option)

    def appendLine(self, line):
        self.appendLines([line])

    def appendLines(self, lines):
        if self._lines:
            self._lines.extend(lines)
        elif self._inReading:
            self._lines = lines
        else:
            for line in lines:
                textLine = self.toTextLine(line)
                lineNo = len(self._textLines)
                textLine.setLineNo(lineNo)
                self._textLines[lineNo] = textLine

        if not self._convertTimer.isActive():
            self._convertTimer.start(0)

        self.viewport().update()

    def beginReading(self):
        """ Call before reading lines to TextViewer """
        self._inReading = True

    def endReading(self):
        """ Call after reading finished """
        self._inReading = False
        if self._lines and \
                len(self._lines) == len(self._textLines):
            self._lines = None

    def clear(self):
        self._lines = None
        self._textLines.clear()
        self._inReading = False
        self._maxWidth = 0
        self._highlightLines.clear()
        self._cursor.clear()
        self._clickOnLink = False
        self._link = None

        self._convertIndex = 0
        self._convertTimer.stop()

        self._adjustScrollbars()
        self.viewport().setCursor(Qt.IBeamCursor)
        self.viewport().update()

    def hasTextLines(self):
        return self.textLineCount() > 0

    def textLineCount(self):
        if self._lines:
            return len(self._lines)

        return len(self._textLines)

    def textLineAt(self, n):
        if n < 0:
            return None

        # n already converted
        if n in self._textLines:
            return self._textLines[n]

        # all converted but no match
        if not self._lines:
            return None

        # convert one
        if n >= len(self._lines):
            return None

        textLine = self.toTextLine(self._lines[n])
        textLine.setLineNo(n)

        self._textLines[n] = textLine
        # free the memory
        self._lines[n] = None
        if not self._inReading and \
                len(self._lines) == len(self._textLines):
            self._lines = None

        return textLine

    def firstVisibleLine(self):
        return self.verticalScrollBar().value()

    @property
    def currentLineNo(self):
        return self.firstVisibleLine()

    def gotoLine(self, lineNo):
        if lineNo < 0 or lineNo >= self.textLineCount():
            return

        # central the lineNo in view
        halfOfPage = self._linesPerPage() // 2
        if lineNo > halfOfPage:
            lineNo -= halfOfPage

        vScrollBar = self.verticalScrollBar()
        if vScrollBar.value() != lineNo:
            vScrollBar.setValue(lineNo)
            self.viewport().update()

    def contentOffset(self):
        if not self.hasTextLines():
            return QPointF(0, 0)

        x = self.horizontalScrollBar().value()

        return QPointF(-x, -0)

    def mapToContents(self, pos):
        x = pos.x() + self.horizontalScrollBar().value()
        y = pos.y() + 0
        return QPoint(x, y)

    @property
    def lineHeight(self):
        return self._lineHeight

    def textLineForPos(self, pos):
        if not self.hasTextLines():
            return None

        y = max(0, pos.y())
        n = int(y / self.lineHeight)
        n += self.firstVisibleLine()

        if n >= self.textLineCount():
            n = self.textLineCount() - 1

        return self.textLineAt(n)

    def highlightLines(self, lines):
        self._highlightLines = lines

        self.viewport().update()

    def highlightFindResult(self, result):
        self._highlightFind = result
        self.viewport().update()

    def selectAll(self):
        if not self.hasTextLines():
            return

        self._cursor.moveTo(0, 0)
        lastLine = self.textLineCount() - 1
        self._cursor.selectTo(lastLine, len(self.textLineAt(lastLine).text()))
        self._invalidateSelection()

    def select(self, cursor):
        if not cursor.isValid():
            return

        self._cursor.moveTo(cursor.beginLine(), cursor.beginPos())
        self._cursor.selectTo(cursor.endLine(), cursor.endPos())
        self.ensureCursorVisible()
        self.viewport().update()

    def ensureCursorVisible(self):
        if not self.hasTextLines():
            return
        if not self._cursor.isValid():
            return

        startLine = self.firstVisibleLine()
        endLine = startLine + self._linesPerPage()
        endLine = min(self.textLineCount(), endLine)

        lineNo = self._cursor.beginLine()
        if lineNo < startLine or lineNo >= endLine:
            halfOfPage = self._linesPerPage() // 2
            if lineNo > halfOfPage:
                lineNo -= halfOfPage
            self.verticalScrollBar().setValue(lineNo)

        hbar = self.horizontalScrollBar()

        start = self._cursor.beginPos()
        end = self._cursor.endPos()
        if start > end:
            start, end = end, start

        textLine = self.textLineAt(lineNo)
        x1 = textLine.offsetToX(start)
        x2 = textLine.offsetToX(end)

        viewWidth = self.viewport().width()
        offset = hbar.value()

        if x1 < offset or x2 > (offset + viewWidth):
            hbar.setValue(x1)

    def findAll(self, text, flags=0):
        result = []
        if not text or not self.hasTextLines():
            return result

        exp = text
        exp_flags = re.IGNORECASE

        if not (flags & FindFlags.UseRegExp):
            exp = re.escape(text)
        if flags & FindFlags.CaseSenitively:
            exp_flags = 0
        if flags & FindFlags.WholeWords:
            exp = r'\b' + text + r'\b'

        pattern = re.compile(exp, exp_flags)

        for i in range(0, self.textLineCount()):
            text = self.textLineAt(i).text()
            if not text:
                continue

            iter = pattern.finditer(text)
            for m in iter:
                tc = TextCursor()
                tc.moveTo(i, m.start())
                tc.selectTo(i, m.end())
                result.append(tc)

        return result

    @property
    def selectedText(self):
        return self._cursor.selectedText()

    def copy(self):
        text = self._cursor.selectedText()
        if not text:
            return

        clipboard = QApplication.clipboard()
        mimeData = QMimeData()
        mimeData.setText(text)
        clipboard.setMimeData(mimeData)

    @property
    def textCursor(self):
        return self._cursor

    def updateLinkData(self, link, lineNo):
        """ Implement in subclass"""
        pass

    @property
    def contextMenu(self):
        if not self._contextMenu:
            self._contextMenu = QMenu(self)
            self._acCopy = self._contextMenu.addAction(
                self.tr("&Copy"),
                self.copy,
                QKeySequence("Ctrl+C"))
            self._contextMenu.addSeparator()
            self._acSelectAll = self._contextMenu.addAction(
                self.tr("Select &All"),
                self.selectAll,
                QKeySequence("Ctrl+A"))

        return self._contextMenu

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

    def _invalidateSelection(self):
        if not self._cursor.hasSelection():
            return

        begin = self._cursor.beginLine()
        end = self._cursor.endLine()

        x = 0
        y = (begin - self.firstVisibleLine()) * self.lineHeight
        w = self.viewport().width()
        h = (end - begin + 1) * self.lineHeight

        rect = QRect(x, y, w, h)
        # offset for some odd fonts LoL
        offset = int(self.lineHeight / 2)
        rect.adjust(0, -offset, 0, offset)
        self.viewport().update(rect)

    def _selectionFormatRange(self, lineIndex):
        if not self._cursor.within(lineIndex):
            return None

        textLine = self.textLineAt(lineIndex)
        start = 0
        end = len(textLine.text())

        if self._cursor.beginLine() == lineIndex:
            start = self._cursor.beginPos()
        if self._cursor.endLine() == lineIndex:
            end = self._cursor.endPos()

        fmt = QTextCharFormat()
        if qApp.applicationState() == Qt.ApplicationActive:
            fmt.setBackground(QBrush(ColorSchema.SelFocus))
        else:
            fmt.setBackground(QBrush(ColorSchema.SelNoFocus))

        return createFormatRange(start, end - start, fmt)

    def _findResultFormatRange(self, lineIndex):
        if not self._highlightFind:
            return None

        result = []
        fmt = QTextCharFormat()
        fmt.setBackground(ColorSchema.FindResult)

        for r in self._highlightFind:
            if r.beginLine() == lineIndex:
                rg = createFormatRange(r.beginPos(), r.endPos() - r.beginPos(), fmt)
                result.append(rg)
            elif r.beginLine() > lineIndex:
                break

        return result

    def _isLetter(self, char):
        if char >= 'a' and char <= 'z':
            return True
        if char >= 'A' and char <= 'Z':
            return True

        if char == '_':
            return True

        if char.isdigit():
            return True

        return False

    def _onConvertEvent(self):
        textLine = self.textLineAt(self._convertIndex)
        self._convertIndex += 1

        if not self._inReading and self._convertIndex >= self.textLineCount():
            self._convertTimer.stop()
            self._convertIndex = 0

        needAdjust = self._inReading
        if textLine:
            width = textLine.boundingRect().width()
            if width > self._maxWidth:
                self._maxWidth = width
                needAdjust = True

        if needAdjust:
            self._adjustScrollbars()

    def paintEvent(self, event):
        if not self.hasTextLines():
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
            textLine = self.textLineAt(i)

            br = textLine.boundingRect()
            r = br.translated(offset)

            if i in self._highlightLines:
                fr = QRectF(br)
                fr.moveTop(fr.top() + r.top())
                fr.setLeft(0)
                fr.setRight(viewportRect.width() - offset.x())
                painter.fillRect(fr, QColor(192, 237, 197))

            formats = []

            # find result
            findRg = self._findResultFormatRange(i)
            if findRg:
                formats.extend(findRg)

            # selection
            selectionRg = self._selectionFormatRange(i)
            if selectionRg:
                formats.append(selectionRg)

            textLine.draw(painter, offset, formats, QRectF(eventRect))

            offset.setY(offset.y() + r.height())

            if (offset.y() > viewportRect.height()):
                break

    def resizeEvent(self, event):
        self._adjustScrollbars()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self.hasTextLines():
            return

        self._clickOnLink = self._link is not None
        self._invalidateSelection()

        textLine = self.textLineForPos(event.pos())
        if not textLine:
            return

        tripleClick = False
        if self._clickTimer.isValid():
            tripleClick = not self._clickTimer.hasExpired(
                QApplication.doubleClickInterval())
            self._clickTimer.invalidate()

        if tripleClick:
            self._cursor.moveTo(textLine.lineNo(), 0)
            self._cursor.selectTo(textLine.lineNo(), len(textLine.text()))
            self._invalidateSelection()
        else:
            offset = textLine.offsetForPos(self.mapToContents(event.pos()))
            self._cursor.moveTo(textLine.lineNo(), offset)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        if self._link and self._clickOnLink:
            self.linkActivated.emit(self._link)

        self._clickOnLink = False
        if not self.hasTextLines() or \
            self._cursor.hasSelection():
            return

        textLine = self.textLineForPos(event.pos())
        if not textLine:
            return

        self.textLineClicked.emit(textLine)

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self.hasTextLines():
            return

        self._clickTimer.restart()
        self._invalidateSelection()
        self._cursor.clear()

        textLine = self.textLineForPos(event.pos())
        if not textLine:
            return

        offset = textLine.offsetForPos(self.mapToContents(event.pos()))
        begin = offset
        end = offset

        # find the word
        content = textLine.text()
        if offset < len(content) and self._isLetter(content[offset]):
            for i in range(offset - 1, -1, -1):
                if self._isLetter(content[i]):
                    begin = i
                    continue
                break

            for i in range(offset + 1, len(content)):
                if self._isLetter(content[i]):
                    end = i
                    continue
                break

        end += 1
        word = content[begin:end]
        if word:
            self._cursor.moveTo(textLine.lineNo(), begin)
            self._cursor.selectTo(textLine.lineNo(), end)
            self._invalidateSelection()

    def mouseMoveEvent(self, event):
        if self._clickTimer.isValid():
            self._clickTimer.invalidate()

        self._clickOnLink = False
        self._link = None
        if not self.hasTextLines():
            return

        textLine = self.textLineForPos(event.pos())
        if not textLine:
            return

        offset = textLine.offsetForPos(self.mapToContents(event.pos()))
        if event.buttons() == Qt.LeftButton:
            self._invalidateSelection()

            n = textLine.lineNo()
            self._cursor.selectTo(n, offset)

            self._invalidateSelection()
        elif event.buttons() == Qt.NoButton:
            x = event.pos().x() + self.horizontalScrollBar().value()
            if textLine.boundingRect().right() >= x:
                self._link = textLine.hitTest(offset)
                if self._link:
                    self.updateLinkData(self._link, textLine.lineNo())

        cursorShape = Qt.PointingHandCursor if self._link \
            else Qt.IBeamCursor
        self.viewport().setCursor(cursorShape)

    def contextMenuEvent(self, event):
        menu = self.contextMenu
        self._acCopy.setEnabled(self._cursor.hasSelection())
        menu.exec_(event.globalPos())
