# --*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *
from collections import namedtuple

from common import *

import subprocess
import re


# item type for LineItem
ItemInvalid = -1
ItemAuthor = 0
ItemParent = 1
ItemBranch = 2
ItemComments = 3
ItemFile = 4
ItemFileInfo = 5
ItemDiff = 6

# diff line content
LineItem = namedtuple("LineItem", ["type", "content"])

diff_re = re.compile(b"^diff --(git a/(.*) b/(.*)|cc (.*))")
diff_begin_re = re.compile("^@{2,}( (\+|\-)[0-9]+,[0-9]+)+ @{2,}")
diff_begin_bre = re.compile(b"^@{2,}( (\+|\-)[0-9]+,[0-9]+)+ @{2,}")

diff_encoding = "utf-8"


class TreeItemDelegate(QItemDelegate):

    def __init__(self, parent=None):
        super(TreeItemDelegate, self).__init__(parent)
        self.pattern = None

    def paint(self, painter, option, index):
        text = index.data()

        itemSelected = option.state & QStyle.State_Selected
        self.drawBackground(painter, option, index)
        self.drawFocus(painter, option, option.rect)

        textLayout = QTextLayout(text, option.font)
        textOption = QTextOption()
        textOption.setWrapMode(QTextOption.NoWrap)

        textLayout.setTextOption(textOption)

        formats = []
        if index.row() != 0 and self.pattern:
            matchs = self.pattern.finditer(text)
            fmt = QTextCharFormat()
            if itemSelected:
                fmt.setForeground(QBrush(Qt.yellow))
            else:
                fmt.setBackground(QBrush(Qt.yellow))
            for m in matchs:
                rg = QTextLayout.FormatRange()
                rg.start = m.start()
                rg.length = m.end() - rg.start
                rg.format = fmt
                formats.append(rg)

        textLayout.setAdditionalFormats(formats)

        textLayout.beginLayout()
        line = textLayout.createLine()
        line.setPosition(QPointF(0, 0))
        textLayout.endLayout()

        painter.save()
        if itemSelected:
            painter.setPen(option.palette.color(QPalette.HighlightedText))
        else:
            painter.setPen(option.palette.color(QPalette.WindowText))

        textLayout.draw(painter, QPointF(option.rect.topLeft()))
        painter.restore()

    def setHighlightPattern(self, pattern):
        self.pattern = pattern


