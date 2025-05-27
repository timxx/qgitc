# -*- coding: utf-8 -*-

from PySide6.QtCore import (
    SIGNAL,
    QAbstractListModel,
    QEvent,
    QFileInfo,
    QModelIndex,
    QObject,
    QProcess,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QDesktopServices,
    QFont,
    QFontMetricsF,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QSplitter,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.commitsource import CommitSource
from qgitc.common import *
from qgitc.difffetcher import DiffFetcher
from qgitc.diffutils import FileInfo
from qgitc.gitutils import Git, GitProcess
from qgitc.patchviewer import PatchViewer


def _makeTextIcon(text, textColor, font: QFont):
    img = QPixmap(QSize(16, 16))
    img.fill(Qt.transparent)

    painter = QPainter(img)
    painter.setPen(textColor)
    painter.setFont(font)
    painter.drawText(img.rect(), Qt.AlignCenter, text)
    painter = None

    return QIcon(img)


class FileListModel(QAbstractListModel):

    RowRole = Qt.UserRole

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fileList: List[(str, FileInfo)] = []

        font: QFont = ApplicationBase.instance().font()
        font.setBold(True)
        self._icons = [
            None,  # normal
            _makeTextIcon(
                "A", ApplicationBase.instance().colorSchema().Adding, font),
            _makeTextIcon(
                "M", ApplicationBase.instance().colorSchema().Modified, font),
            _makeTextIcon(
                "D", ApplicationBase.instance().colorSchema().Deletion, font),
            _makeTextIcon(
                "R", ApplicationBase.instance().colorSchema().Renamed, font),
            _makeTextIcon("R", ApplicationBase.instance(
            ).colorSchema().RenamedModified, font),
        ]

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0

        return len(self._fileList)

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def insertRows(self, row, count, parent=QModelIndex()):
        if row < 0 or count < 1 or row > self.rowCount(parent):
            return False

        self.beginInsertRows(QModelIndex(), row, row + count - 1)
        for i in range(count):
            self._fileList.insert(row, "")
        self.endInsertRows()

        return True

    def removeRows(self, row, count, parent=QModelIndex()):
        if row < 0 or (row + count) > self.rowCount(parent) or count < 1:
            return False

        self.beginRemoveRows(QModelIndex(), row, row + count - 1)
        del self._fileList[row: row + count]
        self.endRemoveRows()

        return True

    def data(self, index, role=Qt.DisplayRole):
        row = index.row()
        if row < 0 or row >= self.rowCount():
            return False

        if role == Qt.DisplayRole:
            return self._fileList[row][0]
        elif role == FileListModel.RowRole:
            return self._fileList[row][1].row
        elif role == Qt.DecorationRole:
            return self._icons[self._fileList[row][1].state]

        return None

    def setData(self, index, value, role=Qt.EditRole):
        row = index.row()
        if row < 0 or row >= self.rowCount():
            return False

        old_value = self._fileList[row]
        if role == Qt.DisplayRole:
            self._fileList[row] = (value, old_value[1])
            return True
        elif role == FileListModel.RowRole:
            self._fileList[row] = (old_value[0], value)
            return True

        return False

    def addFile(self, file, info: FileInfo):
        rowCount = self.rowCount()
        self.beginInsertRows(QModelIndex(), rowCount, rowCount)
        self._fileList.append((file, info))
        self.endInsertRows()

    def clear(self):
        self.removeRows(0, self.rowCount())


class DiffView(QWidget):
    requestCommit = Signal(str, bool, bool)
    requestBlame = Signal(str, bool, Commit)

    beginFetch = Signal()
    endFetch = Signal()

    localChangeRestored = Signal()

    def __init__(self, parent=None):
        super(DiffView, self).__init__(parent)

        self.viewer = PatchViewer(self)
        self.fileListView = QListView(self)
        self.filterPath = None
        self.twMenu = QMenu()
        self.commit = None
        self.branchDir = None
        self.gitArgs = []
        self.fetcher = DiffFetcher(self)
        # sub commit to fetch
        self._commitList: List[Commit] = []

        self._commitSource: CommitSource = None

        self.twMenu.addAction(self.tr("External &diff"),
                              self.__onExternalDiff)
        self.twMenu.addSeparator()

        copyMenu = self.twMenu.addMenu(self.tr("&Copy path"))
        copyMenu.addAction(self.tr("As &seen"),
                           self.__onCopyPath)
        copyMenu.addAction(self.tr("As &absolute"),
                           self.__onCopyAbsPath)
        copyMenu.addAction(self.tr("As &Windows"),
                           self.__onCopyWinPath)
        # useless on non-Windows platform
        if os.name == "nt":
            copyMenu.addAction(self.tr("As W&indows absolute"),
                               self.__onCopyWinAbsPath)
        self.twMenu.addSeparator()

        self.twMenu.addAction(
            self.tr("&Open Containing Folder"),
            self.__onOpenContainingFolder)

        self.twMenu.addSeparator()
        self.twMenu.addAction(self.tr("&Log this file"),
                              self.__onFilterPath)
        self.twMenu.addAction(self.tr("&Blame this file"),
                              self.__onBlameFile)
        self.twMenu.addAction(self.tr("Blame parent commit"),
                              self.__onBlameParentCommit)

        self.twMenu.addSeparator()
        self.acRestoreFiles = self.twMenu.addAction(
            self.tr("&Restore this file"),
            self.__onRestoreFiles)

        self.splitter = QSplitter(self)
        self.splitter.addWidget(self.viewer)

        self.fileListView.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.fileListModel = FileListModel(self)
        self.fileListProxy = QSortFilterProxyModel(self)
        self.fileListProxy.setSourceModel(self.fileListModel)
        self.fileListView.setModel(self.fileListProxy)

        fileListFilter = QLineEdit(self)
        fileListFilter.textChanged.connect(
            self._onFileListFilterChanged)

        listViewWrapper = QWidget(self)
        vbox = QVBoxLayout(listViewWrapper)
        vbox.setContentsMargins(0, 0, 0, 0)

        self.filterStatus = QLabel("0", self)
        hbox = QHBoxLayout()
        hbox.addWidget(fileListFilter)
        hbox.addWidget(self.filterStatus)
        vbox.addLayout(hbox)
        vbox.addWidget(self.fileListView)

        self.splitter.addWidget(listViewWrapper)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        width = self.sizeHint().width()
        sizes = [width * 2 / 3, width * 1 / 3]
        self.splitter.setSizes(sizes)

        self.fileListView.selectionModel().currentRowChanged.connect(
            self.__onFileListViewCurrentRowChanged)
        style = ApplicationBase.instance().style()
        # single click to activate is so terrible
        if not style.styleHint(QStyle.SH_ItemView_ActivateItemOnSingleClick):
            self.fileListView.activated.connect(
                self.__onFileListViewDoubleClicked)
        else:
            self.fileListView.doubleClicked.connect(
                self.__onFileListViewDoubleClicked)

        self.viewer.fileRowChanged.connect(self.__onFileRowChanged)
        self.viewer.requestCommit.connect(self.requestCommit)
        self.viewer.requestBlame.connect(self.requestBlame)

        sett = ApplicationBase.instance().settings()
        sett.ignoreWhitespaceChanged.connect(
            self.__onIgnoreWhitespaceChanged)
        self.__onIgnoreWhitespaceChanged(sett.ignoreWhitespace())

        self.fileListView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.fileListView.customContextMenuRequested.connect(
            self.__onFileListViewContextMenuRequested)

        self.fetcher.diffAvailable.connect(
            self.__onDiffAvailable)
        self.fetcher.fetchFinished.connect(
            self.__onFetchFinished)

        self._difftoolProc = None
        self._withinFileRowChanged = False

        self.fileListView.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.fileListView.installEventFilter(self)

    def __onFileListViewCurrentRowChanged(self, current, previous):
        if not self._withinFileRowChanged and current.isValid():
            row = current.data(FileListModel.RowRole)
            # do not fire the __onFileRowChanged
            self.viewer.blockSignals(True)
            self.viewer.gotoLine(row, False)
            self.viewer.blockSignals(False)

    def __onFileRowChanged(self, row):
        for i in range(self.fileListProxy.rowCount()):
            index = self.fileListProxy.index(i, 0)
            if index.data(FileListModel.RowRole) == row:
                self._withinFileRowChanged = True
                self.fileListView.setCurrentIndex(index)
                self._withinFileRowChanged = False
                break

    def __onExternalDiff(self):
        index = self.fileListView.currentIndex()
        self.__runDiffTool(index)

    def __doCopyPath(self, asWin=False, absPath=False):
        indexList = self.fileListView.selectionModel().selectedRows()
        paths = ""
        for index in indexList:
            path = index.data()
            if absPath and Git.REPO_DIR:
                repoDir = Git.repoTopLevelDir(Git.REPO_DIR) or Git.REPO_DIR
                path = repoDir + "/" + path
            if asWin:
                path = path.replace('/', '\\')
            if paths:
                paths += "\n" + path
            else:
                paths += path

        if paths:
            clipboard = QApplication.clipboard()
            clipboard.setText(paths)

    def __onCopyPath(self):
        self.__doCopyPath()

    def __onCopyAbsPath(self):
        self.__doCopyPath(absPath=True)

    def __onCopyWinPath(self):
        self.__doCopyPath(True)

    def __onCopyWinAbsPath(self):
        self.__doCopyPath(True, absPath=True)

    def __onOpenContainingFolder(self):
        index = self.fileListView.currentIndex()
        if not index.isValid():
            return

        filePath = index.data()
        repoDir = Git.repoTopLevelDir(Git.REPO_DIR) or Git.REPO_DIR
        fullPath = repoDir + "/" + filePath
        if os.name == "nt":
            args = ["/select,", fullPath.replace("/", "\\")]
            QProcess.startDetached("explorer", args)
        else:
            dir = QFileInfo(fullPath).absolutePath()
            QDesktopServices.openUrl(QUrl.fromLocalFile(dir))

    def __onFilterPath(self):
        index = self.fileListView.currentIndex()
        if not index.isValid():
            return

        filePath = index.data()
        self.window().setFilterFile(filePath)

    def __onBlameFile(self):
        index = self.fileListView.currentIndex()
        if not index.isValid():
            return

        self.requestBlame.emit(index.data(), False, self.commit)

    def __onBlameParentCommit(self):
        index = self.fileListView.currentIndex()
        if not index.isValid():
            return

        self.requestBlame.emit(index.data(), True, self.commit)

    def __onRestoreFiles(self):
        indexes = self.fileListView.selectedIndexes()
        if not indexes:
            return

        repoFiles = {}
        for index in indexes:
            if self.__isCommentItem(index):
                continue
            filePath = index.data()
            commit = fileRealCommit(filePath, self.commit)
            assert commit.sha1 == Git.LCC_SHA1 or commit.sha1 == Git.LUC_SHA1

            if commit.repoDir and commit.repoDir != ".":
                filePath = filePath[len(commit.repoDir) + 1:]
            repoFiles.setdefault(commit.repoDir, []).append(filePath)

        if not repoFiles:
            return

        staged = self.commit.sha1 == Git.LCC_SHA1
        error = Git.restoreRepoFiles(repoFiles, staged, self.branchDir)
        if error:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                error)

        # TODO: reload the local changes only
        self.localChangeRestored.emit()

    def __isCommentItem(self, index):
        if not index.isValid():
            return False
        index = self.fileListProxy.mapToSource(index)
        return index.isValid() and index.row() == 0

    def __runDiffTool(self, index):
        if not index.isValid() or not self.commit:
            return

        filePath = index.data()
        commit = fileRealCommit(filePath, self.commit)
        if commit.repoDir and commit.repoDir != ".":
            filePath = filePath[len(commit.repoDir) + 1:]
        tool = DiffView.diffToolForFile(filePath)

        cwd = self.branchDir or Git.REPO_DIR
        if commit.repoDir and commit.repoDir != ".":
            cwd = os.path.join(cwd, commit.repoDir)

        args = ["difftool", "--no-prompt"]
        if commit.sha1 == Git.LUC_SHA1:
            pass
        elif commit.sha1 == Git.LCC_SHA1:
            args.append("--cached")
        else:
            args.append("{0}^..{0}".format(commit.sha1))

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

        self._difftoolProc.start(GitProcess.GIT_BIN, args)

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

    def __onFileListViewDoubleClicked(self, index):
        if not index.isValid() or self.__isCommentItem(index):
            return

        self.__runDiffTool(index)

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

    def __onFileListViewContextMenuRequested(self, pos):
        index = self.fileListView.currentIndex()
        if not index.isValid():
            return

        if self.__isCommentItem(index):
            return

        isLocalChanges = self.commit.sha1 in [Git.LUC_SHA1, Git.LCC_SHA1]
        if isLocalChanges:
            indexes = self.fileListView.selectedIndexes()
            fileCount = 0
            for index in indexes:
                if not self.__isCommentItem(index):
                    fileCount += 1
                    if fileCount > 1:
                        break
            text = self.tr("&Restore these files") if fileCount > 1 else self.tr(
                "&Restore this file")
            self.acRestoreFiles.setText(text)

        self.acRestoreFiles.setVisible(isLocalChanges)
        self.twMenu.exec(self.fileListView.mapToGlobal(pos))

    def __onDiffAvailable(self, lineItems, fileItems):
        self.__addToFileListView(fileItems)
        self.viewer.appendLines(lineItems)

    def __onFetchFinished(self, exitCode):
        # TODO: use multiprocessing maybe is better
        if self._commitList:
            commit = self._commitList.pop(0)
            self.fetcher.resetRow(self.viewer.textLineCount())
            if commit.repoDir != ".":
                self.fetcher.cwd = os.path.join(
                    self.branchDir or Git.REPO_DIR, commit.repoDir)
                self.fetcher.repoDir = commit.repoDir
            else:
                self.fetcher.cwd = self.branchDir or Git.REPO_DIR
            self.fetcher.fetch(commit.sha1, self.filterPath, self.gitArgs)
        else:
            self.fetcher.cwd = self.branchDir or Git.REPO_DIR
            self.viewer.endReading()
            self.endFetch.emit()

        if exitCode != 0 and self.fetcher.errorData:
            QMessageBox.critical(self, self.window().windowTitle(),
                                 self.fetcher.errorData.decode("utf-8"))

    def __addToFileListView(self, *args):
        """specify the @row number of the file in the viewer"""
        if len(args) == 1 and isinstance(args[0], dict):
            for file, info in args[0].items():
                self.fileListModel.addFile(file, info)
        else:
            self.fileListModel.addFile(args[0], FileInfo(args[1]))

        self._updateFilterStatus()

    def __commitDesc(self, commitOrSha1, repoDir=None):
        if isinstance(commitOrSha1, Commit):
            sha1 = commitOrSha1.sha1
            commit: Commit = commitOrSha1
        else:
            sha1 = commitOrSha1
            commit: Commit = None
        if sha1 == Git.LUC_SHA1:
            subject = self.tr(
                "Local uncommitted changes, not checked in to index")
        elif sha1 == Git.LCC_SHA1:
            subject = self.tr(
                "Local changes checked in to index but not committed")
        else:
            if commit:
                subject = commit.comments.split('\n')[0]
            else:
                repoDir = fullRepoDir(repoDir, self.branchDir)
                subject = Git.commitSubject(sha1, repoDir).decode("utf-8")
            fm = QFontMetricsF(self.viewer._font)
            subject = fm.elidedText(subject, Qt.ElideRight, 700)

        return " (" + subject + ")"

    def __commitToTextLines(self, commit: Commit):
        isLocalChanges = commit.sha1 in [Git.LUC_SHA1, Git.LCC_SHA1]
        if not isLocalChanges:
            content = self.tr("Author: ") + commit.author + \
                " " + commit.authorDate
            self.viewer.addAuthorLine(content)

            content = self.tr("Committer: ") + commit.committer + \
                " " + commit.committerDate
            self.viewer.addAuthorLine(content)
        else:
            self.viewer.addAuthorLine(self.tr("Author: ") + self.tr("You"))

        if ApplicationBase.instance().settings().showParentChild():
            for parent in commit.parents:
                content = self.tr("Parent: ") + parent
                repoDir = commit.repoDir
                if isLocalChanges and repoDir:
                    index = self.commitSource.findCommitIndex(parent)
                    if index != -1:
                        parentCommit = self.commitSource.getCommit(index)
                        repoDir = parentCommit.repoDir

                content += self.__commitDesc(parent, repoDir)
                self.viewer.addSHA1Line(content, True)

            for child in commit.children:
                content = self.tr("Child: ") + child.sha1
                content += self.__commitDesc(child, child.repoDir)
                self.viewer.addSHA1Line(content, False)

        for subCommit in commit.subCommits:
            content = makeRepoName(subCommit.repoDir) + ": " + subCommit.sha1
            if commit.sha1 in [Git.LUC_SHA1, Git.LCC_SHA1]:
                content += " (" + commit.comments + ")"
            else:
                content += " (" + commit.author + " " + commit.authorDate + ")"
            self.viewer.addSHA1Line(content, False)

        self.viewer.addNormalTextLine("", False)

        comments = commit.comments.split('\n')
        for comment in comments:
            self.viewer.addSummaryTextLine(comment)

        self.viewer.addNormalTextLine("", False)

    @staticmethod
    def diffToolForFile(filePath):
        tools = ApplicationBase.instance().settings().mergeToolList()
        # ignored case even on Unix platform
        lowercase_file = filePath.lower()
        for tool in tools:
            if tool.canDiff() and tool.isValid():
                if lowercase_file.endswith(tool.suffix.lower()):
                    return tool.command

        return ApplicationBase.instance().settings().diffToolName()

    def showCommit(self, commit: Commit):
        self.clear()
        self.commit = commit

        self.__addToFileListView(self.tr("Comments"), 0)

        index = self.fileListProxy.index(0, 0)
        self.fileListView.setCurrentIndex(index)

        self.__commitToTextLines(commit)

        self.viewer.setParentCount(len(commit.parents))
        self.viewer.beginReading()
        self.fetcher.resetRow(self.viewer.textLineCount())
        if commit.repoDir and commit.repoDir != ".":
            self.fetcher.cwd = os.path.join(
                self.branchDir or Git.REPO_DIR, commit.repoDir)
            self.fetcher.repoDir = commit.repoDir
        else:
            self.fetcher.cwd = self.branchDir or Git.REPO_DIR
            self.fetcher.repoDir = None
        self.fetcher.fetch(commit.sha1, self.filterPath, self.gitArgs)
        # FIXME: delay showing the spinner when loading small diff to avoid flicker
        self.beginFetch.emit()

        self._commitList = commit.subCommits.copy()

    def clear(self):
        self.fileListModel.clear()
        self.viewer.clear()
        self._updateFilterStatus()

    def setFilterPath(self, path):
        # no need update
        self.filterPath = path

    def highlightKeyword(self, pattern, field=FindField.Comments):
        self.viewer.highlightKeyword(pattern, field)

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

    def _onFileListFilterChanged(self, text):
        self.fileListProxy.setFilterRegularExpression(text)

        if not text:
            # restore previus row
            index = self.fileListView.currentIndex()
            if not index.isValid() and self.fileListProxy.rowCount():
                row = self.viewer.currentFileRow()
                self.__onFileRowChanged(row)
        else:
            index = self.fileListProxy.index(0, 0)
            self.fileListView.setCurrentIndex(index)

        self._updateFilterStatus()

    def _updateFilterStatus(self):
        if not self.fileListProxy.filterRegularExpression().pattern():
            self.filterStatus.setText(str(self.fileListProxy.rowCount()))
        else:
            self.filterStatus.setText("{}/{}".format(
                self.fileListProxy.rowCount(),
                self.fileListModel.rowCount()))

    def eventFilter(self, obj, event):
        if obj == self.fileListView and \
                event.type() == QEvent.KeyPress:
            if event.matches(QKeySequence.SelectAll):
                self.fileListView.selectAll()
                return True
            elif event.matches(QKeySequence.Copy):
                self.__onCopyPath()
                return True

        return super().eventFilter(obj, event)

    def closeFindWidget(self):
        return self.viewer.closeFindWidget()

    def queryClose(self):
        self.fetcher.cancel()
        return True

    def setCommitSource(self, source: CommitSource):
        self.commitSource = source
