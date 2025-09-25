# -*- coding: utf-8 -*-

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QSplitter

from qgitc.commitdetailpanel import CommitDetailPanel
from qgitc.common import fullRepoDir
from qgitc.logview import LogView
from qgitc.textline import Link


class CommitPanel(QSplitter):

    linkActivated = Signal(Link)
    requestBlame = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)

        self._logView = LogView(self)
        self._logView.setFrameStyle(QFrame.Shape.StyledPanel)
        self._logView.setEditable(False)
        self._logView.setShowNoDataTips(False)
        self._logView.setStandalone(False)

        self._detailPanel = CommitDetailPanel(self)

        self.addWidget(self._logView)
        self.addWidget(self._detailPanel)

        self._logView.currentIndexChanged.connect(
            self._onCommitChanged)
        self._logView.endFetch.connect(
            self._onLogFetchFinished)

        self._detailPanel.linkActivated.connect(
            self.linkActivated)

    def clear(self):
        self._detailPanel.clear()
        self._logView.setCurrentIndex(-1)

    def showLogs(self, repoDir: str, file: str, rev: str = None, args: List[str] = None):
        args = args or []
        args += ["--follow", "--", file] if file else []
        self._logView.clear()
        self._logView.preferSha1 = rev
        repoDir = fullRepoDir(repoDir)
        self._logView.showLogs(branch=None, branchDir=repoDir, args=args)

    def _onCommitChanged(self, index: int):
        # do nothing if the log is still loading
        if self._logView.fetcher.isLoading():
            return

        self._detailPanel.clear()
        if index == -1:
            return

        commit = self._logView.getCommit(index)
        self._detailPanel.showCommit(commit)

    def _onLogFetchFinished(self):
        if self._detailPanel.textLineCount() > 0:
            return

        index = self._logView.currentIndex()
        if index != -1:
            commit = self._logView.getCommit(index)
            self._detailPanel.showCommit(commit)

    @property
    def logView(self) -> LogView:
        return self._logView
