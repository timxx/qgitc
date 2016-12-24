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


def createFormatRange(start, length, fmt):
    formatRange = QTextLayout.FormatRange()
    formatRange.start = start
    formatRange.length = length
    formatRange.format = fmt

    return formatRange


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
                rg = createFormatRange(m.start(), m.end() - m.start(), fmt)
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
    requestCommit = pyqtSignal(str)

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
        self.viewer.requestCommit.connect(self.requestCommit)

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
            lineItems.append(LineItem(itemType, line))

        self.viewer.setData(lineItems)

    def clear(self):
        self.treeWidget.clear()
        self.viewer.setData(None)

    def setFilterPath(self, path):
        # no need update
        self.filterPath = path

    def updateSettings(self):
        self.viewer.updateSettings()

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


class Link():
    Sha1 = 0
    BugId = 1
    Email = 2

    def __init__(self, url, rect, linkType):
        self.url = url
        self.rect = rect
        self.linkType = linkType
        self.clickHandler = None

    def setUrl(self, url):
        self.url = url

    def setRect(self, rect):
        self.rect = rect

    def hitTest(self, pos):
        return self.rect.contains(pos)

    def onClicked(self, pos):
        if not self.hitTest(pos):
            return False

        if self.clickHandler:
            self.clickHandler(self.url)
        else:
            QDesktopServices.openUrl(QUrl(self.url))

        return True

    def setClickHandler(self, handler):
        self.clickHandler = handler


