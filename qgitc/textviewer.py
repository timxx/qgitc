# -*- coding: utf-8 -*-

import bisect
import re
from typing import List

from PySide6.QtCore import (
    QBasicTimer,
    QElapsedTimer,
    QEvent,
    QMimeData,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QRegularExpression,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QCursor,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QTextCharFormat,
    QTextOption,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSlider,
    QApplication,
    QMenu,
    QScrollBar,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.findconstants import FindFlags, FindPart
from qgitc.findwidget import FindWidget
from qgitc.textcursor import TextCursor
from qgitc.textline import Link, TextLine, createFormatRange

__all__ = ["TextViewer"]


class TextViewer(QAbstractScrollArea):

    textLineClicked = Signal(TextLine)
    linkActivated = Signal(Link)
    findResultAvailable = Signal(list, int)
    findFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # raw text lines
        self._lines = None
        # TextLine instances
        self._textLines = {}
        self._inReading = False

        self._convertIndex = 0
        self._convertTimerId = None

        self._option = QTextOption()
        self._option.setWrapMode(QTextOption.NoWrap)

        self.reloadSettings()

        self._maxWidth = 0
        self._highlightLines = []
        self._highlightFind: List[TextCursor] = []

        self._cursor = TextCursor(self)
        self._clickTimer = QElapsedTimer()

        self.viewport().setMouseTracking(True)

        self._clickOnLink = False
        self._link = None

        self._contextMenu = None

        self._findTimerId = None
        self._findIndex = 0
        self._findPattern = None
        self._findCurPageRange = None

        self._settingsTimer = None
        ApplicationBase.instance().settings().bugPatternChanged.connect(
            self.delayUpdateSettings)
        ApplicationBase.instance().settings().fallbackGlobalChanged.connect(
            self.delayUpdateSettings)

        self._similarWordPattern = None

        self.setTextMargins(4)

        self._autoScrollTimer = QBasicTimer(self)

        self._findWidget: FindWidget = None

        self.horizontalScrollBar().setSingleStep(20)
        self.verticalScrollBar().setSingleStep(1)

    def updateFont(self, font):
        self._font = font
        fm = QFontMetrics(self._font)
        self._lineHeight = fm.height()

    def reloadSettings(self):
        self.updateFont(self.font())
        self._bugPatterns = TextViewer.reloadBugPattern()

    @staticmethod
    def reloadBugPattern():
        repoName = ApplicationBase.instance().repoName()
        sett = ApplicationBase.instance().settings()
        patterns = sett.bugPatterns(repoName)
        globalPatterns = sett.bugPatterns(
            None) if sett.fallbackGlobalLinks(repoName) else None

        bugPatterns = []
        filtered = set()

        def _combine(patterns):
            if not patterns:
                return
            for pattern, url in patterns:
                if not pattern:
                    continue

                if pattern not in filtered:
                    filtered.add(pattern)
                    try:
                        re_pattern = re.compile(pattern)
                        bugPatterns.append((Link.BugId, re_pattern, url))
                    except re.error:
                        continue

        _combine(patterns)
        _combine(globalPatterns)

        return bugPatterns

    def toTextLine(self, text):
        return TextLine(text, self._font, self._option)

    def initTextLine(self, textLine, lineNo):
        textLine.setLineNo(lineNo)
        if textLine.useBuiltinPatterns and self._bugPatterns:
            textLine.setCustomLinkPatterns(self._bugPatterns)

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
                self.appendTextLine(textLine)

        if self._convertTimerId is None:
            self._convertTimerId = self.startTimer(0)

        self.viewport().update()

    def appendTextLine(self, textLine):
        lineNo = self.textLineCount()
        self.initTextLine(textLine, lineNo)
        if self._lines is None:
            self._lines = []
        self._lines.append(None)
        self._textLines[lineNo] = textLine

        if self._convertTimerId is None:
            self._convertTimerId = self.startTimer(0)

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

        if self._findWidget and self._findWidget.isVisible():
            # redo a find
            self._onFind(self._findWidget.text, self._findWidget.flags)

    def clear(self):
        self._lines = None
        self._textLines.clear()
        self._inReading = False
        self._maxWidth = 0
        self._highlightLines.clear()
        self._cursor.clear()
        self._clickOnLink = False
        self._link = None
        self._similarWordPattern = None

        self._convertIndex = 0
        if self._convertTimerId is not None:
            self.killTimer(self._convertTimerId)
            self._convertTimerId = None

        self.cancelFind()

        if self._settingsTimer is not None:
            if self._settingsTimer.isActive():
                self.reloadSettings()
            self._settingsTimer.stop()
            self._settingsTimer = None

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
        self.initTextLine(textLine, n)

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

    def gotoLine(self, lineNo, centralOnView=True):
        if lineNo < 0 or lineNo >= self.textLineCount():
            return

        self._cursor.moveTo(lineNo, 0)

        # central the lineNo in view
        if centralOnView:
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

    def textRowForPos(self, pos):
        if not self.hasTextLines():
            return -1

        y = max(0, pos.y())
        n = int(y / self.lineHeight)
        n += self.firstVisibleLine()

        if n >= self.textLineCount():
            n = self.textLineCount() - 1

        return n

    def textLineForPos(self, pos):
        n = self.textRowForPos(pos)
        if n == -1:
            return None
        return self.textLineAt(n)

    def highlightLines(self, lines):
        self._highlightLines = lines

        self.viewport().update()

    def highlightFindResult(self, result, findPart=FindPart.All):
        if not result:
            self._highlightFind.clear()
        elif findPart in [FindPart.CurrentPage, FindPart.All]:
            self._highlightFind = result[:]
        elif findPart == FindPart.BeforeCurPage:
            low = bisect.bisect_left(self._highlightFind, result[0])
            # FIXME: how to improve performance?
            for i in range(0, len(result)):
                self._highlightFind.insert(low + i, result[i])
        else:
            self._highlightFind.extend(result)

        needUpdate = True
        if result:
            firstVisibleLine = self.firstVisibleLine()
            lastVisibleLine = firstVisibleLine + self._linesPerPage()
            firstLine = result[0].beginLine()
            lastLine = result[-1].endLine()
            if firstLine > lastVisibleLine or lastLine < firstVisibleLine:
                needUpdate = False
        if needUpdate:
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

    def ensureCursorVisible(self, lineOnly=False):
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
            newLineNo = lineNo
            if newLineNo > halfOfPage:
                newLineNo -= halfOfPage
            self.verticalScrollBar().setValue(newLineNo)

        if lineOnly:
            return

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

    def ensureSelectionVisible(self):
        if not self.hasTextLines():
            return
        if not self._cursor.isValid():
            return

        startLine = self.firstVisibleLine()
        endLine = startLine + self._linesPerPage()
        endLine = min(self.textLineCount(), endLine)

        if self._cursor._endLine > endLine:
            self.verticalScrollBar().setValue(self._cursor._endLine - endLine + startLine)
        elif self._cursor._endLine < startLine:
            self.verticalScrollBar().setValue(self._cursor._endLine)

        textLine = self.textLineAt(self._cursor._endLine)
        x = textLine.offsetToX(self._cursor._endPos)

        hbar = self.horizontalScrollBar()
        viewWidth = self.viewport().width()
        offset = hbar.value()

        if x > (offset + viewWidth):
            hbar.setValue(x - viewWidth + offset)
        elif x < offset:
            hbar.setValue(x)

    def ensureLineVisible(self, lineNo: int, centralOnView=True):
        if lineNo < 0 or lineNo >= self.textLineCount():
            return

        # central the lineNo in view
        if centralOnView:
            halfOfPage = self._linesPerPage() // 2
            if lineNo > halfOfPage:
                lineNo -= halfOfPage

        needUpdate = False
        vScrollBar = self.verticalScrollBar()
        if vScrollBar.value() != lineNo:
            vScrollBar.setValue(lineNo)
            needUpdate = True

        hbar = self.horizontalScrollBar()
        if hbar.value() != 0:
            hbar.setValue(0)
            needUpdate = True

        if needUpdate:
            self.viewport().update()

    def findAll(self, text, flags=0):
        if not text or not self.hasTextLines():
            return []

        pattern = self._toFindPattern(text, flags)
        return self._findInRange(pattern, 0, self.textLineCount())

    def findAllAsync(self, text, flags=0):
        """ Find text in idle.
        False returned if search done without starting idle
        """

        if not text or not self.hasTextLines():
            return False

        self.cancelFind()

        # Always find current visible page first
        begin = self.firstVisibleLine()
        end = self._linesPerPage() + begin
        if end >= self.textLineCount():
            end = self.textLineCount()

        pattern = self._toFindPattern(text, flags)
        result = self._findInRange(pattern, begin, end)

        if result:
            self.findResultAvailable.emit(result, FindPart.CurrentPage)

        # no more lines
        if begin == 0 and end == self.textLineCount():
            return False

        self._findPattern = pattern
        self._findCurPageRange = (begin, end - 1)
        self._findIndex = end  # search from next page
        self._findTimerId = self.startTimer(0)

        return True

    def cancelFind(self):
        if self._findTimerId is not None:
            self.killTimer(self._findTimerId)
            self._findTimerId = None
            self._findPattern = None
            self.findFinished.emit()

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

    def createContextMenu(self):
        menu = QMenu(self)
        self._acCopy = menu.addAction(
            self.tr("&Copy"),
            self.copy,
            QKeySequence(QKeySequence.Copy))
        self._acCopy.setIcon(QIcon.fromTheme("edit-copy"))
        self._acSelectAll = menu.addAction(
            self.tr("Select &All"),
            self.selectAll,
            QKeySequence(QKeySequence.SelectAll))
        self._acSelectAll.setIcon(QIcon.fromTheme("edit-select-all"))
        menu.addSeparator()
        acFind = menu.addAction(
            self.tr("&Find"),
            self.executeFind,
            QKeySequence(QKeySequence.Find))
        acFind.setIcon(QIcon.fromTheme("edit-find"))
        return menu

    @property
    def contextMenu(self):
        if not self._contextMenu:
            self._contextMenu = self.createContextMenu()
        return self._contextMenu

    def updateContextMenu(self, pos):
        self._acCopy.setEnabled(self._cursor.hasSelection())

    def drawLineBackground(self, painter, textLine, lineRect):
        pass

    def drawLinesBorder(self, painter, rect):
        pass

    def canDrawLineBorder(self, textLine):
        return False

    def textLineFormatRange(self, textLine):
        return None

    def delayUpdateSettings(self):
        if self._settingsTimer:
            # restart
            self._settingsTimer.start(10)
        else:
            self._settingsTimer = QTimer(self)
            self._settingsTimer.timeout.connect(
                self._onUpdateSettings)
            self._settingsTimer.setSingleShot(True)
            self._settingsTimer.start(10)

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

        start = textLine.mapToUtf16(start)
        end = textLine.mapToUtf16(end)

        # select the new line if multiple lines selected
        if lineIndex < self._cursor.endLine():
            end += 1

        fmt = QTextCharFormat()

        def _hasFocus():
            if ApplicationBase.instance().applicationState() != Qt.ApplicationActive:
                return False
            if self.hasFocus():
                return True
            fw = ApplicationBase.instance().focusWidget()
            return fw and self.isAncestorOf(fw)

        if _hasFocus():
            fmt.setBackground(
                QBrush(ApplicationBase.instance().colorSchema().SelFocus))
        else:
            fmt.setBackground(
                QBrush(ApplicationBase.instance().colorSchema().SelNoFocus))

        return createFormatRange(start, end - start, fmt)

    def _findResultFormatRange(self, lineIndex, endLine):
        if not self._highlightFind:
            return None

        key = TextCursor()
        key.moveTo(lineIndex, 0)
        low = bisect.bisect_left(self._highlightFind, key)
        if low >= len(self._highlightFind):
            return None
        if self._highlightFind[low].beginLine() > lineIndex:
            return None

        result = []
        fmt = QTextCharFormat()
        fmt.setBackground(ApplicationBase.instance().colorSchema().FindResult)

        for i in range(low, len(self._highlightFind)):
            r = self._highlightFind[i]
            if r.beginLine() == lineIndex:
                startLine = self.textLineAt(r.beginLine())
                start = startLine.mapToUtf16(r.beginPos())
                end = startLine.mapToUtf16(r.endPos())
                rg = createFormatRange(start, end - start, fmt)
                result.append(rg)
            elif r.beginLine() > lineIndex or r.beginLine() > endLine:
                break

        return result

    def _similarWordRange(self, textLine: TextLine):
        if not self._similarWordPattern:
            return None

        result = []
        fmt = QTextCharFormat()
        fmt.setBackground(ApplicationBase.instance().colorSchema().SimilarWord)

        matches = self._similarWordPattern.globalMatch(textLine.text())
        while matches.hasNext():
            m = matches.next()
            start = m.capturedStart()
            end = m.capturedEnd()
            result.append(createFormatRange(start, end - start, fmt))

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

    def _reloadTextLine(self, textLine):
        if textLine.useBuiltinPatterns:
            textLine.setCustomLinkPatterns(self._bugPatterns)

    def _toFindPattern(self, text, flags):
        exp = text
        exp_flags = re.IGNORECASE

        if not (flags & FindFlags.UseRegExp):
            exp = re.escape(text)
        if flags & FindFlags.CaseSenitively:
            exp_flags = 0
        if flags & FindFlags.WholeWords:
            exp = r'\b' + text + r'\b'

        return re.compile(exp, exp_flags)

    def _findInRange(self, pattern, low, high):
        result = []
        for i in range(low, high):
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

    def _onConvertEvent(self):
        # wait for more text lines
        if self._inReading and self._convertIndex >= self.textLineCount():
            return

        textLine = self.textLineAt(self._convertIndex)
        self._convertIndex += 1

        if not self._inReading and self._convertIndex >= self.textLineCount():
            self.killTimer(self._convertTimerId)
            self._convertTimerId = None
            self._convertIndex = 0

        maximum = self.textLineCount() - self._linesPerPage()
        needAdjust = self.verticalScrollBar().maximum() < maximum
        if textLine:
            width = textLine.boundingRect().width()
            if width > self._maxWidth:
                self._maxWidth = width
                needAdjust = True

        if needAdjust:
            self._adjustScrollbars()
            self.ensureCursorVisible(True)

    def _onUpdateSettings(self):
        self.reloadSettings()

        if self._settingsTimer:
            self._settingsTimer.disconnect(self)
            self._settingsTimer = None

        # TODO: move to background
        for _, line in self._textLines.items():
            self._reloadTextLine(line)

        self._adjustScrollbars()
        self.viewport().update()

    def _onFindEvent(self):
        low, high = self._findCurPageRange
        if self._findIndex > high:
            findPart = FindPart.AfterCurPage
            # Search from beginning
            if self._findIndex == self.textLineCount():
                self._findIndex = 0
                findPart = FindPart.BeforeCurPage
        else:
            findPart = FindPart.BeforeCurPage

        assert (self._findIndex < low or high < self._findIndex)

        begin = self._findIndex
        end = begin + 1000
        pattern = self._findPattern
        if findPart == FindPart.AfterCurPage:
            if end >= self.textLineCount():
                end = self.textLineCount()
        else:
            if end >= low:
                end = low

        self._findIndex = end

        result = self._findInRange(pattern, begin, end)
        if result:
            self.findResultAvailable.emit(result, findPart)

        if findPart == FindPart.AfterCurPage:
            if low == 0 and self._findIndex == self.textLineCount():
                self.cancelFind()
        else:
            if self._findIndex == low:
                self.cancelFind()

    def paintEvent(self, event):
        if not self.hasTextLines():
            return

        painter = QPainter(self.viewport())
        eventRect = event.rect()

        if eventRect.isValid():
            startLine = self.textRowForPos(eventRect.topLeft())
            endLine = self.textRowForPos(eventRect.bottomRight()) + 1
        else:
            startLine = self.firstVisibleLine()
            endLine = startLine + self._linesPerPage() + 1
        endLine = min(self.textLineCount(), endLine)

        offset = self.contentOffset()
        offset.setY(offset.y() + (startLine -
                                  self.firstVisibleLine()) * self.lineHeight)
        viewportRect = self.viewport().rect()

        painter.setClipRect(eventRect)

        highlightLineBg = ApplicationBase.instance().colorSchema().HighlightLineBg

        borderStartLine = -1
        borderRect = QRectF()
        for i in range(startLine, endLine):
            textLine = self.textLineAt(i)

            br = textLine.boundingRect()
            r = br.translated(offset)

            def lineRect():
                fr = QRectF(br)
                fr.moveTop(fr.top() + r.top())
                fr.setLeft(0)
                fr.setRight(viewportRect.width() - offset.x())
                return fr

            if i in self._highlightLines:
                painter.fillRect(lineRect(), highlightLineBg)
            else:
                self.drawLineBackground(painter, textLine, lineRect())

            # TODO: move to subclass???
            if self.canDrawLineBorder(textLine):
                if borderStartLine == -1:
                    borderStartLine = i
                    borderRect = lineRect()
                else:
                    borderRect.setBottom(lineRect().bottom())
            elif borderStartLine != -1:
                self.drawLinesBorder(painter, borderRect)
                borderStartLine = -1
                borderRect = QRectF()

            formats = []

            similarWordRg = self._similarWordRange(textLine)
            if similarWordRg:
                formats.extend(similarWordRg)

            # find result
            findRg = self._findResultFormatRange(i, endLine)
            if findRg:
                formats.extend(findRg)

            # TextLine format
            textLineRg = self.textLineFormatRange(textLine)
            if textLineRg:
                formats.extend(textLineRg)

            # selection
            selectionRg = self._selectionFormatRange(i)
            if selectionRg:
                formats.append(selectionRg)

            textLine.draw(painter, offset, formats, QRectF(eventRect))

            offset.setY(offset.y() + self._lineHeight)

            if offset.y() > viewportRect.height():
                break

        if borderStartLine != -1:
            self.drawLinesBorder(painter, borderRect)

    def resizeEvent(self, event):
        self._adjustScrollbars()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        if not self.hasTextLines():
            return

        self._clickOnLink = self._link is not None
        self._invalidateSelection()

        # FIXME: delay a while to avoid clearing by double click
        # Qt.MouseEventCreatedDoubleClick flag doesn't help
        if self._similarWordPattern is not None:
            self._similarWordPattern = None
            self.viewport().update()

        textLine = self.textLineForPos(event.position())
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
            offset = textLine.offsetForPos(
                self.mapToContents(event.position()))
            self._cursor.moveTo(textLine.lineNo(), offset)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.source() == Qt.MouseEventNotSynthesized and \
                self._autoScrollTimer.isActive():
            self._autoScrollTimer.stop()

        if event.button() != Qt.LeftButton:
            return

        if self._link and self._clickOnLink:
            self.linkActivated.emit(self._link)

        self._clickOnLink = False
        if not self.hasTextLines() or \
                self._cursor.hasSelection():
            return

        textLine = self.textLineForPos(event.position())
        if not textLine:
            return

        self.textLineClicked.emit(textLine)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        if not self.hasTextLines():
            return

        self._clickTimer.restart()
        self._invalidateSelection()
        self._cursor.clear()

        textLine = self.textLineForPos(event.position())
        if not textLine:
            return

        offset = textLine.offsetForPos(self.mapToContents(event.position()))
        begin = offset
        end = offset

        # find the word
        isWord = False
        content = textLine.text()
        if offset < len(content) and self._isLetter(content[offset]):
            isWord = True
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
        referWordPattern = None
        if word:
            self._cursor.moveTo(textLine.lineNo(), begin)
            self._cursor.selectTo(textLine.lineNo(), end)
            self._invalidateSelection()

            word = word.strip()
            if word:
                referWordPattern = QRegularExpression(r"\b{}\b".format(
                    word)) if isWord else QRegularExpression(r"{}".format(re.escape(word)))
        if self._similarWordPattern != referWordPattern:
            self._similarWordPattern = referWordPattern
            self.viewport().update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._clickTimer.isValid():
            self._clickTimer.invalidate()

        self._clickOnLink = False
        self._link = None
        if not self.hasTextLines():
            return

        pos = event.position().toPoint()
        textLine = self.textLineForPos(pos)
        if not textLine:
            return

        offset = textLine.offsetForPos(self.mapToContents(pos))
        if event.buttons() == Qt.LeftButton:
            self._invalidateSelection()

            n = textLine.lineNo()
            self._cursor.selectTo(n, offset)

            self._invalidateSelection()

            if event.source() == Qt.MouseEventNotSynthesized:
                visibleRect = self.viewport().rect()
                if visibleRect.contains(pos):
                    self._autoScrollTimer.stop()
                elif not self._autoScrollTimer.isActive():
                    self._autoScrollTimer.start(100, self)
        elif event.buttons() == Qt.NoButton:
            x = pos.x() + self.horizontalScrollBar().value()
            if textLine.boundingRect().right() >= x:
                self._link = textLine.hitTest(offset)
                if self._link:
                    self.updateLinkData(self._link, textLine.lineNo())

        cursorShape = Qt.PointingHandCursor if self._link \
            else Qt.IBeamCursor
        self.viewport().setCursor(cursorShape)

    def contextMenuEvent(self, event):
        menu = self.contextMenu
        self.updateContextMenu(event.pos())
        menu.exec(event.globalPos())

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy()
        elif event.matches(QKeySequence.SelectAll):
            self.selectAll()
        elif event.matches(QKeySequence.MoveToStartOfDocument):
            self.verticalScrollBar().triggerAction(
                QScrollBar.SliderToMinimum)
        elif event.matches(QKeySequence.MoveToEndOfDocument):
            self.verticalScrollBar().triggerAction(
                QScrollBar.SliderToMaximum)
        elif event.matches(QKeySequence.MoveToPreviousPage):
            self.verticalScrollBar().triggerAction(
                QScrollBar.SliderPageStepSub)
        elif event.matches(QKeySequence.MoveToNextPage):
            self.verticalScrollBar().triggerAction(
                QScrollBar.SliderPageStepAdd)
        elif event.matches(QKeySequence.StandardKey.SelectNextChar):
            self._cursor.selectNextChar()
            self.ensureSelectionVisible()
            self.viewport().update()
        elif event.matches(QKeySequence.StandardKey.SelectPreviousChar):
            self._cursor.selectPreviousChar()
            self.ensureSelectionVisible()
            self.viewport().update()
        elif event.matches(QKeySequence.StandardKey.SelectNextLine):
            self._cursor.selectNextLine()
            self.ensureSelectionVisible()
            self.viewport().update()
        elif event.matches(QKeySequence.StandardKey.SelectPreviousLine):
            self._cursor.selectPreviousLine()
            self.ensureSelectionVisible()
            self.viewport().update()
        elif event.matches(QKeySequence.StandardKey.Find):
            self.executeFind()
        else:
            super().keyPressEvent(event)

    def timerEvent(self, event):
        id = event.timerId()
        if id == self._convertTimerId:
            self._onConvertEvent()
        elif id == self._findTimerId:
            self._onFindEvent()
        elif id == self._autoScrollTimer.timerId():
            self._handleAutoScroll()

    def _handleAutoScroll(self):
        visible = self.viewport().rect()
        pos = QPoint()

        globalPos = QCursor.pos()
        pos = self.viewport().mapFromGlobal(globalPos)
        topPos = self.viewport().mapTo(self.topLevelWidget(), pos)
        ev = QMouseEvent(QEvent.MouseMove, pos, topPos, globalPos,
                         Qt.LeftButton, Qt.LeftButton, ApplicationBase.instance().keyboardModifiers())
        self.mouseMoveEvent(ev)

        deltaY = max(pos.y() - visible.top(), visible.bottom() -
                     pos.y()) - visible.height()
        deltaX = max(pos.x() - visible.left(),
                     visible.right() - pos.x()) - visible.width()
        delta = max(deltaX, deltaY)
        if delta >= 0:
            if delta < 7:
                delta = 7
            timeout = 4900 / (delta * delta)
            self._autoScrollTimer.start(timeout, self)

            if deltaY > 0:
                vbar = self.verticalScrollBar()
                vbar.triggerAction(QAbstractSlider.SliderSingleStepSub if pos.y(
                ) < visible.center().y() else QAbstractSlider.SliderSingleStepAdd)
            if deltaX > 0:
                hbar = self.horizontalScrollBar()
                hbar.triggerAction(QAbstractSlider.SliderSingleStepSub if pos.x(
                ) < visible.center().x() else QAbstractSlider.SliderSingleStepAdd)

    def event(self, evt):
        if evt.type() == QEvent.PaletteChange:
            self._onColorSchemeChanged()

        return super().event(evt)

    def _onColorSchemeChanged(self):
        for _, line in self._textLines.items():
            line.reapplyColorTheme()

        self.viewport().update()

    def setTextMargins(self, margin):
        self.setViewportMargins(margin, margin, margin, margin)

    def textMargins(self):
        return self.viewportMargins().left()

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange:
            if not self.isActiveWindow():
                self._autoScrollTimer.stop()

    def executeFind(self):
        if not self._findWidget:
            self._findWidget = FindWidget(self.viewport(), self)
            self._findWidget.find.connect(self._onFind)
            self._findWidget.cursorChanged.connect(
                self._onFindCursorChanged)
            self._findWidget.afterHidden.connect(
                self._onFindHidden)
            self.findFinished.connect(
                self._findWidget.findFinished)

        text = self.selectedText
        if text:
            # first line only
            text = text.lstrip('\n')
            index = text.find('\n')
            if index != -1:
                text = text[:index]
            self._findWidget.setText(text)
        self._findWidget.showAnimate()

    def _onFind(self, text, flags):
        self._findWidget.updateFindResult([])
        self.highlightFindResult([])

        if self.textLineCount() > 3000:
            self.curIndexFound = False
            if self.findAllAsync(text, flags):
                self._findWidget.findStarted()
        else:
            findResult = self.findAll(text, flags)
            if findResult:
                self._onFindResultAvailable(findResult, FindPart.All)

    def _onFindCursorChanged(self, cursor):
        self.select(cursor)

    def _onFindHidden(self):
        self.highlightFindResult([])
        self.cancelFind()

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

        self._findWidget.updateFindResult(result, curFindIndex, findPart)

    def closeFindWidget(self):
        if self._findWidget and self._findWidget.isVisible():
            self._findWidget.hideAnimate()
            return True
        return False

    def canFindNext(self):
        if not self._findWidget:
            return False
        return self._findWidget.isVisible() and self._findWidget.canFindNext()

    def canFindPrevious(self):
        if not self._findWidget:
            return False
        return self._findWidget.isVisible() and self._findWidget.canFindPrevious()

    def findNext(self):
        if self._findWidget:
            self._findWidget.findNext()

    def findPrevious(self):
        if self._findWidget:
            self._findWidget.findPrevious()

    @property
    def findWidget(self):
        return self._findWidget
