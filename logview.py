# --*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from common import *

import re


class CommitFetcher():

    def __init__(self):
        self.items = []
        self.source = None
        self.loadedCount = 0

    def __len__(self):
        return self.count()

    def __getitem__(self, index):
        return self.data(index)

    def __ensureCommit(self, index):
        if not self.source or self.items[index]:
            return

        commit = Commit()
        commit.parseRawString(self.source[index])
        self.items[index] = commit
        self.loadedCount += 1

        # no need the source
        if self.loadedCount == len(self.source):
            self.source = None

    def count(self):
        return len(self.items)

    def data(self, index):
        if index < 0 or index >= self.count():
            return None

        self.__ensureCommit(index)
        return self.items[index]

    def setSource(self, source):
        self.source = source
        self.items.clear()
        self.loadedCount = 0
        if source:
            self.items = [None for i in range(len(source))]

    def findCommitIndex(self, sha1):
        index = -1

        for i in range(len(self.items)):
            self.__ensureCommit(i)
            item = self.items[i]
            if item.sha1.startswith(sha1):
                index = i
                break

        return index


class LogView(QAbstractScrollArea):
    currentIndexChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super(LogView, self).__init__(parent)

        self.setFocusPolicy(Qt.StrongFocus)

        self.data = CommitFetcher()
        self.curIdx = -1
        self.branchA = True

        self.lineSpace = 5
        self.marginX = 3
        self.marginY = 3

        self.color = "#FF0000"
        self.sha1Url = None
        self.bugUrl = None
        self.bugRe = None

        self.menu = QMenu()
        self.menu.addAction(self.tr("&Copy commit summary"),
                            self.__onCopyCommitSummary)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)

        # never show the horizontalScrollBar
        # since we can view the long content in diff view
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.updateSettings()

    def setBranchB(self):
        self.branchA = False
        settings = QApplication.instance().settings()
        self.setColor(settings.commitColorB().name())

    def setColor(self, color):
        self.color = color

    def setSha1Url(self, url):
        self.sha1Url = url

    def setBugUrl(self, url):
        self.bugUrl = url

    def setBugPattern(self, pattern):
        self.bugRe = re.compile(pattern)

    def setLogs(self, commits):
        self.data.setSource(commits)
        if self.data:
            self.setCurrentIndex(0)

        self.updateGeometries()
        self.viewport().update()

    def clear(self):
        self.data.setSource(None)
        self.curIdx = -1
        self.viewport().update()
        self.currentIndexChanged.emit(self.curIdx)

    def getCommit(self, index):
        return self.data[index]

    def currentIndex(self):
        return self.curIdx

    def ensureVisible(self):
        if self.curIdx == -1:
            return

        startLine = self.verticalScrollBar().value()
        endLine = startLine + self.__linesPerPage()

        if self.curIdx < startLine or self.curIdx > endLine:
            self.verticalScrollBar().setValue(self.curIdx)

    def setCurrentIndex(self, index):
        if index >= 0 and index < len(self.data):
            self.curIdx = index
            self.ensureVisible()
            self.viewport().update()
            self.currentIndexChanged.emit(index)

    def switchToCommit(self, sha1):
        # ignore if sha1 same as current's
        if self.curIdx != -1 and self.curIdx < len(self.data):
            commit = self.data[self.curIdx]
            if commit and commit.sha1.startswith(sha1):
                self.ensureVisible()
                return True

        index = self.data.findCommitIndex(sha1)
        if index != -1:
            self.setCurrentIndex(index)

        return index != -1

    def showContextMenu(self, pos):
        if self.curIdx != -1:
            globalPos = self.mapToGlobal(pos)
            self.menu.exec(globalPos)

    def updateSettings(self):
        settings = QApplication.instance().settings()
        self.font = settings.logViewFont()

        self.lineHeight = QFontMetrics(self.font).height() + self.lineSpace

        if self.branchA:
            self.setColor(settings.commitColorA().name())
        else:
            self.setColor(settings.commitColorB().name())
        self.setSha1Url(settings.commitUrl())
        self.setBugUrl(settings.bugUrl())
        self.setBugPattern(settings.bugPattern())

        self.updateGeometries()

    def __onCopyCommitSummary(self):
        if self.curIdx == -1:
            return
        commit = self.data[self.curIdx]
        if not commit:
            return

        commit = getCommitSummary(commit.sha1)

        clipboard = QApplication.clipboard()

        htmlText = '<html>\n'
        htmlText += '<head>\n'
        htmlText += '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>\n'
        htmlText += '</head>\n'
        htmlText += '<body>\n'
        htmlText += '<div>\n'
        htmlText += '<p style="margin:0pt">\n'
        htmlText += '<span style="font-size:10pt;color:{0}">'.format(
            self.color)
        htmlText += self.__sha1Url(commit["sha1"])
        htmlText += ' (&quot;'
        htmlText += self.__filterBug(commit["subject"])
        htmlText += '&quot;, ' + \
            self.__mailTo(commit["author"], commit["email"])
        htmlText += ', ' + commit["date"]
        htmlText += ')</span>'
        htmlText += '</p>\n'
        htmlText += '</div>\n'
        htmlText += '</body>\n'
        htmlText += '</html>\n'

        mimeData = QMimeData()
        mimeData.setHtml(htmlText)
        mimeData.setText('{0} ("{1}"), {2}, {3}'.format(
            commit["sha1"],
            commit["subject"],
            commit["author"],
            commit["date"]))

        clipboard.setMimeData(mimeData)

    def __sha1Url(self, sha1):
        if not self.sha1Url:
            return sha1

        return '<a href="{0}{1}">{1}</a>'.format(self.sha1Url, sha1)

    def __filterBug(self, subject):
        text = htmlEscape(subject)
        if not self.bugUrl or not self.bugRe:
            return text

        return self.bugRe.sub('<a href="{0}\\1">\\1</a>'.format(self.bugUrl), text)

    def __mailTo(self, author, email):
        return '<a href="mailto:{0}">{1}</a>'.format(email, htmlEscape(author))

    def __linesPerPage(self):
        h = self.viewport().height() - self.marginY
        return int(h / self.lineHeight)

    def __itemRect(self, index):
        """@index the index of data"""

        # the row number in viewport
        row = (index - self.verticalScrollBar().value())

        offsetX = self.horizontalScrollBar().value()
        x = self.marginX - offsetX
        y = self.marginY + row * self.lineHeight
        w = self.viewport().width() - x - self.marginX
        h = self.lineHeight

        rect = QRect(x, y, w, h)

        return rect

    def invalidateItem(self, index):
        rect = self.__itemRect(index)
        # update if visible in the viewport
        if rect.y() >= 0:
            self.viewport().update(rect)

    def updateGeometries(self):
        hScrollBar = self.horizontalScrollBar()
        vScrollBar = self.verticalScrollBar()

        if not self.data:
            hScrollBar.setRange(0, 0)
            vScrollBar.setRange(0, 0)
            return

        linesPerPage = self.__linesPerPage()
        totalLines = len(self.data)

        vScrollBar.setRange(0, totalLines - linesPerPage)
        vScrollBar.setPageStep(linesPerPage)

    def resizeEvent(self, event):
        super(LogView, self).resizeEvent(event)

        self.updateGeometries()

    def paintEvent(self, event):
        if not self.data:
            return

        painter = QPainter(self.viewport())

        startLine = self.verticalScrollBar().value()
        endLine = startLine + self.__linesPerPage() + 1
        endLine = min(len(self.data), endLine)

        palette = self.palette()

        for i in range(startLine, endLine):
            commit = self.data[i]
            content = commit.comments.split('\n')[0]

            rect = self.__itemRect(i)

            if i == self.curIdx:
                painter.fillRect(rect, palette.highlight())
                if self.hasFocus():
                    painter.setPen(QPen(Qt.DotLine))
                    painter.drawRect(rect.adjusted(0, 0, -1, -1))
                painter.setPen(palette.color(QPalette.HighlightedText))
            else:
                painter.setPen(palette.color(QPalette.WindowText))

            painter.setFont(self.font)
            # don't know why style.drawControl not works :(
            painter.drawText(rect.adjusted(2, 0, 0, 0),
                             Qt.AlignLeft | Qt.AlignVCenter, content)

    def mousePressEvent(self, event):
        if not self.data:
            return

        y = event.pos().y()
        index = int(y / self.lineHeight)
        index += self.verticalScrollBar().value()

        if index < len(self.data):
            self.setCurrentIndex(index)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            if self.curIdx > 0:
                startLine = self.verticalScrollBar().value()
                self.curIdx -= 1
                if self.curIdx >= startLine:
                    self.invalidateItem(self.curIdx + 1)
                    self.invalidateItem(self.curIdx)
                else:
                    self.verticalScrollBar().setValue(self.curIdx)

                self.currentIndexChanged.emit(self.curIdx)
        elif event.key() == Qt.Key_Down:
            if self.curIdx + 1 < len(self.data):
                endLine = self.verticalScrollBar().value() + self.__linesPerPage()
                self.curIdx += 1
                if self.curIdx < endLine:
                    self.invalidateItem(self.curIdx - 1)
                    self.invalidateItem(self.curIdx)
                else:
                    v = self.verticalScrollBar().value()
                    self.verticalScrollBar().setValue(v + 1)

                self.currentIndexChanged.emit(self.curIdx)

    def focusInEvent(self, event):
        self.invalidateItem(self.curIdx)

    def focusOutEvent(self, event):
        self.invalidateItem(self.curIdx)
