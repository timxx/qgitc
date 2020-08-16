# -*- coding: utf-8 -*-

from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PySide2.QtCore import *

from .common import *
from .gitutils import Git
from .findwidget import FindWidget
from .datafetcher import DataFetcher
from .textline import (
    createFormatRange,
    Link,
    TextLine,
    SourceTextLineBase,
    LinkTextLine)
from .colorschema import ColorSchema
from .sourceviewer import SourceViewer
from .textviewer import FindPart
from .events import OpenLinkEvent

import re


diff_re = re.compile(b"^diff --(git a/(.*) b/(.*)|cc (.*))")
diff_begin_re = re.compile(r"^@{2,}( (\+|\-)[0-9]+(,[0-9]+)?)+ @{2,}")
diff_begin_bre = re.compile(rb"^@{2,}( (\+|\-)[0-9]+(,[0-9]+)?)+ @{2,}")

submodule_re = re.compile(
    rb"^Submodule (.*) [a-z0-9]{7,}\.{2,3}[a-z0-9]{7,}.*$")

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


class DiffType:
    File = 0
    FileInfo = 1
    Diff = 2


class DiffFetcher(DataFetcher):

    diffAvailable = Signal(list, dict)

    def __init__(self, parent=None):
        super(DiffFetcher, self).__init__(parent)
        self._isDiffContent = False
        self._row = 0
        self._firstPatch = True

    def parse(self, data):
        lineItems = []
        fileItems = {}

        if data[-1] == ord(self.separator):
            data = data[:-1]

        lines = data.split(self.separator)
        for line in lines:
            match = diff_re.search(line)
            if match:
                if match.group(4):  # diff --cc
                    fileA = match.group(4)
                    fileB = None
                else:
                    fileA = match.group(2)
                    fileB = match.group(3)

                if not self._firstPatch:
                    lineItems.append((DiffType.Diff, b''))
                    self._row += 1
                self._firstPatch = False

                fileItems[fileA.decode(diff_encoding)] = self._row
                # renames, keep new file name only
                if fileB and fileB != fileA:
                    lineItems.append((DiffType.File, fileB))
                    fileItems[fileB.decode(diff_encoding)] = self._row
                else:
                    lineItems.append((DiffType.File, fileA))

                self._row += 1
                self._isDiffContent = False

                continue

            match = submodule_re.match(line)
            if match:
                if not self._firstPatch:
                    lineItems.append((DiffType.Diff, b''))
                    self._row += 1
                self._firstPatch = False

                submodule = match.group(1)
                lineItems.append((DiffType.File, submodule))
                fileItems[submodule.decode(diff_encoding)] = self._row
                self._row += 1

                lineItems.append((DiffType.FileInfo, line))
                self._row += 1

                self._isDiffContent = True
                continue

            if self._isDiffContent:
                itemType = DiffType.Diff
            elif diff_begin_bre.search(line):
                self._isDiffContent = True
                itemType = DiffType.Diff
            elif line.startswith(b"--- ") or line.startswith(b"+++ "):
                continue
            elif not line:  # ignore the empty info line
                continue
            else:
                itemType = DiffType.FileInfo

            if itemType != DiffType.Diff:
                line = line.rstrip(b'\r')
            lineItems.append((itemType, line))
            self._row += 1

        if lineItems:
            self.diffAvailable.emit(lineItems, fileItems)

    def resetRow(self, row):
        self._row = row
        self._isDiffContent = False
        self._firstPatch = True

    def cancel(self):
        self._isDiffContent = False
        super(DiffFetcher, self).cancel()

    def makeArgs(self, args):
        sha1 = args[0]
        filePath = args[1]
        gitArgs = args[2]

        if sha1 == Git.LCC_SHA1:
            git_args = ["diff-index", "--cached", "HEAD"]
        elif sha1 == Git.LUC_SHA1:
            git_args = ["diff-files"]
        else:
            git_args = ["diff-tree", "-r", "--root", sha1]

        git_args.extend(["-p", "--textconv", "--submodule",
                         "-C", "--cc", "--no-commit-id", "-U3"])

        if gitArgs:
            git_args.extend(gitArgs)

        if filePath:
            git_args.append("--")
            git_args.extend(filePath)

        return git_args


