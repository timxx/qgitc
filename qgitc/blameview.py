# -*- coding: utf-8 -*-

import os
from typing import List

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.blamefetcher import BlameFetcher
from qgitc.blameline import BlameLine
from qgitc.blamesourceviewer import BlameSourceViewer
from qgitc.coloredicontoolbutton import ColoredIconToolButton
from qgitc.common import Commit, dataDirPath
from qgitc.events import OpenLinkEvent
from qgitc.gitutils import Git
from qgitc.logview import LogView
from qgitc.namefetcher import NameFetcher
from qgitc.patchviewer import SummaryTextLine
from qgitc.revisionpanel import RevisionPanel
from qgitc.textline import Link, LinkTextLine
from qgitc.textviewer import TextViewer
from qgitc.waitingspinnerwidget import QtWaitingSpinner

__all__ = ["BlameView"]


class BlameHistory:

    def __init__(self, file, rev=None, lineNo=0):
        self.file = file
        self.rev = rev
        self.lineNo = lineNo


class CommitDetailPanel(TextViewer):

    def __init__(self, viewer: BlameSourceViewer, parent=None):
        super().__init__(parent)
        self._viewer = viewer

        settings = ApplicationBase.instance().settings()
        settings.diffViewFontChanged.connect(self.delayUpdateSettings)

    def showCommit(self, commit: Commit, previous: str = None):
        super().clear()

        text = self.tr("Commit: ") + commit.sha1
        textLine = LinkTextLine(text, self._font, Link.Sha1)
        self.appendTextLine(textLine)

        text = self.tr("Author: ") + commit.author + " " + commit.authorDate
        textLine = LinkTextLine(text, self._font, Link.Email)
        self.appendTextLine(textLine)

        text = self.tr("Committer: ") + commit.committer + \
            " " + commit.committerDate
        textLine = LinkTextLine(text, self._font, Link.Email)
        self.appendTextLine(textLine)

        if previous:
            text = self.tr("Previous: ") + previous
            textLine = LinkTextLine(text, self._font, Link.Sha1)
            self.appendTextLine(textLine)

        if commit.comments:
            self.appendLine("")
            for line in commit.comments.splitlines():
                textLine = SummaryTextLine(line, self._font, self._option, 0)
                self.appendTextLine(textLine)

    def clear(self):
        super().clear()

    def reloadSettings(self):
        super().reloadSettings()
        self.updateFont(ApplicationBase.instance().settings().diffViewFont())

    def _reloadTextLine(self, textLine):
        super()._reloadTextLine(textLine)
        textLine.setFont(self._font)


class CommitPanel(QSplitter):

    linkActivated = Signal(Link)
    requestBlame = Signal(str, str)

    def __init__(self, viewer: BlameSourceViewer, parent=None):
        super().__init__(Qt.Horizontal, parent)

        self._nameFetcher = NameFetcher(self)
        self._nameFetcher.dataAvailable.connect(
            self._onNameAvailable)

        self._sha1Names = {}
        self._curFile = None

        self._viewer = viewer
        self.logView = LogView(self)
        self.logView.setFrameStyle(QFrame.Shape.StyledPanel)
        self.logView.setEditable(False)

        self.detailPanel = CommitDetailPanel(viewer, self)

        self.addWidget(self.logView)
        self.addWidget(self.detailPanel)

        self.logView.currentIndexChanged.connect(
            self._onCommitChanged)
        self.logView.endFetch.connect(
            self._onLogFetchFinished)

        self.detailPanel.linkActivated.connect(
            self.linkActivated)

    def clear(self):
        self.detailPanel.clear()
        self.logView.setCurrentIndex(-1)

    def showRevision(self, rev: BlameLine):
        self.logView.blockSignals(True)
        if self.logView.switchToCommit(rev.sha1):
            # the log is fetching, update later in _onCommitChanged
            index = self.logView.currentIndex()
            if index != -1:
                commit = self.logView.getCommit(index)
                self.detailPanel.showCommit(commit, rev.previous)
        else:
            self.detailPanel.clear()
        self.logView.blockSignals(False)

    def showLogs(self, repoDir: str, file: str, rev: str = None):
        assert (file)
        # only refresh the log if the file has changed
        normFile = os.path.normcase(os.path.normpath(file))
        if self._isFileCached(normFile, repoDir):
            return

        self._curFile = normFile

        self._sha1Names.clear()
        self._nameFetcher.cwd = repoDir
        self._nameFetcher.fetch(file)

        args = ["--follow", "--", file]
        self.logView.clear()
        self.logView.preferSha1 = rev
        self.logView.showLogs(branch=None, branchDir=repoDir, args=args)

    def _isFileCached(self, file: str, repoDir: str):
        if self._curFile is None:
            return False

        if self._curFile == file:
            return True

        normRepoDir = os.path.normcase(os.path.normpath(repoDir))
        if normRepoDir.endswith(os.sep):
            normRepoDir = normRepoDir[:-1]

        isAbsFile = os.path.isabs(file)
        isAbsCurFile = os.path.isabs(self._curFile)
        if not isAbsFile and isAbsCurFile:
            if os.path.join(normRepoDir, file) == self._curFile:
                return True
        elif isAbsFile and not isAbsCurFile:
            if os.path.join(normRepoDir, self._curFile) == file:
                return True

        if isAbsFile and file.startswith(normRepoDir):
            file = file[len(normRepoDir) + 1:]

        file.replace("\\", "/")
        if file in self._sha1Names.values():
            return True

        return False

    def _onCommitChanged(self, index: int):
        # do nothing if the log is still loading
        if self.logView.fetcher.isLoading():
            return

        self.detailPanel.clear()
        if index == -1:
            return

        commit = self.logView.getCommit(index)
        file = self._sha1Names.get(commit.sha1)
        assert (file is not None)

        panel: RevisionPanel = self._viewer.panel
        i = panel.setActiveRevBySha1(commit.sha1)
        if i == -1:
            previous = None
            self.requestBlame.emit(commit.sha1, file)
        else:
            previous = panel.revisions[i].previous

        self.detailPanel.showCommit(commit, previous)

    def _onLogFetchFinished(self):
        panel: RevisionPanel = self._viewer.panel
        rev = panel._activeRev
        if rev:
            self.logView.switchToCommit(rev)
        else:
            self.logView.setCurrentIndex(-1)

    def _onNameAvailable(self, data: List[tuple]):
        if not data:
            return

        for sha1, file in data:
            self._sha1Names[sha1] = file


