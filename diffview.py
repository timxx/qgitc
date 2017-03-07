# --*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *
from collections import namedtuple

from common import *

import subprocess
import re
import bisect


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
diff_begin_re = re.compile("^@{2,}( (\+|\-)[0-9]+(,[0-9]+)?)+ @{2,}")
diff_begin_bre = re.compile(b"^@{2,}( (\+|\-)[0-9]+(,[0-9]+)?)+ @{2,}")

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
        layout.setContentsMargins(0, 0, 0, 0)
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
        self.treeWidget.itemDoubleClicked.connect(
            self.__onTreeItemDoubleClicked)

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

    def __onTreeItemDoubleClicked(self, item, column):
        if not item or item == self.treeWidget.topLevelItem(0):
            return

        if not self.commit:
            return

        filePath = item.text(0)
        externalDiff(self.commit, filePath)

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


class Link():
    Sha1 = 0
    BugId = 1
    Email = 2

    def __init__(self, offset, start, end, type):
        self.offset = offset  # block position
        self.start = start
        self.end = end
        self.type = type
        self.data = None
        self.clickHandler = None

    def setData(self, data):
        self.data = data

    def hitTest(self, pos):
        return (self.offset + self.start) <= pos and \
            pos <= (self.offset + self.end)

    def onClicked(self):
        if self.clickHandler:
            self.clickHandler(self)
        else:
            QDesktopServices.openUrl(QUrl(self.data))

    def setClickHandler(self, handler):
        self.clickHandler = handler


class ColorSchema():

    def __init__(self, palette):
        self._clrNewline = QColor(0, 0, 255)
        self._clrAdding = QColor(0, 128, 0)
        self._clrDeletion = QColor(255, 0, 0)
        self._clrInfo = QColor(170, 170, 170)
        self._clrLink = palette.link().color()
        self._clrSpace = QColor(Qt.lightGray)

    def newLine(self):
        return self._clrNewline

    def adding(self):
        return self._clrAdding

    def deletion(self):
        return self._clrDeletion

    def info(self):
        return self._clrInfo

    def link(self):
        return self._clrLink

    def space(self):
        return self._clrSpace


class TextBlockData(QTextBlockUserData):

    def __init__(self):
        super(TextBlockData, self).__init__()
        self.type = ItemInvalid
        self.links = []

    def hasLink(self):
        return len(self.links) > 0

    def addLink(self, link):
        self.links.append(link)


class DiffHighlighter(QSyntaxHighlighter):

    def __init__(self, cs, parent):
        super(DiffHighlighter, self).__init__(parent)

        self._cs = cs
        self._fmtSpaces = QTextCharFormat()
        self._fmtSpaces.setForeground(cs.space())

    def highlightBlock(self, text):
        if not text:
            return

        data = self.currentBlockUserData()
        if not data:
            return

        tcFormat = QTextCharFormat()

        if data.type == ItemFile or data.type == ItemFileInfo:
            font = self.document().defaultFont()
            font.setBold(True)
            tcFormat.setFont(font)
        elif diff_begin_re.search(text) or text.startswith("\ No newline "):
            tcFormat.setForeground(self._cs.newLine())
        elif text.lstrip().startswith("+"):
            tcFormat.setForeground(self._cs.adding())
        elif text.lstrip().startswith("-"):
            tcFormat.setForeground(self._cs.deletion())

        self.setFormat(0, len(text), tcFormat)

        if data.hasLink():
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
            fmt.setForeground(self._cs.link())
            for link in data.links:
                self.setFormat(link.start, link.end - link.start, fmt)

        self.applyWhitespaces(text)

    def applyWhitespaces(self, text):
        offset = 0
        length = len(text)
        while offset < length:
            if text[offset].isspace():
                start = offset
                offset += 1
                while offset < length and text[offset].isspace():
                    offset += 1
                self.setFormat(start, offset - start, self._fmtSpaces)
            else:
                offset += 1