class DiffView(QWidget):

    def __init__(self, parent=None):
        super(DiffView, self).__init__(parent)

        self.viewer = PatchViewer(self)
        self.treeWidget = QTreeWidget(self)
        self.filterPath = None
        self.twMenu = QMenu()
        self.commit = None

        self.twMenu.addAction(self.tr("External &diff"),
                              self.__onExternalDiff)
        self.twMenu.addAction(self.tr("&Copy path"),
                              self.__onCopyPath)

        splitter = QSplitter(self)
        splitter.addWidget(self.viewer)
        splitter.addWidget(self.treeWidget)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.treeWidget.setColumnCount(1)
        self.treeWidget.setHeaderHidden(True)
        self.treeWidget.setRootIsDecorated(False)
        self.treeWidget.header().setStretchLastSection(False)
        self.treeWidget.header().setResizeMode(QHeaderView.ResizeToContents)

        self.itemDelegate = TreeItemDelegate(self)
        self.treeWidget.setItemDelegate(self.itemDelegate)

        width = self.sizeHint().width()
        sizes = [width * 2 / 3, width * 1 / 3]
        splitter.setSizes(sizes)

        self.treeWidget.currentItemChanged.connect(self.__onTreeItemChanged)
        self.viewer.fileRowChanged.connect(self.__onFileRowChanged)

        self.treeWidget.installEventFilter(self)

    def __onTreeItemChanged(self, current, previous):
        if current:
            row = current.data(0, Qt.UserRole)
            self.viewer.scrollToRow(row)

    def __onFileRowChanged(self, row):
        for i in range(self.treeWidget.topLevelItemCount()):
            item = self.treeWidget.topLevelItem(i)
            n = item.data(0, Qt.UserRole)
            if n == row:
                self.treeWidget.blockSignals(True)
                self.treeWidget.setCurrentItem(item)
                self.treeWidget.blockSignals(False)
                break

    def __onExternalDiff(self):
        item = self.treeWidget.currentItem()
        if not item:
            return
        if not self.commit:
            return
        filePath = item.text(0)
        externalDiff(self.commit, filePath)

    def __onCopyPath(self):
        item = self.treeWidget.currentItem()
        if not item:
            return

        clipboard = QApplication.clipboard()
        clipboard.setText(item.text(0))

    def __addToTreeWidget(self, string, row):
        """specify the @row number of the file in the viewer"""
        item = QTreeWidgetItem([string])
        item.setData(0, Qt.UserRole, row)
        self.treeWidget.addTopLevelItem(item)
        if row == 0:
            self.treeWidget.setCurrentItem(item)

    def __commitToLineItems(self, commit):
        items = []
        item = LineItem(ItemAuthor,
                        self.tr("Author: ") + commit.author +
                        " " + commit.authorDate)
        items.append(item)

        item = LineItem(ItemAuthor,
                        self.tr("Committer: ") + commit.commiter +
                        " " + commit.commiterDate)

        items.append(item)

        # TODO: get commit info
        for parent in commit.parents:
            item = LineItem(ItemParent, self.tr("Parent: ") + parent)
            items.append(item)

        # TODO: add child, branch etc...

        items.append(LineItem(ItemComments, ""))

        comments = commit.comments.split('\n')
        for comment in comments:
            content = comment if not comment else "    " + comment
            item = LineItem(ItemComments, content)
            items.append(item)

        items.append(LineItem(ItemComments, ""))

        return items

    # TODO: shall we cache the commit?
    def showCommit(self, commit):
        self.clear()
        self.commit = commit

        data = getCommitRawDiff(commit.sha1, self.filterPath)
        lines = data.split(b'\n')

        self.__addToTreeWidget(self.tr("Comments"), 0)

        lineItems = []
        lineItems.extend(self.__commitToLineItems(commit))

        isDiffContent = False
        lastEncoding = None

        for line in lines:
            match = diff_re.search(line)
            if match:
                fileA = None
                fileB = None
                if match.group(4):  # diff --cc
                    fileA = match.group(4).decode(diff_encoding)
                else:
                    fileA = match.group(2).decode(diff_encoding)
                    fileB = match.group(3).decode(diff_encoding)

                row = len(lineItems)
                self.__addToTreeWidget(fileA, row)
                # renames, keep new file name only
                if fileB and fileB != fileA:
                    lineItems.append(LineItem(ItemFile, fileB))
                    self.__addToTreeWidget(fileB, row)
                else:
                    lineItems.append(LineItem(ItemFile, fileA))

                isDiffContent = False

                continue

            itemType = ItemInvalid

            if isDiffContent:
                itemType = ItemDiff
            elif diff_begin_bre.search(line):
                isDiffContent = True
                itemType = ItemDiff
            elif line.startswith(b"--- ") or line.startswith(b"+++ "):
                continue
            elif not line:  # ignore the empty info line
                continue
            else:
                itemType = ItemFileInfo

            line, lastEncoding = decodeDiffData(line, lastEncoding)
            if itemType != ItemDiff:
                line = line.rstrip('\r')
            else:
                line = line.replace('\r', '^M')
            lineItems.append(LineItem(itemType, line))

        self.viewer.setData(lineItems)

    def clear(self):
        self.treeWidget.clear()
        self.viewer.setData(None)

    def setFilterPath(self, path):
        # no need update
        self.filterPath = path

    def updateSettings(self):
        self.viewer.resetFont()

    def highlightKeyword(self, pattern, field=FindField.Comments):
        self.viewer.highlightKeyword(pattern, field)
        if field == FindField.Paths:
            self.itemDelegate.setHighlightPattern(pattern)
        else:
            self.itemDelegate.setHighlightPattern(None)
        self.treeWidget.viewport().update()

    def eventFilter(self, obj, event):
        if obj != self.treeWidget:
            return False

        if event.type() != QEvent.ContextMenu:
            return False

        item = self.treeWidget.currentItem()
        if not item:
            return False

        if self.treeWidget.topLevelItemCount() < 2:
            return False

        if item == self.treeWidget.topLevelItem(0):
            return False

        self.twMenu.exec(event.globalPos())

        return False