class HeaderWidget(QWidget):

    def __init__(self, view=None):
        super().__init__(view)

        self._view = view
        self._histories = []
        self._curIndex = 0
        self._blockAdd = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        def _newButton(svg):
            fullPath = dataDirPath() + "/icons/" + svg
            icon = QIcon(fullPath)
            return ColoredIconToolButton(icon, QSize(20, 20), self)

        self._btnPrev = _newButton("arrow-back.svg")
        layout.addWidget(self._btnPrev)

        self._btnNext = _newButton("arrow-forward.svg")
        layout.addWidget(self._btnNext)

        self._waitingSpinner = QtWaitingSpinner(self)
        layout.addWidget(self._waitingSpinner)

        self._lbFile = QLabel(self)
        layout.addWidget(self._lbFile)

        self._lbRev = QLabel(self)
        layout.addWidget(self._lbRev)
        layout.addSpacerItem(QSpacerItem(
            0, 0,
            QSizePolicy.Expanding,
            QSizePolicy.Fixed))

        self._btnPrev.clicked.connect(
            self._onPrevious)
        self._btnNext.clicked.connect(
            self._onNext)

        height = self._lbFile.height() // 6
        self._waitingSpinner.setLineLength(height)
        self._waitingSpinner.setInnerRadius(height)
        self._waitingSpinner.setNumberOfLines(14)

        self._updateInfo()

    def _updateInfo(self):
        if not self._histories:
            file = ""
            rev = ""
        else:
            history = self._histories[self._curIndex]
            rev = history.rev
            file = history.file
            if rev is None:
                rev = ""

        self._lbRev.setText(rev)
        self._lbFile.setText(file)

        enablePrev = False
        enableNext = False

        total = len(self._histories)
        if total > 1:
            if self._curIndex != 0:
                enablePrev = True
            if self._curIndex != total - 1:
                enableNext = True
        self._btnPrev.setEnabled(enablePrev)
        self._btnNext.setEnabled(enableNext)

    def _blameCurrent(self):
        self._blockAdd = True
        history = self._histories[self._curIndex]
        self._view.blame(history.file, history.rev,
                         history.lineNo, self._view.viewer.repoDir)
        self._blockAdd = False

    def _onPrevious(self):
        self._curIndex -= 1
        self._updateInfo()
        self._blameCurrent()

    def _onNext(self):
        self._curIndex += 1
        self._updateInfo()
        self._blameCurrent()

    def clear(self):
        self._histories.clear()
        self._updateInfo()

    def addBlameInfo(self, file, rev, lineNo):
        if self._blockAdd:
            return

        index = -1
        for i in range(len(self._histories)):
            history = self._histories[i]
            if file == history.file and rev == history.rev:
                index = i
                break

        if index != -1:
            self._curIndex = index
        else:
            self._curIndex += 1
            self._histories.insert(
                self._curIndex, BlameHistory(file, rev, lineNo))
            if self._curIndex >= len(self._histories):
                self._curIndex = len(self._histories) - 1

        self._updateInfo()

    def notifyFecthingStarted(self):
        self._waitingSpinner.start()

    def notifyFecthingFinished(self):
        self._waitingSpinner.stop()

    def updateCurPos(self, lineNo):
        assert (0 <= self._curIndex < len(self._histories))
        self._histories[self._curIndex].lineNo = lineNo + 1