class DiffView(QWidget):
    requestCommit = Signal(str, bool, bool)
    requestBlame = Signal(str, bool)

    beginFetch = Signal()
    endFetch = Signal()

    def __init__(self, parent=None):
        super(DiffView, self).__init__(parent)

        self.viewer = PatchViewer(self)
        self.treeWidget = QTreeWidget(self)
        self.filterPath = None
        self.twMenu = QMenu()
        self.commit = None
        self.branchDir = None
        self.gitArgs = []
        self.fetcher = DiffFetcher(self)

        self.twMenu.addAction(self.tr("External &diff"),
                              self.__onExternalDiff)
        self.twMenu.addAction(self.tr("&Copy path"),
                              self.__onCopyPath)
        self.twMenu.addAction(self.tr("Copy &Windows path"),
                              self.__onCopyWinPath)
        self.twMenu.addSeparator()
        self.twMenu.addAction(self.tr("&Log this file"),
                              self.__onFilterPath)
        self.twMenu.addAction(self.tr("&Blame this file"),
                              self.__onBlameFile)
        self.twMenu.addAction(self.tr("Blame parent commit"),
                              self.__onBlameParentCommit)

        self.splitter = QSplitter(self)
        self.splitter.addWidget(self.viewer)
        self.splitter.addWidget(self.treeWidget)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        self.treeWidget.setColumnCount(1)
        self.treeWidget.setHeaderHidden(True)
        self.treeWidget.setRootIsDecorated(False)
        self.treeWidget.header().setStretchLastSection(False)
        self.treeWidget.header().setSectionResizeMode(QHeaderView.ResizeToContents)

        self.itemDelegate = TreeItemDelegate(self)
        self.treeWidget.setItemDelegate(self.itemDelegate)

        width = self.sizeHint().width()
        sizes = [width * 2 / 3, width * 1 / 3]
        self.splitter.setSizes(sizes)

        self.treeWidget.currentItemChanged.connect(self.__onTreeItemChanged)
        style = qApp.style()
        # single click to activate is so terrible
        if not style.styleHint(QStyle.SH_ItemView_ActivateItemOnSingleClick):
            self.treeWidget.itemActivated.connect(
                self.__onTreeItemDoubleClicked)
        else:
            self.treeWidget.itemDoubleClicked.connect(
                self.__onTreeItemDoubleClicked)

        self.viewer.fileRowChanged.connect(self.__onFileRowChanged)
        self.viewer.requestCommit.connect(self.requestCommit)
        self.viewer.requestBlame.connect(self.requestBlame)

        sett = qApp.instance().settings()
        sett.ignoreWhitespaceChanged.connect(
            self.__onIgnoreWhitespaceChanged)
        self.__onIgnoreWhitespaceChanged(sett.ignoreWhitespace())

        self.treeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treeWidget.customContextMenuRequested.connect(
            self.__onTreeWidgetContextMenuRequested)

        self.fetcher.diffAvailable.connect(
            self.__onDiffAvailable)
        self.fetcher.fetchFinished.connect(
            self.__onFetchFinished)

        self._difftoolProc = None

    def __onTreeItemChanged(self, current, previous):
        if current:
            row = current.data(0, Qt.UserRole)
            # do not fire the __onFileRowChanged
            self.viewer.blockSignals(True)
            self.viewer.gotoLine(row, False)
            self.viewer.blockSignals(False)

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
        self.__runDiffTool(item)

    def __doCopyPath(self, asWin=False):
        item = self.treeWidget.currentItem()
        if not item:
            return

        clipboard = QApplication.clipboard()
        if not asWin:
            clipboard.setText(item.text(0))
        else:
            clipboard.setText(item.text(0).replace('/', '\\'))

    def __onCopyPath(self):
        self.__doCopyPath()

    def __onCopyWinPath(self):
        self.__doCopyPath(True)

    def __onFilterPath(self):
        item = self.treeWidget.currentItem()
        if not item:
            return

        filePath = item.text(0)
        self.window().setFilterFile(filePath)

    def __onBlameFile(self):
        item = self.treeWidget.currentItem()
        if not item:
            return

        self.requestBlame.emit(item.text(0), False)

    def __onBlameParentCommit(self):
        item = self.treeWidget.currentItem()
        if not item:
            return

        self.requestBlame.emit(item.text(0), True)

    def __isCommentItem(self, item):
        # operator not implemented LoL
        # return item and item == self.treeWidget.topLevelItem(0):
        return item and item.data(0, Qt.UserRole) == 0

    def __runDiffTool(self, item):
        if not item or not self.commit:
            return

        filePath = item.text(0)
        tool = self.__diffToolForFile(filePath)

        cwd = self.branchDir if self.branchDir else Git.REPO_DIR
        args = ["difftool", "--no-prompt"]
        if self.commit.sha1 == Git.LUC_SHA1:
            pass
        elif self.commit.sha1 == Git.LCC_SHA1:
            args.append("--cached")
        else:
            args.append("{0}^..{0}".format(self.commit.sha1))

        if tool:
            args.append("--tool={}".format(tool))

        if filePath:
            args.append("--")
            args.append(filePath)

        if self._difftoolProc:
            QObject.disconnect(self._difftoolProc,
                               SIGNAL("finished(int, QProcess::ExitStatus)"),
                               self.__onDiffToolFinished)

        self._difftoolProc = QProcess(self)
        self._difftoolProc.setWorkingDirectory(cwd)
        # only care about the error
        self._difftoolProc.finished.connect(self.__onDiffToolFinished)

        self._difftoolProc.start("git", args)

    def __onDiffToolFinished(self, exitCode, exitStatus):
        if exitStatus == QProcess.CrashExit:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                self.tr("The external diff tool crashed!"))
        elif exitCode != 0:
            data = self._difftoolProc.readAllStandardError()
            if data:
                QMessageBox.critical(
                    self, self.window().windowTitle(),
                    data.data().decode("utf-8"))

        self._difftoolProc = None

    def __onTreeItemDoubleClicked(self, item, column):
        if not item or self.__isCommentItem(item):
            return

        self.__runDiffTool(item)

    def __onIgnoreWhitespaceChanged(self, index):
        args = ["", "--ignore-space-at-eol",
                "--ignore-space-change"]
        if index < 0 or index >= len(args):
            index = 0

        # TODO: remove args only
        self.gitArgs.clear()
        if index > 0:
            self.gitArgs.append(args[index])

        if self.commit:
            self.showCommit(self.commit)

    def __onTreeWidgetContextMenuRequested(self, pos):
        item = self.treeWidget.currentItem()
        if not item:
            return

        if self.treeWidget.topLevelItemCount() < 2:
            return

        if self.__isCommentItem(item):
            return

        self.twMenu.exec_(self.treeWidget.mapToGlobal(pos))

    def __onDiffAvailable(self, lineItems, fileItems):
        self.__addToTreeWidget(fileItems)
        self.viewer.appendLines(lineItems)

    def __onFetchFinished(self, exitCode):
        self.viewer.endReading()
        self.endFetch.emit()

        if exitCode != 0 and self.fetcher.errorData:
            QMessageBox.critical(self, self.window().windowTitle(),
                                 self.fetcher.errorData.decode("utf-8"))

    def __addToTreeWidget(self, *args):
        """specify the @row number of the file in the viewer"""
        if len(args) == 1 and isinstance(args[0], dict):
            items = []
            for file, row in args[0].items():
                item = QTreeWidgetItem([file])
                item.setData(0, Qt.UserRole, row)
                items.append(item)
            self.treeWidget.addTopLevelItems(items)
        else:
            item = QTreeWidgetItem([args[0]])
            item.setData(0, Qt.UserRole, args[1])
            self.treeWidget.addTopLevelItem(item)

    def __commitDesc(self, sha1):
        if sha1 == Git.LUC_SHA1:
            subject = self.tr("Local uncommitted changes, not checked in to index")
        elif sha1 == Git.LCC_SHA1:
            subject = self.tr("Local changes checked in to index but not committed")
        else:
            subject = Git.commitSubject(sha1).decode("utf-8")

        return " (" + subject + ")"

    def __commitToTextLines(self, commit):
        if not commit.sha1 in [Git.LUC_SHA1, Git.LCC_SHA1]:
            content = self.tr("Author: ") + commit.author + \
                                     " " + commit.authorDate
            self.viewer.addAuthorLine(content)

            content = self.tr("Committer: ") + commit.committer + \
                                     " " + commit.committerDate
            self.viewer.addAuthorLine(content)

        for parent in commit.parents:
            content = self.tr("Parent: ") + parent
            content += self.__commitDesc(parent)
            self.viewer.addSHA1Line(content, True)

        for child in commit.children:
            content = self.tr("Child: ") + child
            content += self.__commitDesc(child)
            self.viewer.addSHA1Line(content, False)

        self.viewer.addNormalTextLine("", False)

        comments = commit.comments.split('\n')
        for comment in comments:
            content = comment if not comment else "    " + comment
            self.viewer.addNormalTextLine(content)

        self.viewer.addNormalTextLine("", False)

    def __diffToolForFile(self, filePath):
        tools = qApp.settings().mergeToolList()
        # ignored case even on Unix platform
        lowercase_file = filePath.lower()
        for tool in tools:
            if tool.canDiff() and tool.isValid():
                if lowercase_file.endswith(tool.suffix.lower()):
                    return tool.command

        return qApp.settings().diffToolName()

    def showCommit(self, commit):
        self.clear()
        self.commit = commit

        self.__addToTreeWidget(self.tr("Comments"), 0)

        item = self.treeWidget.topLevelItem(0)
        self.treeWidget.setCurrentItem(item)

        self.__commitToTextLines(commit)

        self.viewer.setParentCount(len(commit.parents))
        self.viewer.beginReading()
        self.fetcher.resetRow(self.viewer.textLineCount())
        self.fetcher.fetch(commit.sha1, self.filterPath, self.gitArgs)
        # FIXME: delay showing the spinner when loading small diff to avoid flicker
        self.beginFetch.emit()

    def clear(self):
        self.treeWidget.clear()
        self.viewer.clear()

    def setFilterPath(self, path):
        # no need update
        self.filterPath = path

    def highlightKeyword(self, pattern, field=FindField.Comments):
        self.viewer.highlightKeyword(pattern, field)
        self.treeWidget.viewport().update()

    def saveState(self, settings, isBranchA):
        state = self.splitter.saveState()
        settings.setDiffViewState(state, isBranchA)

    def restoreState(self, settings, isBranchA):
        state = settings.diffViewState(isBranchA)
        if state:
            self.splitter.restoreState(state)

    def setBranchDir(self, branchDir):
        self.branchDir = branchDir
        self.fetcher.cwd = branchDir


