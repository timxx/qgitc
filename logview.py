# --*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *

from common import *
from git import *

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

    def findCommitIndex(self, sha1, begin=0, findNext=True):
        index = -1

        findRange = range(begin, len(self.items)) \
            if findNext else range(begin, -1, -1)
        for i in findRange:
            self.__ensureCommit(i)
            item = self.items[i]
            if item.sha1.startswith(sha1):
                index = i
                break

        return index


class FindThread(QThread):
    findFinished = pyqtSignal(int)
    findProgress = pyqtSignal(int)

    def __init__(self, parent=None):
        super(FindThread, self).__init__(parent)

        self.mutex = QMutex()

        pattern = b'diff --(git a/.* b/.*|cc .*)\n'
        pattern += b'|index [a-z0-9]{7,}..[a-z0-9]{7,}( [0-7]{6})?\n'
        pattern += b'|@{2,}( (\+|\-)[0-9]+,[0-9]+)+ @{2,}'
        pattern += b'|\-\-\- (a/.*|/dev/null)\n'
        pattern += b'|\+\+\+ (b/.*|/dev/null)\n'
        pattern += b'|(new|deleted) file mode [0-7]{6}\n'
        pattern += b'|Binary files.* and .* differ\n'
        pattern += b'|\\ No newline at end of file'
        self.diffRe = re.compile(pattern)

        self.initData(None, None, None, 0)

    def __findCommitInHeader(self, commit):
        if self.regexp.search(commit.comments):
            return True

        if self.regexp.search(commit.author):
            return True

        if self.regexp.search(commit.commiter):
            return True

        if self.regexp.search(commit.sha1):
            return True

        if self.regexp.search(commit.authorDate):
            return True

        if self.regexp.search(commit.commiterDate):
            return True

        for p in commit.parents:
            if self.regexp.search(p):
                return True

        return False

    def __findCommitInPath(self, commit):
        paths = Git.commitFiles(commit.sha1)
        if self.regexp.search(paths):
            return True
        return False

    def __findCommitInDiff(self, commit):
        # TODO: improve performance
        diff = Git.commitRawDiff(commit.sha1)
        # remove useless lines
        diff = self.diffRe.sub(b'', diff)

        # different file might have different encoding
        # so split the diff data into lines
        lastEncoding = None
        lines = diff.split(b'\n')
        for line in lines:
            line, lastEncoding = decodeDiffData(line, lastEncoding)
            if line and self.regexp.search(line):
                return True
        return False

    def __isInterruptionRequested(self):
        interruptionReguested = False
        self.mutex.lock()
        interruptionReguested = self.interruptionReguested
        self.mutex.unlock()
        return interruptionReguested

    def initData(self, commits, findPattern, findRange, findField):
        self.commits = commits
        self.regexp = findPattern
        self.findRange = findRange
        self.findField = findField
        self.interruptionReguested = False

    def requestInterruption(self):
        if not self.isRunning():
            return
        self.mutex.lock()
        self.interruptionReguested = True
        self.mutex.unlock()

    def isInterruptionRequested(self):
        if not self.isRunning():
            return False
        return self.__isInterruptionRequested()

    def run(self):
        findInCommit = self.__findCommitInDiff
        if self.findField == FindField.Comments:
            findInCommit = self.__findCommitInHeader
        elif self.findField == FindField.Paths:
            findInCommit = self.__findCommitInPath

        result = -1
        total = abs(self.findRange.stop - self.findRange.start)
        progress = 0
        percentage = -1
        # profile = MyProfile()
        for i in self.findRange:
            if self.__isInterruptionRequested():
                result = -2
                break

            progress += 1
            new_percentage = int(progress * 100 / total)
            # avoid too many updates on main thread
            if percentage != new_percentage:
                percentage = new_percentage
                self.findProgress.emit(percentage)

            if findInCommit(self.commits[i]):
                result = i
                break

        # profile = None
        self.findFinished.emit(result)


class Marker():
    CHAR_MARK = chr(0x2713)

    def __init__(self):
        self._begin = -1
        self._end = -1

    def mark(self, begin, end):
        self._begin = min(begin, end)
        self._end = max(begin, end)

    def clear(self):
        self._begin = -1
        self._end = -1

    def hasMark(self):
        return self._begin != -1 and \
            self._end != -1

    def begin(self):
        return self._begin

    def end(self):
        return self._end

    def isMarked(self, index):
        return self.hasMark() and \
            self._begin <= index and \
            self._end >= index

    def draw(self, index, painter, rect):
        if not self.isMarked(index):
            return

        painter.save()

        painter.setPen(Qt.red)
        br = painter.drawText(rect, Qt.AlignVCenter, Marker.CHAR_MARK)
        rect.adjust(br.width(), 0, 0, 0)

        painter.restore()