class BlameView(QWidget):

    blameFileAboutToChange = Signal(str)
    blameFileChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.setSpacing(4)

        sourceWidget = QWidget(self)
        layout = QVBoxLayout(sourceWidget)
        layout.setContentsMargins(0, 0, 0, 0)

        self._headerWidget = HeaderWidget(self)
        layout.addWidget(self._headerWidget)

        self._viewer = BlameSourceViewer(self)
        layout.addWidget(self._viewer)

        self._commitPanel = CommitPanel(self._viewer, self)
        self._commitPanel.requestBlame.connect(
            self._onRequestBlame)

        vSplitter = QSplitter(Qt.Vertical, self)
        vSplitter.addWidget(sourceWidget)
        vSplitter.addWidget(self._commitPanel)

        height = vSplitter.sizeHint().height()
        sizes = [height * 4 / 5, height * 1 / 5]
        vSplitter.setSizes(sizes)

        mainLayout.addWidget(vSplitter)

        self._file = None
        self._rev = None
        self._lineNo = -1

        self._fetcher = BlameFetcher(self)
        self._fetcher.dataAvailable.connect(
            self._onFetchDataAvailable)
        self._fetcher.fetchFinished.connect(
            self._onFetchFinished)

        self._commitPanel.linkActivated.connect(
            self._onLinkActivated)
        self._viewer.linkActivated.connect(
            self._onLinkActivated)
        self._viewer.revisionActivated.connect(
            self._commitPanel.showRevision)

        self.viewer.currentLineChanged.connect(
            self._headerWidget.updateCurPos)

    def _onLinkActivated(self, link):
        if link.type == Link.Sha1:
            if self._rev != link.data:
                file = self._findFileBySHA1(link.data)
                self.blame(file, link.data, repoDir=self._viewer.repoDir)
        else:
            ApplicationBase.instance().postEvent(
                ApplicationBase.instance(), OpenLinkEvent(link))

    def _onFetchDataAvailable(self, lines: List[BlameLine]):
        self._viewer.appendBlameLines(lines)

    def _onFetchFinished(self, exitCode):
        self.blameFileChanged.emit(self._file)
        self._headerWidget.notifyFecthingFinished()
        if self._lineNo > 0:
            self._viewer.gotoLine(self._lineNo - 1)
            self._viewer.panel.setActiveRevByLineNumber(self._lineNo - 1)
            self._lineNo = -1
        elif self._rev:
            self._viewer.panel.setActiveRevBySha1(self._rev)
        self._viewer.endReading()
        if not self._viewer.hasTextLines() and self._fetcher.errorData:
            QMessageBox.critical(self, self.window().windowTitle(),
                                 self._fetcher.errorData.decode("utf-8"))

    def _findFileBySHA1(self, sha1):
        file = self._viewer.panel.getFileBySHA1(sha1)
        return file if file else self._file

    def clear(self):
        self._viewer.clear()
        self._commitPanel.clear()

    def blame(self, file, rev=None, lineNo=0, repoDir=None):
        if not Git.available():
            return

        if self._file == file and self._rev == rev:
            return

        self._headerWidget.notifyFecthingStarted()
        self.blameFileAboutToChange.emit(file)
        self.clear()
        self._viewer.repoDir = repoDir
        self._viewer.beginReading()
        self._fetcher.cwd = repoDir or Git.REPO_DIR
        self._fetcher.fetch(file, rev)

        self._commitPanel.showLogs(self._fetcher.cwd, file, rev)

        self._file = file
        self._rev = rev
        self._lineNo = lineNo

        self._headerWidget.addBlameInfo(file, rev, lineNo)

    @property
    def viewer(self):
        return self._viewer

    @property
    def commitPanel(self):
        return self._commitPanel

    def queryClose(self):
        self._fetcher.cancel()

    def _onRequestBlame(self, sha1: str, file: str):
        self.blame(file, sha1, repoDir=self._viewer.repoDir)
        self._viewer.gotoLine(0)
        self._viewer.panel.setActiveRevBySha1(sha1)