class DiffTextLine(SourceTextLineBase):

    def __init__(self, viewer, text, parentCount):
        super().__init__(text, viewer._font, viewer._option)
        self._parentCount = parentCount

    def rehighlight(self):
        text = self.text()

        formats = self._commonHighlightFormats()
        tcFormat = QTextCharFormat()
        if not text:
            pass
        elif text[0] == "+":
            if len(text) >= 2 and text[1] == "+":
                tcFormat.setFontWeight(QFont.Bold)
            else:
                tcFormat.setForeground(ColorSchema.Adding)
        elif text[0] == "-":
            tcFormat.setForeground(ColorSchema.Deletion)
        elif text[0] == " " and len(text) >= 2:
            # TODO: only if in submodule changes
            if text.startswith("  > "):
                tcFormat.setForeground(ColorSchema.Submodule)
            elif text.startswith("  < "):
                tcFormat.setForeground(ColorSchema.Submodule2)
            elif self._parentCount > 1 and len(text) >= self._parentCount:
                index = self._parentCount - 1
                if text[index] == "+":
                    tcFormat.setFontWeight(QFont.Bold)
                    tcFormat.setForeground(ColorSchema.Adding)
                elif text[index] == "-":
                    tcFormat.setFontWeight(QFont.Bold)
                    tcFormat.setForeground(ColorSchema.Deletion)
        elif diff_begin_re.search(text) or text.startswith(r"\ No newline "):
            tcFormat.setForeground(ColorSchema.Newline)

        if tcFormat.isValid():
            formats.append(createFormatRange(0, len(text), tcFormat))

        if formats:
            self._layout.setAdditionalFormats(formats)


