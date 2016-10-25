# --*- coding: utf-8 -*-

from PyQt4.QtGui import *
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
ItemInfo = 4
ItemDiff = 5

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

    def __addToTreeWidget(self, string):
        item = QTreeWidgetItem([string])
        self.treeWidget.addTopLevelItem(item)

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
            item = LineItem(ItemComments, "    " + comment)
            items.append(item)

        items.append(LineItem(ItemComments, ""))

        return items

    def showCommit(self, commit):
        self.clear()

        data = subprocess.check_output(["git", "diff-tree",
                                        "-r", "-p", "--textconv",
                                        "--submodule", "-C",
                                        "--cc", "--no-commit-id",
                                        "-U3", "--root",
                                        commit.sha1])
        lines = data.split(b'\n')

        self.__addToTreeWidget(self.tr("Comments"))

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

                self.__addToTreeWidget(fileA)
                # renames, keep new file name only
                if fileB and fileB != fileA:
                    lineItems.append(LineItem(ItemInfo, fileB))
                    self.__addToTreeWidget(fileB)
                else:
                    lineItems.append(LineItem(ItemInfo, fileA))

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
            else:
                itemType = ItemInfo

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


class PatchViewer(QAbstractScrollArea):

    def __init__(self, parent=None):
        super(PatchViewer, self).__init__(parent)

        self.lineItems = []
        self.lineSpace = 5  # space between each line
        # total height of a line
        self.lineHeight = self.fontMetrics().height() + self.lineSpace
        # char width in English
        self.charWidth = self.fontMetrics().width('W')
        # max line width in current viewport
        self.maxWidth = 0

        self.verticalScrollBar().valueChanged.connect(
            self.__onVScollBarValueChanged)

    def setData(self, items):
        self.lineItems = items

        self.__adjust()
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

        metrics = QFontMetrics(painter.font())
        # TODO: offsetX
        offsetX = self.horizontalScrollBar().value() * self.charWidth
        offsetY = self.verticalScrollBar().value() * self.lineHeight
        x = 0
        y = self.lineHeight

        # TODO: highlight, selection and many many...
        for i in range(0, linesPerPage):
            item = self.lineItems[i + startLine]
            painter.drawText(x - offsetX, y, item.content)
            y += self.lineHeight

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

        offsetY = vScrollBar.value() * self.lineHeight
        maxY = min(totalLines, offsetY + linesPerPage)

        self.maxWidth = 0
        metrics = QFontMetrics(self.font())
        for i in range(offsetY, maxY):
            width = metrics.width(self.lineItems[i].content)
            self.maxWidth = width if width > self.maxWidth else self.maxWidth

        if self.maxWidth > 0:
            hScrollBar.setRange(0, self.maxWidth - self.viewport().width())
            hScrollBar.setPageStep(self.viewport().width())

    def __onVScollBarValueChanged(self, value):
        hScrollBar = self.horizontalScrollBar()
        hScrollBar.blockSignals(True)
        self.__updateHScrollBar()
        hScrollBar.blockSignals(False)