class PatchViewer(QPlainTextEdit):
    fileRowChanged = pyqtSignal(int)
    requestCommit = pyqtSignal(str)

    def __init__(self, parent=None):
        super(PatchViewer, self).__init__(parent)

        self.setReadOnly(True)
        self.setWordWrapMode(QTextOption.NoWrap)
        self.viewport().setMouseTracking(True)

        self.cs = ColorSchema(self.palette())
        self.highlighter = DiffHighlighter(self.cs, self.document())

        self.updateSettings()

        self.sha1Re = re.compile("\\b[a-f0-9]{7,40}\\b")
        self.emailRe = re.compile(
            "[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

        self.currentLink = None
        self.clickOnLink = False

        self.verticalScrollBar().valueChanged.connect(
            self.__onVScollBarValueChanged)

    def __openLink(self, link):
        url = None
        if link.type == Link.Sha1:
            self.requestCommit.emit(link.data)
        elif link.type == Link.Email:
            url = "mailto:" + link.data
        elif link.type == Link.BugId:
            url = self.bugUrl + link.data

        if url:
            QDesktopServices.openUrl(QUrl(url))

    def __lineItemToTextBlock(self, textCursor, lineItem):
        block = textCursor.block()
        block.setUserData(self.__createBlockData(block, lineItem))
        textCursor.insertText(lineItem.content)

    def __createBlockData(self, block, item):
        data = TextBlockData()
        data.type = item.type

        if not item.content:
            return data

        if item.type == ItemFile or \
                item.type == ItemFileInfo:
            return data

        patterns = {Link.Sha1: self.sha1Re,
                    Link.Email: self.emailRe}

        if self.bugRe and self.bugUrl:
            patterns[Link.BugId] = self.bugRe

        foundLinks = []
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
                i = bisect.bisect_left(foundLinks, (m.start(), m.end()))
                for x in range(i, len(foundLinks)):
                    start, end = foundLinks[x]
                    if (start <= m.start() and m.start() <= end) \
                            or (start <= m.end() and m.end() <= end):
                        found = True
                        break
                # not allow links in the same range
                if found:
                    continue

                link = Link(block.position(), m.start(), m.end(), linkType)
                link.setClickHandler(self.__openLink)
                link.setData(m.group(0))

                data.addLink(link)
                bisect.insort(foundLinks, (m.start(), m.end()))

        return data

    def __onVScollBarValueChanged(self, value):
        block = self.firstVisibleBlock()
        while block.isValid():
            data = block.userData()
            itemType = ItemInvalid if not data else data.type
            if itemType == ItemFile:
                self.fileRowChanged.emit(block.blockNumber())
                break
            elif itemType == ItemParent or itemType == ItemAuthor:
                self.fileRowChanged.emit(0)
                break

            block = block.previous()

    def __updateCursorAndLink(self, pos, leftButtonPressed):
        self.currentLink = None
        textCursor = self.cursorForPosition(pos)
        if not textCursor.isNull():
            onText = self.cursorRect(textCursor).right() >= pos.x()
            if not onText:
                nextPos = textCursor
                nextPos.movePosition(QTextCursor.Right)
                onText = self.cursorRect(nextPos).right() >= pos.x()

            data = textCursor.block().userData()
            if onText and data:
                for link in data.links:
                    if link.hitTest(textCursor.position()):
                        self.currentLink = link
                        break

        if not leftButtonPressed and self.currentLink:
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.IBeamCursor)

    def updateSettings(self):
        settings = QApplication.instance().settings()
        self.document().setDefaultFont(settings.diffViewFont())

        self.bugUrl = settings.bugUrl()
        self.bugRe = re.compile(settings.bugPattern())

        self.showWhiteSpace = settings.showWhitespace()
        tabSize = settings.tabSize()

        option = self.document().defaultTextOption()
        if self.showWhiteSpace:
            option.setFlags(option.flags() | QTextOption.ShowTabsAndSpaces)
        else:
            option.setFlags(option.flags() & ~QTextOption.ShowTabsAndSpaces)

        fm = QFontMetrics(settings.diffViewFont())
        option.setTabStop(tabSize * fm.width(' '))
        self.document().setDefaultTextOption(option)

        # TODO: rehighlight only when font and show whitespaces changed
        self.highlighter.rehighlight()

    def setData(self, data):
        self.clear()
        self.currentLink = None

        if not data:
            return

        textCursor = self.textCursor()
        textCursor.beginEditBlock()

        self.__lineItemToTextBlock(textCursor, data[0])

        for i in range(1, len(data)):
            textCursor.insertBlock()
            self.__lineItemToTextBlock(textCursor, data[i])

        textCursor.endEditBlock()
        # scroll to comments
        self.moveCursor(QTextCursor.Start)

    def scrollToRow(self, row):
        block = self.document().findBlockByNumber(row)
        if block.isValid():
            self.moveCursor(QTextCursor.End)
            self.setTextCursor(QTextCursor(block))

    def fillBackground(self, p, rect, brush, gradientRect=QRectF()):
        p.save()
        if brush.style() >= Qt.LinearGradientPattern and brush.style() <= Qt.ConicalGradientPattern:
            if not gradientRect.isNull():
                m = QTransform.fromTranslate(
                    gradientRect.left(), gradientRect.top())
                m.scale(gradientRect.width(), gradientRect.height())
                brush.setTransform(m)
                brush.gradient().setCoordinateMode(QGradient.LogicalMode)
        else:
            p.setBrushOrigin(rect.topLeft())

        p.fillRect(rect, brush)
        p.restore()

    def paintEvent(self, event):
        # taken from QPlainTextEdit::paintEvent
        painter = QPainter(self.viewport())
        offset = QPointF(self.contentOffset())

        er = event.rect()
        viewportRect = self.viewport().rect()

        block = self.firstVisibleBlock()
        maximumWidth = self.document().documentLayout().documentSize().width()

        # Set a brush origin so that the WaveUnderline knows where the wave
        # started
        painter.setBrushOrigin(offset)

        # keep right margin clean from full-width selection
        maxX = offset.x() + max(viewportRect.width(), maximumWidth) - \
            self.document().documentMargin()
        er.setRight(min(er.right(), maxX))
        painter.setClipRect(er)

        context = self.getPaintContext()

        while block.isValid():
            r = self.blockBoundingRect(block).translated(offset)
            layout = block.layout()

            if not block.isVisible():
                offset.setY(offset.y() + r.height())
                block = block.next()
                continue

            if r.bottom() >= er.top() and r.top() <= er.bottom():
                blockFormat = block.blockFormat()

                bg = blockFormat.background()
                if bg != Qt.NoBrush:
                    contentsRect = r
                    contentsRect.setWidth(max(r.width(), maximumWidth))
                    self.fillBackground(painter, contentsRect, bg)

                # file info background
                itemType = ItemInvalid if not block.userData() else block.userData().type
                if itemType == ItemFile or itemType == ItemFileInfo:
                    # one line one block
                    rr = layout.lineForTextPosition(0).rect()
                    rr.moveTop(rr.top() + r.top())
                    rr.setLeft(0)
                    rr.setRight(viewportRect.width() - offset.x())
                    painter.fillRect(rr, self.cs.info())

                selections = []
                blpos = block.position()
                bllen = block.length()
                for i in range(0, len(context.selections)):
                    rg = context.selections[i]
                    selStart = rg.cursor.selectionStart() - blpos
                    selEnd = rg.cursor.selectionEnd() - blpos
                    if selStart < bllen and selEnd > 0 and selEnd > selStart:
                        o = QTextLayout.FormatRange()
                        o.start = selStart
                        o.length = selEnd - selStart
                        o.format = rg.format
                        selections.append(o)
                    elif not rg.cursor.hasSelection() and rg.format.hasProperty(QTextFormat.FullWidthSelection) \
                            and block.contains(rg.cursor.position()):
                        # for full width selections we don't require an actual selection, just
                        # a position to specify the line. that's more
                        # convenience in usage.
                        o = QTextLayout.FormatRange()
                        l = layout.lineForTextPosition(
                            rg.cursor.position() - blpos)
                        o.start = l.textStart()
                        o.length = l.textLength()
                        if o.start + o.length == bllen - 1:
                            o.length += 1  # include newline
                        o.format = rg.format
                        selections.append(o)

                layout.draw(painter, offset, selections, QRectF(er))

            offset.setY(offset.y() + r.height())
            if offset.y() > viewportRect.height():
                break
            block = block.next()

        if self.backgroundVisible() and not block.isValid() and offset.y() <= er.bottom() \
                and (self.centerOnScroll() or self.verticalScrollBar().maximum() == self.verticalScrollBar().minimum()):
            painter.fillRect(QRect(QPoint(er.left(), offset.y()),
                                   er.bottomRight()), self.palette().background())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clickOnLink = self.currentLink is not None

        super(PatchViewer, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and \
                self.clickOnLink and self.currentLink:
            self.currentLink.onClicked()
            self.clickOnLink = False
        else:
            super(PatchViewer, self).mouseReleaseEvent(event)

        self.__updateCursorAndLink(event.pos(), False)

    def mouseMoveEvent(self, event):
        self.clickOnLink = False

        leftButtonPressed = event.buttons() & Qt.LeftButton
        self.__updateCursorAndLink(event.pos(), leftButtonPressed)

        super(PatchViewer, self).mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if not self.currentLink:
            super(PatchViewer, self).mouseDoubleClickEvent(event)