class LogView(QAbstractScrollArea):
    currentIndexChanged = pyqtSignal(int)
    findFinished = pyqtSignal(int)
    findProgress = pyqtSignal(int)

    # for refs
    TAG_COLORS = [Qt.yellow,
                  QColor(0, 0x7F, 0),
                  QColor(255, 221, 170)]

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

        self.authorRe = re.compile("(.*) <.*>$")

        self.findThread = FindThread(self)
        self.findThread.findFinished.connect(self.findFinished)
        self.findThread.findProgress.connect(self.findProgress)

        self.highlightPattern = None
        self.marker = Marker()

        self.menu = QMenu()
        self.menu.addAction(self.tr("&Copy commit summary"),
                            self.__onCopyCommitSummary)
        self.menu.addSeparator()

        self.menu.addAction(self.tr("&Mark this commit"),
                            self.__onMarkCommit)
        self.acMarkTo = self.menu.addAction(self.tr("Mark &to this commit"),
                                            self.__onMarkToCommit)
        self.acClearMarks = self.menu.addAction(self.tr("Clea&r Marks"),
                                                self.__onClearMarks)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)

        # never show the horizontalScrollBar
        # since we can view the long content in diff view
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.updateSettings()

    def __del__(self):
        self.cancelFindCommit()

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
        self.marker.clear()
        self.viewport().update()
        self.currentIndexChanged.emit(self.curIdx)
        self.cancelFindCommit()

    def getCommit(self, index):
        return self.data[index]

    def getCount(self):
        return len(self.data)

    def currentIndex(self):
        return self.curIdx

    def ensureVisible(self):
        if self.curIdx == -1:
            return

        startLine = self.verticalScrollBar().value()
        endLine = startLine + self.__linesPerPage()

        if self.curIdx < startLine or self.curIdx >= endLine:
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

    def switchToNearCommit(self, sha1, goNext=True):
        curIdx = self.curIdx if self.curIdx >= 0 else 0
        index = self.data.findCommitIndex(sha1, self.curIdx, goNext)
        if index != -1:
            self.setCurrentIndex(index)
        return index != -1

    def showContextMenu(self, pos):
        if self.curIdx == -1:
            return

        hasMark = self.marker.hasMark()
        self.acMarkTo.setVisible(hasMark)
        self.acClearMarks.setVisible(hasMark)

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

        commit = Git.commitSummary(commit.sha1)

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

    def __onMarkCommit(self):
        assert self.curIdx >= 0

        begin = self.curIdx
        end = self.curIdx
        self.marker.mark(begin, end)
        # TODO: update marked lines only
        self.viewport().update()

    def __onMarkToCommit(self):
        assert self.curIdx >= 0

        begin = self.marker.begin()
        end = self.curIdx
        self.marker.mark(begin, end)
        # TODO: update marked lines only
        self.viewport().update()

    def __onClearMarks(self):
        self.marker.clear()
        # TODO: update marked lines only
        self.viewport().update()

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

    def __drawTag(self, painter, rect, color, text, bold=False):
        painter.save()

        if bold:
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)

        flags = Qt.AlignLeft | Qt.AlignVCenter
        br = painter.boundingRect(rect, flags, text)
        br.adjust(0, -1, 4, 1)

        painter.fillRect(br, color)
        painter.setPen(Qt.black)
        painter.drawRect(br)

        painter.drawText(br, Qt.AlignCenter, text)

        painter.restore()
        rect.adjust(br.width(), 0, 0, 0)

    def __drawTriangleTag(self, painter, rect, color, text):
        painter.save()

        flags = Qt.AlignLeft | Qt.AlignVCenter
        br = painter.boundingRect(rect, flags, text)
        br.adjust(0, -1, 4, 1)

        h = br.height()
        w = int(h / 2)

        path = QPainterPath()
        path.moveTo(QPoint(br.x(), br.y() + int(h / 2)))

        # move rect to right
        br.adjust(w, 0, w, 0)

        path.lineTo(br.topLeft())
        path.lineTo(br.topRight())
        path.lineTo(br.bottomRight())
        path.lineTo(br.bottomLeft())
        path.closeSubpath()

        painter.setPen(Qt.black)
        painter.fillPath(path, color)
        painter.drawPath(path)

        painter.drawText(br, Qt.AlignCenter, text)

        painter.restore()
        rect.adjust(path.boundingRect().width(), 0, 0, 0)

    def __drawGraph(self, painter, rect, commit):
        w = int(rect.height() * 3 / 4)
        x1 = 0
        x2 = x1 + w

        h = int(rect.height() / 2)
        m = int((x1 + x2) / 2)
        r = int((x2 - x1) * 1 / 3)
        d = int(2 * r)

        # points
        # TL(m-r, h-r), TR(m+r, h-r)
        ###########
        #         #
        #    #    #  center (m, h)
        #         #
        ###########
        # BL(m, h+r), BR(m+r, h+r)

        painter.save()

        painter.translate(rect.topLeft())
        rc = QRect(rect)
        rc.moveTo(QPoint(0, 0))

        # TODO: implement graph drawing

        # vertical line
        painter.setPen(QPen(Qt.black, 2))
        if not commit.parents:
            painter.drawLine(m, 0, m, h)
        else:
            painter.drawLine(m, 0, m, 2 * h)

        # only antialiasing for rounding
        painter.save()
        painter.setRenderHints(QPainter.Antialiasing)
        painter.setPen(Qt.black)
        painter.setBrush(Qt.blue)
        painter.drawEllipse(m - r, h - r, d, d)
        painter.restore()

        # the real rect width
        graphW = m + r
        rc.adjust(graphW, 0, 0, 0)

        # refs
        if commit.sha1 in Git.REF_MAP:
            refs = Git.REF_MAP[commit.sha1]
            x = m + r
            cW = d  # line width
            for ref in refs:
                # connector
                painter.setPen(QPen(Qt.black, 2))
                painter.drawLine(x, h, x + cW, h)
                rc.adjust(cW, 0, 0, 0)

                # tag
                painter.setPen(QPen(Qt.black))
                color = LogView.TAG_COLORS[ref.type]

                preL = rc.left()
                if ref.type == Ref.TAG:
                    self.__drawTriangleTag(painter, rc, color, ref.name)
                else:
                    bold = (ref.type == Ref.HEAD and commit.sha1 == Git.REV_HEAD)
                    self.__drawTag(painter, rc, color, ref.name, bold)
                x += (rc.left() - preL) + cW + 1

            graphW += x - (m + r)

        painter.restore()
        rect.adjust(graphW + r, 0, 0, 0)

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

    def findCommitAsync(self, findPattern, findRange, findField):
        # cancel the previous one
        self.cancelFindCommit()

        if not findPattern:
            return False

        self.findThread.initData(
            self.data, findPattern, findRange, findField)
        self.findThread.start()

        return True

    def cancelFindCommit(self):
        if self.findThread.isRunning():
            self.findThread.requestInterruption()
            self.findThread.wait()
            return True
        return False

    def highlightKeyword(self, pattern):
        self.highlightPattern = pattern
        self.viewport().update()

    def resizeEvent(self, event):
        super(LogView, self).resizeEvent(event)

        self.updateGeometries()

    def paintEvent(self, event):
        if not self.data:
            return

        painter = QPainter(self.viewport())
        painter.setClipRect(event.rect())

        startLine = self.verticalScrollBar().value()
        endLine = startLine + self.__linesPerPage() + 1
        endLine = min(len(self.data), endLine)

        palette = self.palette()

        for i in range(startLine, endLine):
            commit = self.data[i]
            content = commit.comments.split('\n')[0]

            rect = self.__itemRect(i)

            painter.setFont(self.font)

            rect.adjust(2, 0, 0, 0)

            self.__drawGraph(painter, rect, commit)

            # author
            text = self.authorRe.sub("\\1", commit.author)
            color = Qt.gray
            self.__drawTag(painter, rect, color, text)

            # date
            text = commit.authorDate.split(' ')[0]
            color = QColor(140, 208, 80)
            self.__drawTag(painter, rect, color, text)
            rect.adjust(4, 0, 0, 0)

            # marker
            self.marker.draw(i, painter, rect)

            # subject
            painter.save()
            if i == self.curIdx:
                painter.fillRect(rect, palette.highlight())
                if self.hasFocus():
                    painter.setPen(QPen(Qt.DotLine))
                    painter.drawRect(rect.adjusted(0, 0, -1, -1))
                painter.setPen(palette.color(QPalette.HighlightedText))
            else:
                painter.setPen(palette.color(QPalette.WindowText))

            textLayout = QTextLayout(content, self.font)

            textOption = QTextOption()
            textOption.setWrapMode(QTextOption.NoWrap)
            textOption.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            textLayout.setTextOption(textOption)

            formats = []
            if self.highlightPattern:
                matchs = self.highlightPattern.finditer(content)
                fmt = QTextCharFormat()
                if i == self.curIdx:
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

            # setAlignment doesn't works at all!
            # we have to vcenter by self LoL
            rect.adjust(2, 0, 0, 0)
            offsetY = (rect.height() - painter.fontMetrics().lineSpacing()) / 2
            pos = QPointF(rect.left(), rect.top() + offsetY)
            textLayout.draw(painter, pos)

            painter.restore()

    def mousePressEvent(self, event):
        if not self.data:
            return

        y = event.pos().y()
        index = int(y / self.lineHeight)
        index += self.verticalScrollBar().value()

        if index >= len(self.data):
            return

        mod = qApp.keyboardModifiers()
        # no OR combination
        if mod == Qt.ShiftModifier:
            self.marker.mark(self.curIdx, index)
            self.viewport().update()
        else:
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

        super(LogView, self).keyPressEvent(event)

    def focusInEvent(self, event):
        self.invalidateItem(self.curIdx)

    def focusOutEvent(self, event):
        self.invalidateItem(self.curIdx)
