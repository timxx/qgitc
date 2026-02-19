# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


@dataclass
class AmendCommitInfo:
    """Information about a commit that will be amended"""
    repoDir: Optional[str]  # None for main repo, submodule path otherwise
    sha1: str
    subject: str
    author: str
    date: str
    willAmend: bool = True  # Whether this commit will be amended
    body: Optional[str] = None


class AmendCommitListModel(QAbstractListModel):
    """Model for displaying commits that will be amended"""

    RepoDirRole = Qt.UserRole + 1
    Sha1Role = Qt.UserRole + 2
    SubjectRole = Qt.UserRole + 3
    WillAmendRole = Qt.UserRole + 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._commits = []
        self._showRepoName = True
        self._allowUncheck = False

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._commits)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._commits):
            return None

        commit = self._commits[index.row()]

        if role == Qt.DisplayRole:
            # Format: [repo] short_sha: subject
            repoLabel = commit.repoDir
            if not repoLabel or repoLabel == ".":
                repoLabel = "<main>"

            if self._showRepoName:
                return f"[{repoLabel}] {commit.sha1[:7]}: {commit.subject}"
            return f"{commit.sha1[:7]}: {commit.subject}"
        elif role == Qt.CheckStateRole:
            if not self._allowUncheck:
                return None
            return Qt.Checked if commit.willAmend else Qt.Unchecked
        elif role == Qt.ToolTipRole:
            tooltips = ""
            if self._showRepoName:
                repoLabel = commit.repoDir
                if not repoLabel or repoLabel == ".":
                    repoLabel = "<main>"
                tooltips += self.tr("Repository: {}".format(repoLabel)) + "\n"

            tooltips += self.tr("SHA-1: {}").format(commit.sha1) + "\n"
            tooltips += self.tr("Subject: {}").format(commit.subject) + "\n"
            tooltips += self.tr("Author: {}").format(commit.author) + "\n"
            tooltips += self.tr("Date: {}").format(commit.date)
            return tooltips

        elif role == self.RepoDirRole:
            return commit.repoDir
        elif role == self.Sha1Role:
            return commit.sha1
        elif role == self.SubjectRole:
            return commit.subject
        elif role == self.WillAmendRole:
            return commit.willAmend

        return None

    def setData(self, index: QModelIndex, value, role=Qt.EditRole):
        if not index.isValid() or index.row() >= len(self._commits):
            return False

        if role == Qt.CheckStateRole:
            self._commits[index.row()].willAmend = (value == Qt.Checked.value)
            self.dataChanged.emit(
                index, index, [Qt.CheckStateRole, self.WillAmendRole])
            return True

        return False

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self._allowUncheck:
            flags |= Qt.ItemIsUserCheckable
        return flags

    def clear(self):
        if not self._commits:
            return
        self.beginResetModel()
        self._commits.clear()
        self.endResetModel()

    def setCommits(self, commits):
        """Set the list of commits to display"""
        self.beginResetModel()
        self._commits = commits
        self.endResetModel()

    def setShowRepoName(self, showRepoName: bool):
        if self._showRepoName == showRepoName:
            return
        self._showRepoName = showRepoName
        if self._commits:
            topLeft = self.index(0, 0)
            bottomRight = self.index(len(self._commits) - 1, 0)
            self.dataChanged.emit(topLeft, bottomRight, [Qt.DisplayRole])

    def getAmendCommits(self):
        """Get the list of commits that will be amended (willAmend=True)"""
        return [c for c in self._commits if c.willAmend]

    def getAllCommits(self):
        """Get all commits in the model"""
        return self._commits

    def setAllowUncheck(self, allowUncheck: bool):
        self._allowUncheck = allowUncheck