class Selection():

    def __init__(self):
        self.clear()

    def clear(self):
        self._beginLine = -1
        self._beginPos = -1
        self._endLine = -1
        self._endPos = -1

    def hasSelection(self):
        return self._beginLine != -1 and self._endLine != -1

    def within(self, line):
        if not self.hasSelection():
            return False

        if line >= self.beginLine() and line <= self.endLine():
            return True

        return False

    def beginLine(self):
        return min(self._beginLine, self._endLine)

    def endLine(self):
        return max(self._beginLine, self._endLine)

    def beginPos(self):
        if self._beginLine == self._endLine:
            return min(self._beginPos, self._endPos)
        elif self._beginLine < self._endLine:
            return self._beginPos
        else:
            return self._endPos

    def endPos(self):
        if self._beginLine == self._endLine:
            return max(self._beginPos, self._endPos)
        elif self._beginLine < self._endLine:
            return self._endPos
        else:
            return self._beginPos

    def begin(self, line, pos):
        self._beginLine = line
        self._beginPos = pos

    def end(self, line, pos):
        self._endLine = line
        self._endPos = pos


class PatchViewer(QAbstractScrollArea):
    fileRowChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super(PatchViewer, self).__init__(parent)

        self.lineItems = []
        self.resetFont()

        self.showWhiteSpace = True
        self.highlightPattern = None
        self.highlightField = FindField.Comments
        self.wordPattern = None

        # width of LineItem.content
        self.itemWidths = {}

        self.selection = Selection()
        self.tripleClickTimer = QElapsedTimer()

        self.menu = QMenu()
        action = self.menu.addAction(self.tr("&Copy"), self.__onCopy)
        action.setIcon(QIcon.fromTheme("edit-copy"))
        action.setShortcuts(QKeySequence.Copy)

        self.menu.addAction(self.tr("Copy All"), self.__onCopyAll)
        self.menu.addSeparator()

        action = self.menu.addAction(self.tr("Select All"), self.__onSelectAll)
        action.setIcon(QIcon.fromTheme("edit-select-all"))
        action.setShortcuts(QKeySequence.SelectAll)

        # FIXME: show scrollbar always to prevent dead loop
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

        self.verticalScrollBar().valueChanged.connect(
            self.__onVScollBarValueChanged)

        self.viewport().setCursor(Qt.IBeamCursor)

    def resetFont(self):
        # font for comments, file info, diff
        self.fonts = [None, None, None]

        settings = QApplication.instance().settings()
        fm = QFontMetrics(settings.diffViewFont())
        # total height of a line
        self.lineHeight = fm.height()

        self.tabstopWidth = fm.width(' ') * 4

        self.__adjust()

    def setData(self, items):
        self.lineItems = items
        self.itemWidths.clear()
        self.selection.clear()
        self.wordPattern = None

        hScrollBar = self.horizontalScrollBar()
        vScrollBar = self.verticalScrollBar()
        hScrollBar.blockSignals(True)
        vScrollBar.blockSignals(True)

        hScrollBar.setValue(0)
        vScrollBar.setValue(0)

        hScrollBar.blockSignals(False)
        vScrollBar.blockSignals(False)

        self.__adjust()
        self.viewport().update()

    def scrollToRow(self, row):
        vScrollBar = self.verticalScrollBar()
        if vScrollBar.value() != row:
            vScrollBar.blockSignals(True)
            vScrollBar.setValue(row)
            vScrollBar.blockSignals(False)
            self.__updateHScrollBar()
            self.viewport().update()

    def highlightKeyword(self, pattern, field):
        self.highlightPattern = pattern
        self.highlightField = field
        self.viewport().update()

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return

        self.__updateSelection()
        line, index = self.__posToContentIndex(event.pos())
        if line == -1 or index == -1:
            return
        self.selection.end(line, index)
        self.__updateSelection()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        timeout = QApplication.doubleClickInterval()
        # triple click
        isTripleClick = False
        if self.tripleClickTimer.isValid():
            isTripleClick = not self.tripleClickTimer.hasExpired(timeout)
            self.tripleClickTimer.invalidate()

        self.__updateSelection()
        self.wordPattern = None
        line, index = self.__posToContentIndex(event.pos(), not isTripleClick)
        if line == -1:
            return

        if isTripleClick:
            self.selection.begin(line, 0)
            self.selection.end(line, len(self.lineItems[line].content))
            self.__updateSelection()
        elif index != -1:
            self.selection.begin(line, index)
            self.selection.end(-1, -1)

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        self.tripleClickTimer.restart()

        self.__updateSelection()
        self.selection.clear()

        line, index = self.__posToContentIndex(event.pos())
        # find the word
        content = self.lineItems[line].content
        begin = index
        end = index

        for i in range(index - 1, -1, -1):
            if self.__isLetter(content[i]):
                begin = i
                continue
            break

        for i in range(index + 1, len(content)):
            if self.__isLetter(content[i]):
                end = i
                continue
            break

        word = content[begin:end + 1]
        if word:
            word = normalizeRegex(word)
            self.wordPattern = re.compile('\\b' + word + '\\b')
        else:
            self.wordPattern = None
        self.viewport().update()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.__doCopy()
        elif event.matches(QKeySequence.SelectAll):
            self.__onSelectAll()

    def contextMenuEvent(self, event):
        self.menu.exec(event.globalPos())

    def resizeEvent(self, event):
        self.__adjust()

    def paintEvent(self, event):
        if not self.lineItems:
            return

        painter = QPainter(self.viewport())

        startLine = self.verticalScrollBar().value()
        endLine = startLine + self.__linesPerPage() + 1
        endLine = min(len(self.lineItems), endLine)

        for i in range(startLine, endLine):
            item = self.lineItems[i]
            rect = self.__lineRect(i)

            painter.save()

            textLayout = QTextLayout(item.content, self.itemFont(item.type))
            formats = []

            # selection
            selectionRg = self.__selectionFormatRange(i)
            if selectionRg:
                formats.append(selectionRg)

            formats.extend(self.__wordFormatRange(item.content))

            textOption = QTextOption()
            textOption.setWrapMode(QTextOption.NoWrap)

            if self.__initCommentsLayout(item, textLayout, textOption, formats):
                pass
            elif self.__initInfoLayout(item, textLayout, textOption, formats):
                self.__drawInfo(painter, item, rect)
            elif self.__initDiffLayout(item, textLayout, textOption, formats):
                pass

            textLayout.setTextOption(textOption)
            textLayout.setAdditionalFormats(formats)

            textLayout.beginLayout()
            textLine = textLayout.createLine()
            textLine.setPosition(QPointF(0, 0))
            textLayout.endLayout()

            textLayout.draw(painter, QPointF(rect.topLeft()))

            painter.restore()

    def commentsFont(self):
        if not self.fonts[0]:
            settings = QApplication.instance().settings()
            self.fonts[0] = settings.diffViewFont()
        return self.fonts[0]

    def fileInfoFont(self):
        if not self.fonts[1]:
            settings = QApplication.instance().settings()
            self.fonts[1] = settings.diffViewFont()
            self.fonts[1].setBold(True)
        return self.fonts[1]

    def diffFont(self):
        if not self.fonts[2]:
            settings = QApplication.instance().settings()
            self.fonts[2] = settings.diffViewFont()
        return self.fonts[2]

    def itemFont(self, itemType):
        if itemType >= ItemAuthor and itemType <= ItemComments:
            return self.commentsFont()
        elif itemType >= ItemFile and itemType <= ItemFileInfo:
            return self.fileInfoFont()
        else:
            return self.diffFont()

    def __highlightFormatRange(self, text):
        formats = []
        if self.highlightPattern:
            matchs = self.highlightPattern.finditer(text)
            for m in matchs:
                rg = QTextLayout.FormatRange()
                rg.start = m.start()
                rg.length = m.end() - rg.start
                fmt = QTextCharFormat()
                fmt.setBackground(QBrush(Qt.yellow))
                rg.format = fmt
                formats.append(rg)
        return formats

    def __wordFormatRange(self, text):
        if not self.wordPattern:
            return []

        formats = []
        fmt = QTextCharFormat()
        fmt.setTextOutline(QPen(QColor(68, 29, 98)))
        matches = self.wordPattern.finditer(text)
        for m in matches:
            rg = QTextLayout.FormatRange()
            rg.start = m.start()
            rg.length = m.end() - rg.start
            rg.format = fmt
            formats.append(rg)

        return formats

    def __selectionFormatRange(self, lineIndex):
        if not self.selection.within(lineIndex):
            return None

        start = 0
        end = len(self.lineItems[lineIndex].content)

        if self.selection.beginLine() == lineIndex:
            start = self.selection.beginPos()
        if self.selection.endLine() == lineIndex:
            end = self.selection.endPos()

        fmt = QTextCharFormat()
        fmt.setBackground(self.palette().highlight())

        fmtRg = QTextLayout.FormatRange()
        fmtRg.start = start
        fmtRg.length = end - start + 1
        fmtRg.format = fmt

        return fmtRg

    def __initCommentsLayout(self, item, textLayout, textOption, formats):
        if not (item.type >= ItemAuthor and item.type <= ItemComments):
            return False

        if self.highlightField == FindField.Comments:
            formats.extend(self.__highlightFormatRange(item.content))

        return True

    def __initInfoLayout(self, item, textLayout, textOption, formats):
        if item.type != ItemFile and item.type != ItemFileInfo:
            return False

        return True

    def __drawInfo(self, painter, item, rect):
        painter.fillRect(rect, QBrush(QColor(170, 170, 170)))

    def __initDiffLayout(self, item, textLayout, textOption, formats):
        if item.type != ItemDiff:
            return False

        if self.showWhiteSpace:
            textOption.setTabStop(self.tabstopWidth)
            textOption.setFlags(QTextOption.ShowTabsAndSpaces)

        color = QColor()
        if diff_begin_re.search(item.content) or \
                item.content.startswith("\ No newline "):
            color = QColor(0, 0, 255)
        elif item.content.lstrip().startswith("+"):
            color = QColor(0, 168, 0)
        elif item.content.lstrip().startswith("-"):
            color = QColor(255, 0, 0)

        if color.isValid() or self.showWhiteSpace:
            formatRange = QTextLayout.FormatRange()
            formatRange.start = 0
            formatRange.length = len(textLayout.text())
            if color.isValid():
                fmt = QTextCharFormat()
                fmt.setForeground(QBrush(color))
                formatRange.format = fmt
            formats.append(formatRange)

        # format for \r
        if textLayout.text().endswith("^M"):
            fmtCRRg = QTextLayout.FormatRange()
            fmtCRRg.start = len(textLayout.text()) - 2
            fmtCRRg.length = 2
            fmt = QTextCharFormat()
            fmt.setForeground(QBrush(Qt.white))
            fmt.setBackground(QBrush(Qt.black))
            fmtCRRg.format = fmt
            formats.append(fmtCRRg)

        if self.highlightField == FindField.Diffs:
            formats.extend(self.__highlightFormatRange(item.content))

        return True

    def __linesPerPage(self):
        return int(self.viewport().height() / self.lineHeight)

    def __totalLines(self):
        return len(self.lineItems)

    def __adjust(self):

        hScrollBar = self.horizontalScrollBar()
        vScrollBar = self.verticalScrollBar()

        if not self.lineItems:
            hScrollBar.setRange(0, 0)
            vScrollBar.setRange(0, 0)
            return

        linesPerPage = self.__linesPerPage()
        totalLines = self.__totalLines()

        vScrollBar.setRange(0, totalLines - linesPerPage)
        vScrollBar.setPageStep(linesPerPage)

        self.__updateHScrollBar()

    def __updateHScrollBar(self):
        hScrollBar = self.horizontalScrollBar()
        vScrollBar = self.verticalScrollBar()

        if not self.lineItems:
            hScrollBar.setRange(0, 0)
            return

        linesPerPage = self.__linesPerPage()
        totalLines = self.__totalLines()

        offsetY = vScrollBar.value()
        maxY = min(totalLines, offsetY + linesPerPage)

        maxWidth = 0
        for i in range(offsetY, maxY):
            if i in self.itemWidths:
                width = self.itemWidths[i]
            else:
                item = self.lineItems[i]
                fm = QFontMetrics(self.itemFont(item.type))
                width = fm.width(item.content)
                self.itemWidths[i] = width
            maxWidth = max(maxWidth, width)

        hScrollBar.setRange(0, maxWidth - self.viewport().width())
        hScrollBar.setPageStep(self.viewport().width())

    def __onVScollBarValueChanged(self, value):
        self.__updateHScrollBar()

        if not self.lineItems:
            return

        # TODO: improve
        for i in range(value, -1, -1):
            item = self.lineItems[i]
            if item.type == ItemFile:
                self.fileRowChanged.emit(i)
                break
            elif item.type == ItemParent or item.type == ItemAuthor:
                self.fileRowChanged.emit(0)
                break

    def __onCopy(self):
        self.__doCopy()

    def __onCopyAll(self):
        self.__doCopy(False)

    def __onSelectAll(self):
        if not self.lineItems:
            return

        self.wordPattern = None
        self.selection.begin(0, 0)
        lastLine = len(self.lineItems) - 1
        self.selection.end(lastLine, len(self.lineItems[lastLine]))
        self.__updateSelection()

    def __makeContent(self, item, begin=None, end=None):
        if item.type == ItemDiff:
            return item.content[begin:end].rstrip("^M")
        return item.content[begin:end]

    def __doCopy(self, selectionOnly=True):
        if selectionOnly and not self.selection.hasSelection:
            return

        if selectionOnly:
            beginLine = self.selection.beginLine()
            beginPos = self.selection.beginPos()
            endLine = self.selection.endLine()
            endPos = self.selection.endPos()
        else:
            beginLine = 0
            beginPos = 0
            endLine = len(self.lineItems) - 1
            endPos = len(self.lineItems[endLine - 1]) - 1

        content = ""
        # only one line
        if beginLine == endLine:
            item = self.lineItems[beginLine]
            content = self.__makeContent(item, beginPos, endPos + 1)
        else:
            # first line
            content = self.__makeContent(
                self.lineItems[beginLine], beginPos, None)
            beginLine += 1

            # middle lines
            for i in range(beginLine, endLine):
                content += "\n" + self.__makeContent(self.lineItems[i])

            # last line
            content += "\n" + \
                self.__makeContent(self.lineItems[endLine], 0, endPos + 1)

        clipboard = QApplication.clipboard()
        mimeData = QMimeData()
        mimeData.setText(content)

        # TODO: html format support
        clipboard.setMimeData(mimeData)

    def __posToContentIndex(self, pos, calCharIndex=True):
        if not self.lineItems:
            return -1, -1

        lineIndex = int(pos.y() / self.lineHeight)
        lineIndex += self.verticalScrollBar().value()

        if lineIndex >= len(self.lineItems):
            lineIndex = len(self.lineItems) - 1

        if not calCharIndex:
            return lineIndex, -1

        x = pos.x() + self.horizontalScrollBar().value()

        item = self.lineItems[lineIndex]
        font = self.itemFont(item.type)
        fm = QFontMetrics(font)

        charIndex = -1
        # FIXME: fixed pitch not means all chars are the same width
        if QFontInfo(font).fixedPitch():
            charIndex = int(x / fm.width('A'))
        else:
            # TODO: calc char index
            charIndex = int(x / fm.width('A'))

        if not item.content:
            charIndex = 0
        elif charIndex >= len(item.content):
            charIndex = len(item.content) - 1

        return lineIndex, charIndex

    def __lineRect(self, index):
        # the row number in viewport
        row = (index - self.verticalScrollBar().value())

        offsetX = self.horizontalScrollBar().value()
        x = 0 - offsetX
        y = 0 + row * self.lineHeight
        w = self.viewport().width() - x
        h = self.lineHeight

        return QRect(x, y, w, h)

    def __updateSelection(self):
        if self.wordPattern:
            self.viewport().update()
            return

        if not self.selection.hasSelection():
            return

        begin = self.selection.beginLine()
        end = self.selection.endLine()
        rect = self.__lineRect(begin)
        rect.setWidth(self.viewport().width())
        # the rect may not actually the one draws, so add some extra spaces
        rect.setHeight(self.lineHeight * (end - begin + 1) +
                       self.lineHeight / 3)

        self.viewport().update(rect)

    def __isLetter(self, char):
        if char.isalpha():
            return True

        if char == '_':
            return True

        if char.isdigit():
            return True

        return False