class InfoTextLine(TextLine):

    def __init__(self, viewer, type, text):
        super(InfoTextLine, self).__init__(
            text, viewer._font)
        self._type = type
        self.useBuiltinPatterns = False

    def _findLinks(self, patterns):
        # do nothing
        pass

    def isFileInfo(self):
        return self._type == DiffType.FileInfo

    def isFile(self):
        return self._type == DiffType.File

    def rehighlight(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold)
        fmtRg = createFormatRange(0, len(self.text()), fmt)

        formats = []
        formats.append(fmtRg)

        self._layout.setAdditionalFormats(formats)


class AuthorTextLine(LinkTextLine):

    def __init__(self, viewer, text):
        super().__init__(text, viewer._font, Link.Email)


class Sha1TextLine(LinkTextLine):

    def __init__(self, viewer, text, isParent):
        super().__init__(text, viewer._font, Link.Sha1)
        self._isParent = isParent

    def isParent(self):
        return self._isParent


class PatchViewer(SourceViewer):
    fileRowChanged = Signal(int)
    requestCommit = Signal(str, bool, bool)
    requestBlame = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.highlightPattern = None
        self.highlightField = FindField.Comments

        self.findWidget = None
        self.curIndexFound = False

        self._parentCount = 1

        self.verticalScrollBar().valueChanged.connect(
             self._onVScollBarValueChanged)
        self.linkActivated.connect(self._onLinkActivated)
        self.findResultAvailable.connect(self._onFindResultAvailable)

    def endReading(self):
        super().endReading()
        if self.findWidget and self.findWidget.isVisible():
            # redo a find
            self._onFind(self.findWidget.text)

    def toTextLine(self, item):
        type, content = item

        # alloc too many objects at the same time is too slow
        # so delay construct TextLine and decode bytes here
        if type == DiffType.Diff:
            text, _ = decodeFileData(content, diff_encoding)
            textLine = DiffTextLine(self, text, self._parentCount)
        elif type == DiffType.File or \
                type == DiffType.FileInfo:
            textLine = InfoTextLine(self, type, content.decode(diff_encoding))
        else:
            assert(False)

        return textLine

    def addAuthorLine(self, name):
        textLine = AuthorTextLine(self, name)
        self.appendTextLine(textLine)

    def addSHA1Line(self, content, isParent):
        textLine = Sha1TextLine(self, content, isParent)
        self.appendTextLine(textLine)

    def addNormalTextLine(self, text, useBuiltinPatterns=True):
        textLine = TextLine(text, self._font)
        textLine.useBuiltinPatterns = useBuiltinPatterns
        self.appendTextLine(textLine)

    def drawLineBackground(self, painter, textLine, lineRect):
        if isinstance(textLine, InfoTextLine):
            painter.fillRect(lineRect, ColorSchema.Info)

    def textLineFormatRange(self, textLine):
        formats = []

        if isinstance(textLine, DiffTextLine):
            fmt = self._createDiffFormats(textLine)
            if fmt:
                formats.extend(fmt)
        elif not isinstance(textLine, InfoTextLine):
            fmt = self._createCommentsFormats(textLine)
            if fmt:
                formats.extend(fmt)

        return formats

    def createContextMenu(self):
        menu = super().createContextMenu()
        menu.addSeparator()

        self._acOpenCommit = menu.addAction(
            self.tr("&Open commit in browser"), self._onOpenCommit)

        return menu

    def updateContextMenu(self, pos):
        enabled = False
        if self._link is not None:
            enabled = self._link.type == Link.Sha1

        self._acOpenCommit.setEnabled(enabled)

    def updateLinkData(self, link, lineNo):
        if link.type == Link.Sha1:
            textLine = self.textLineAt(lineNo)
            if isinstance(textLine, Sha1TextLine):
                if not isinstance(link.data, tuple):
                    link.data = (link.data, textLine.isParent())

    def highlightKeyword(self, pattern, field):
        self.highlightPattern = pattern
        self.highlightField = field
        self.viewport().update()

    def hasSelection(self):
        return self._cursor.hasSelection()

    def executeFind(self):
        if not self.findWidget:
            self.findWidget = FindWidget(self.viewport(), self)
            self.findWidget.find.connect(self._onFind)
            self.findWidget.cursorChanged.connect(
                self._onFindCursorChanged)
            self.findWidget.afterHidden.connect(
                self._onFindHidden)
            self.findFinished.connect(
                self.findWidget.findFinished)

        text = self.selectedText
        if text:
            # first line only
            text = text.lstrip('\n')
            index = text.find('\n')
            if index != -1:
                text = text[:index]
            self.findWidget.setText(text)
        self.findWidget.showAnimate()

    def setParentCount(self, n):
        self._parentCount = n

    def _highlightFormatRange(self, text):
        formats = []
        if self.highlightPattern:
            matchs = self.highlightPattern.finditer(text)
            fmt = QTextCharFormat()
            fmt.setBackground(QBrush(Qt.yellow))
            for m in matchs:
                rg = createFormatRange(m.start(), m.end() - m.start(), fmt)
                formats.append(rg)
        return formats

    def _createCommentsFormats(self, textLine):
        if self.highlightField == FindField.Comments or \
                self.highlightField == FindField.All:
            return self._highlightFormatRange(textLine.text())

        return None

    def _createDiffFormats(self, textLine):
        if self.highlightField == FindField.All:
            return self._highlightFormatRange(textLine.text())
        elif FindField.isDiff(self.highlightField):
            text = textLine.text().lstrip()
            if text.startswith('+') or text.startswith('-'):
                return self._highlightFormatRange(textLine.text())

        return None

    def _onVScollBarValueChanged(self, value):
        if not self.hasTextLines():
            return

        # TODO: improve
        for i in range(value, -1, -1):
            textLine = self.textLineAt(i)
            if isinstance(textLine, InfoTextLine) and textLine.isFile():
                self.fileRowChanged.emit(i)
                break
            elif isinstance(textLine, AuthorTextLine) or \
                    (isinstance(textLine, Sha1TextLine) and textLine.isParent()):
                self.fileRowChanged.emit(0)
                break

    def _onOpenCommit(self):
        sett = qApp.settings()
        repoName = qApp.repoName()
        url = sett.commitUrl(repoName)
        if not url and sett.fallbackGlobalLinks(repoName):
            url = sett.commitUrl(None)
        if not url:
            return

        if isinstance(self._link.data, tuple):
            url += self._link.data[0]
        else:
            url += self._link.data
        QDesktopServices.openUrl(QUrl(url))

    def _onFind(self, text):
        self.findWidget.updateFindResult([])
        self.highlightFindResult([])

        if self.textLineCount() > 3000:
            self.curIndexFound = False
            if self.findAllAsync(text):
                self.findWidget.findStarted()
        else:
            findResult = self.findAll(text)
            if findResult:
                self._onFindResultAvailable(findResult, FindPart.All)

    def _onFindCursorChanged(self, cursor):
        self.select(cursor)

    def _onFindHidden(self):
        self.highlightFindResult([])
        self.cancelFind()

    def _onLinkActivated(self, link):
        if link.type == Link.Sha1:
            data = link.data
            isNear = isinstance(data, tuple)
            goNext = False
            if isNear:
                goNext = data[1]
                data = data[0]
            self.requestCommit.emit(data, isNear, goNext)
        else:
            qApp.postEvent(qApp, OpenLinkEvent(link))

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

        self.findWidget.updateFindResult(result, curFindIndex, findPart)
