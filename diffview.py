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
diff_encoding = "utf-8"


class DiffView(QWidget):

    def __init__(self, parent=None):
        super(DiffView, self).__init__(parent)

        self.viewer = PatchViewer(self)
        self.treeWidget = QTreeWidget(self)

        splitter = QSplitter(self)
        splitter.addWidget(self.viewer)
        splitter.addWidget(self.treeWidget)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self.treeWidget.setColumnCount(1)
        self.treeWidget.setHeaderHidden(True)
        self.treeWidget.setRootIsDecorated(False)

        width = self.sizeHint().width()
        sizes = [width * 2 / 3, width * 1 / 3]
        splitter.setSizes(sizes)

        self.treeWidget.currentItemChanged.connect(self.__onTreeItemChanged)
        self.viewer.fileRowChanged.connect(self.__onFileRowChanged)

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

        data = subprocess.check_output(["git", "diff-tree",
                                        "-r", "-p", "--textconv",
                                        "--submodule", "-C",
                                        "--cc", "--no-commit-id",
                                        "-U3", "--root",
                                        commit.sha1])
        lines = data.split(b'\n')

        self.__addToTreeWidget(self.tr("Comments"), 0)

        lineItems = []
        lineItems.extend(self.__commitToLineItems(commit))

        isDiffContent = False

        encodings = ["gb18030", "utf16"]
        if not diff_encoding in encodings:
            encodings.insert(0, diff_encoding)

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
            elif line.startswith(b"@@ "):
                isDiffContent = True
                itemType = ItemDiff
            elif line.startswith(b"--- ") or line.startswith(b"+++ "):
                continue
            elif not line:  # ignore the empty info line
                continue
            else:
                itemType = ItemFileInfo

            # TODO: improve
            for encoding in encodings:
                try:
                    line = line.decode(encoding).rstrip('\r')
                    break
                except UnicodeDecodeError:
                    pass
            lineItems.append(LineItem(itemType, line))

        self.viewer.setData(lineItems)

    def clear(self):
        self.treeWidget.clear()
        self.viewer.setData(None)


class PatchViewer(QAbstractScrollArea):
    fileRowChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super(PatchViewer, self).__init__(parent)

        self.lineItems = []
        self.lineSpace = 5  # space between each line
        # total height of a line
        self.lineHeight = self.fontMetrics().height() + self.lineSpace
        # max line width in current viewport
        self.maxWidth = 0

        self.verticalScrollBar().valueChanged.connect(
            self.__onVScollBarValueChanged)

    def setData(self, items):
        self.lineItems = items

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

    def mouseMoveEvent(self, event):
        pass

    def mousePressEvent(self, event):
        pass

    def resizeEvent(self, event):
        self.__adjust()

    def paintEvent(self, event):
        if not self.lineItems:
            return

        painter = QPainter(self.viewport())

        linesPerPage = self.__linesPerPage()
        linesPerPage = min(self.__totalLines(), linesPerPage)
        startLine = self.verticalScrollBar().value()

        offsetX = self.horizontalScrollBar().value()
        x = 0 - offsetX
        y = self.lineHeight

        # TODO:  selection and many many...
        for i in range(0, linesPerPage):
            item = self.lineItems[i + startLine]

            if self.__drawInfo(painter, item, x, y):
                pass
            elif self.__drawDiff(painter, item, x, y):
                pass
            else:
                painter.drawText(x, y, item.content)

            y += self.lineHeight

    def __drawInfo(self, painter, item, x, y):
        if item.type != ItemFile and item.type != ItemFileInfo:
            return False

        painter.save()
        # first fill background
        painter.fillRect(0,
                         y - self.lineHeight / 2 - self.lineSpace,  # top
                         self.viewport().width(),
                         self.lineHeight,
                         QBrush(QColor(170, 170, 170)))

        # now the text
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(x, y, item.content)

        painter.restore()

        return True

    def __drawDiff(self, painter, item, x, y):
        if item.type != ItemDiff:
            return False

        painter.save()

        pen = painter.pen()
        if item.content.startswith("@@ ") or  \
                item.content.startswith("\ No newline "):
            pen.setColor(QColor(0, 0, 255))
        elif item.content.startswith("+"):
            pen.setColor(QColor(0, 168, 0))
        elif item.content.startswith("-"):
            pen.setColor(QColor(255, 0, 0))

        painter.setPen(pen)
        painter.drawText(x, y, item.content)

        painter.restore()

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

        linesPerPage = self.__linesPerPage()
        totalLines = self.__totalLines()

        offsetY = vScrollBar.value()
        maxY = min(totalLines, offsetY + linesPerPage)

        self.maxWidth = 0
        metrics = QFontMetrics(self.font())
        for i in range(offsetY, maxY):
            # TODO: cache the width
            width = metrics.width(self.lineItems[i].content)
            self.maxWidth = width if width > self.maxWidth else self.maxWidth

        if self.maxWidth > 0:
            hScrollBar.setRange(0, self.maxWidth - self.viewport().width())
            hScrollBar.setPageStep(self.viewport().width())

    def __onVScollBarValueChanged(self, value):
        self.__updateHScrollBar()

        # TODO: improve
        for i in range(value, -1, -1):
            item = self.lineItems[i]
            if item.type == ItemFile:
                self.fileRowChanged.emit(i)
                break
            elif item.type == ItemParent or item.type == ItemAuthor:
                self.fileRowChanged.emit(0)
                break