class PatchViewer(QAbstractScrollArea):
    fileRowChanged = pyqtSignal(int)
    requestCommit = pyqtSignal(str)

    def __init__(self, parent=None):
        super(PatchViewer, self).__init__(parent)

        # width of LineItem.content
        self.itemWidths = {}

        self.lineItems = []
        self.updateSettings()

        self.highlightPattern = None
        self.highlightField = FindField.Comments
        self.wordPattern = None

        self.selection = Selection()
        self.tripleClickTimer = QElapsedTimer()
        self.clickOnLink = False
        self.cursorChanged = False

        self.links = []
        self.sha1Re = re.compile("\\b[a-f0-9]{7,40}\\b")
        self.emailRe = re.compile(
            "[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

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
        self.viewport().setMouseTracking(True)

    def updateSettings(self):
        # font for comments, file info, diff
        self.fonts = [None, None, None]

        settings = QApplication.instance().settings()
        fm = QFontMetrics(settings.diffViewFont())
        # total height of a line
        self.lineHeight = fm.height()

        self.showWhiteSpace = settings.showWhitespace()
        tabSize = settings.tabSize()
        self.tabstopWidth = fm.width(' ') * tabSize

        self.itemWidths.clear()
        self.bugUrl = settings.bugUrl()
        self.bugRe = re.compile(settings.bugPattern())

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
        if self.tripleClickTimer.isValid():
            self.tripleClickTimer.invalidate()

        if not self.lineItems:
            return

        hoveredLink = False
        self.clickOnLink = False
        for link in self.links:
            if link.hitTest(event.pos()):
                hoveredLink = True
                break

        # is setCursor waste many resource?
        if hoveredLink:
            if not self.cursorChanged:
                self.viewport().setCursor(Qt.PointingHandCursor)
                self.cursorChanged = True
        elif self.cursorChanged:
            self.cursorChanged = False
            self.viewport().setCursor(Qt.IBeamCursor)

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

        if not self.lineItems:
            return

        self.clickOnLink = False
        for link in self.links:
            if link.hitTest(event.pos()):
                self.clickOnLink = True
                break

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
            self.selection.end(line, len(self.__getItem(line).content))
            self.__updateSelection()
        elif index != -1:
            self.selection.begin(line, index)
            self.selection.end(-1, -1)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self.lineItems:
            return

        if not self.clickOnLink:
            return

        self.clickOnLink = False
        for link in self.links:
            if link.onClicked(event.pos()):
                return

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        if not self.lineItems:
            return

        for link in self.links:
            if link.hitTest(event.pos()):
                return

        self.tripleClickTimer.restart()

        self.__updateSelection()
        self.selection.clear()

        line, index = self.__posToContentIndex(event.pos())
        if line == -1 or index == -1:
            return

        # find the word
        content = self.__getItem(line).content
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
            self.selection.begin(line, begin)
            self.selection.end(line, end)
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

        # reset every paints
        self.links.clear()

        for i in range(startLine, endLine):
            item = self.__getItem(i)
            rect = self.__lineRect(i)

            painter.save()

            textLayout = QTextLayout(item.content, self.itemFont(item.type))
            formats = []

            # selection
            selectionRg = self.__selectionFormatRange(i)
            if selectionRg:
                formats.append(selectionRg)

            formats.extend(self.__wordFormatRange(item.content))

            textOption = self.__textOption(item)

            if self.__initCommentsLayout(item, textLayout, formats):
                pass
            elif self.__initInfoLayout(item, textLayout, formats):
                self.__drawInfo(painter, item, rect)
            elif self.__initDiffLayout(item, textLayout, formats):
                pass

            topLeft = QPointF(rect.topLeft())
            self.__findLinks(topLeft, item, formats)

            textLayout.setTextOption(textOption)
            textLayout.setAdditionalFormats(formats)

            textLayout.beginLayout()
            textLine = textLayout.createLine()
            textLine.setPosition(QPointF(0, 0))
            textLayout.endLayout()

            textLayout.draw(painter, topLeft)

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
            fmt = QTextCharFormat()
            fmt.setBackground(QBrush(Qt.yellow))
            for m in matchs:
                rg = createFormatRange(m.start(), m.end() - m.start(), fmt)
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
            rg = createFormatRange(m.start(), m.end() - m.start(), fmt)
            formats.append(rg)

        return formats

    def __selectionFormatRange(self, lineIndex):
        if not self.selection.within(lineIndex):
            return None

        start = 0
        end = len(self.__getItem(lineIndex).content)

        if self.selection.beginLine() == lineIndex:
            start = self.selection.beginPos()
        if self.selection.endLine() == lineIndex:
            end = self.selection.endPos()

        fmt = QTextCharFormat()
        if self.hasFocus():
            fmt.setBackground(QBrush(QColor(173, 214, 255)))
        else:
            fmt.setBackground(QBrush(QColor(229, 235, 241)))

        return createFormatRange(start, end - start + 1, fmt)

    def __initCommentsLayout(self, item, textLayout, formats):
        if not (item.type >= ItemAuthor and item.type <= ItemComments):
            return False

        if self.highlightField == FindField.Comments:
            formats.extend(self.__highlightFormatRange(item.content))

        return True

    def __initInfoLayout(self, item, textLayout, formats):
        if item.type != ItemFile and item.type != ItemFileInfo:
            return False

        return True

    def __drawInfo(self, painter, item, rect):
        painter.fillRect(rect, QBrush(QColor(170, 170, 170)))

    def __initDiffLayout(self, item, textLayout, formats):
        if item.type != ItemDiff:
            return False

        color = QColor()
        if diff_begin_re.search(item.content) or \
                item.content.startswith("\ No newline "):
            color = QColor(0, 0, 255)
        elif item.content.lstrip().startswith("+"):
            color = QColor(0, 128, 0)
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
        if self.showWhiteSpace and textLayout.text().endswith("^M"):
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
                item = self.__getItem(i)

                textLayout = QTextLayout(
                    item.content, self.itemFont(item.type))
                textLayout.setTextOption(self.__textOption(item))
                textLayout.beginLayout()
                textLayout.createLine()
                textLayout.endLayout()

                width = int(textLayout.boundingRect().width())
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
            item = self.__getItem(i)
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
        self.selection.end(lastLine, len(self.__getItem(lastLine)))
        self.__updateSelection()

    def __makeContent(self, item, begin=None, end=None):
        if self.showWhiteSpace and item.type == ItemDiff:
            return item.content[begin:end].rstrip("^M")
        return item.content[begin:end]

    def __doCopy(self, selectionOnly=True):
        if not self.lineItems:
            return
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
            endPos = len(self.__getItem(endLine - 1)) - 1

        content = ""
        # only one line
        if beginLine == endLine:
            item = self.__getItem(beginLine)
            content = self.__makeContent(item, beginPos, endPos + 1)
        else:
            # first line
            content = self.__makeContent(
                self.__getItem(beginLine), beginPos, None)
            beginLine += 1

            # middle lines
            for i in range(beginLine, endLine):
                content += "\n" + self.__makeContent(self.__getItem(i))

            # last line
            content += "\n" + \
                self.__makeContent(self.__getItem(endLine), 0, endPos + 1)

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

        item = self.__getItem(lineIndex)
        if len(item.content) < 2:
            return lineIndex, 0

        font = self.itemFont(item.type)

        textLayout = QTextLayout()
        textLayout.setFont(font)
        textLayout.setTextOption(self.__textOption(item))

        # TODO: improve performance, calc like binary search?
        charIndex = len(item.content) - 1
        for i in range(0, len(item.content)):
            textLayout.setText(item.content[0:i + 1])
            textLayout.beginLayout()
            line = textLayout.createLine()
            textLayout.endLayout()
            width = int(textLayout.boundingRect().width())
            if width > x:
                charIndex = i
                break

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

    def __textOption(self, item):
        textOption = QTextOption()
        textOption.setWrapMode(QTextOption.NoWrap)

        if item.type == ItemDiff:
            textOption.setTabStop(self.tabstopWidth)
            if self.showWhiteSpace:
                textOption.setFlags(QTextOption.ShowTabsAndSpaces)

        return textOption

    def __getItem(self, index):
        """ ugly way to make content consist """
        item = self.lineItems[index]
        if item.type != ItemDiff:
            return item

        if self.showWhiteSpace:
            content = item.content.replace('\r', '^M')
        else:
            content = item.content.rstrip('\r')

        return LineItem(item.type, content)

    def __getLinkRect(self, pos, item, begin, end):
        textLayout = QTextLayout()
        textLayout.setFont(self.itemFont(item.type))
        textLayout.setTextOption(self.__textOption(item))

        ranges = [begin, end]
        rects = []
        for i in ranges:
            substr = item.content[0:i]
            textLayout.setText(substr)
            textLayout.beginLayout()
            textLayout.createLine()
            textLayout.endLayout()
            rect = textLayout.boundingRect()
            rect.moveTo(pos)
            rects.append(rect)

        rects[1].setTopLeft(rects[0].topRight())
        return rects[1]

    def __findLinks(self, pos, item, formats):
        if not item.content:
            return
        if item.type == ItemFile or \
                item.type == ItemFileInfo:
            return

        patterns = {Link.Sha1: self.sha1Re,
                    Link.Email: self.emailRe}

        if self.bugRe and self.bugUrl:
            patterns[Link.BugId] = self.bugRe

        foundLinks = []
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        fmt.setForeground(self.palette().link())

        for linkType, pattern in patterns.items():
            # only find email if item is author
            if linkType != Link.Email and \
                    item.type == ItemAuthor:
                continue
            # search sha1 only if item is parent
            if linkType != Link.Sha1 and \
                    item.type == ItemParent:
                continue

            matches = pattern.finditer(item.content)
            for m in matches:
                found = False
                for l in foundLinks:
                    if m.start() >= l.x() and m.start() <= l.y() \
                            or m.end() >= l.x() and m.end() <= l.y():
                        found = True
                        break
                # not allow links in the same range
                if found:
                    continue

                linkRg = createFormatRange(m.start(), m.end() - m.start(), fmt)
                formats.append(linkRg)

                rect = self.__getLinkRect(pos, item, m.start(), m.end())
                link = Link(None, rect, linkType)

                if linkType == Link.Sha1:
                    url = m.group(0)
                    link.setClickHandler(self.__requestCommit)
                elif linkType == Link.Email:
                    url = "mailto:" + m.group(0)
                else:
                    url = self.bugUrl + m.group(0)
                link.setUrl(url)
                self.links.append(link)
                foundLinks.append(QPoint(m.start(), m.end()))

    def __requestCommit(self, sha1):
        self.requestCommit.emit(sha1)
