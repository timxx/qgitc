# -*- coding: utf-8 -*-

import datetime
from typing import List

from PySide6.QtCore import QObject, QSize, QTimer
from PySide6.QtGui import QIcon

from qgitc.aichatcontextprovider import AiChatContextProvider, AiContextDescriptor
from qgitc.common import Commit, dataDirPath
from qgitc.diffview import FileListModel
from qgitc.drawutils import makeColoredIconPixmap


class MainWindowAiChatContextProvider(AiChatContextProvider):
    """Context provider for the embedded AI chat inside MainWindow."""

    CTX_ACTIVE_COMMIT = "commit.active"
    CTX_SELECTED_COMMITS = "commit.selected"
    CTX_SELECTED_FILES = "files.selected"
    CTX_ACTIVE_BRANCH = "branch.active"
    CTX_DIFF_SELECTION = "diff.selection"

    def __init__(self, mainWindow, parent: QObject | None = None):
        super().__init__(parent or mainWindow)
        from qgitc.mainwindow import MainWindow
        self._mainWindow: MainWindow = mainWindow

        self._iconsDir = dataDirPath() + "/icons"

        self._emitTimer = QTimer(self)
        self._emitTimer.setSingleShot(True)
        self._emitTimer.timeout.connect(self.contextsChanged.emit)

        self._installHooks()

    def _scheduleChanged(self):
        if not self._emitTimer.isActive():
            self._emitTimer.start(0)

    def _installHooks(self):
        gitView = self._mainWindow.ui.gitViewA
        if not gitView:
            return

        # Commit selection
        gitView.ui.logView.currentIndexChanged.connect(
            self._scheduleChanged)

        # Branch selector
        gitView.ui.cbBranch.currentIndexChanged.connect(
            self._scheduleChanged)

        # File list selection
        selModel = gitView.ui.diffView.fileListView.selectionModel()
        if selModel:
            selModel.selectionChanged.connect(
                lambda *_: self._scheduleChanged())

        # Diff text selection.
        gitView.ui.diffView.viewer.selectionChanged.connect(
            self._scheduleChanged)

        self._scheduleChanged()

    def _themedIcon(self, iconFile: str, size: int = 16) -> QIcon:
        icon = QIcon(self._iconsDir + "/" + iconFile)
        pixmap = makeColoredIconPixmap(
            self._mainWindow, icon, QSize(size, size))
        return QIcon(pixmap)

    def _gitView(self):
        return self._mainWindow.ui.gitViewA

    def _activeBranch(self) -> str:
        gitView = self._gitView()
        if not gitView:
            return ""

        return gitView.currentBranch()

    def _selectedCommits(self) -> List[Commit]:
        gitView = self._gitView()
        if not gitView:
            return []
        return gitView.ui.logView.getSelectedCommits()

    def _activeCommit(self) -> Commit | None:
        gitView = self._gitView()
        if not gitView:
            return None
        commit = gitView.ui.diffView.commit
        if commit:
            return commit

        commits = self._selectedCommits()
        return commits[0] if commits else None

    def _selectedFiles(self) -> List[str]:
        gitView = self._gitView()
        if not gitView:
            return []

        sel = gitView.ui.diffView.fileListView.selectionModel()
        if not sel:
            return []
        rows = sel.selectedRows() or []
        files = []
        for idx in rows:
            # Skip the non-file "Comments" entry (RowRole == 0)
            if idx.data(FileListModel.RowRole) == 0:
                continue
            p = idx.data()
            if p:
                files.append(p)
        return files

    def _diffSelection(self) -> str:
        gitView = self._gitView()
        if not gitView:
            return ""

        viewer = gitView.ui.diffView.viewer
        if viewer and viewer.hasSelection():
            return viewer.selectedText or ""

        return ""

    def availableContexts(self) -> List[AiContextDescriptor]:
        contexts: List[AiContextDescriptor] = []

        icoCommit = self._themedIcon("commit.svg")
        icoFiles = self._themedIcon("filter-list.svg")
        icoBranch = self._themedIcon("arrow-forward.svg")
        icoSelect = self._themedIcon("select-all.svg")

        branch = self._activeBranch()
        if branch:
            contexts.append(AiContextDescriptor(
                id=self.CTX_ACTIVE_BRANCH,
                label=self.tr("Active branch"),
                icon=icoBranch,
                tooltip=branch,
            ))

        active = self._activeCommit()
        if active and active.isValid():
            subj = (active.comments or "").splitlines()[
                0] if active.comments else ""
            contexts.append(AiContextDescriptor(
                id=self.CTX_ACTIVE_COMMIT,
                label=self.tr("Active commit"),
                icon=icoCommit,
                tooltip=f"{active.sha1[:7]} {subj}".strip(),
            ))

        commits = self._selectedCommits()
        if commits:
            contexts.append(AiContextDescriptor(
                id=self.CTX_SELECTED_COMMITS,
                label=self.tr("Selected commits ({0})").format(len(commits)),
                icon=icoCommit,
                tooltip="\n".join(
                    (f"{c.sha1[:7]} {(c.comments or '').splitlines()[0] if c.comments else ''}").strip(
                    )
                    for c in commits[:8]
                ) + ("\n…" if len(commits) > 8 else ""),
            ))

        files = self._selectedFiles()
        if files:
            contexts.append(AiContextDescriptor(
                id=self.CTX_SELECTED_FILES,
                label=self.tr("Selected files ({0})").format(len(files)),
                icon=icoFiles,
                tooltip="\n".join(files[:12]) +
                ("\n…" if len(files) > 12 else ""),
            ))

        diffSel = self._diffSelection()
        if diffSel:
            contexts.append(AiContextDescriptor(
                id=self.CTX_DIFF_SELECTION,
                label=self.tr("Diff selection"),
                icon=icoSelect,
                tooltip=self.tr("Selected diff text"),
            ))

        return contexts

    def defaultContextIds(self) -> List[str]:
        active = self._activeCommit()
        if active is not None and active.isValid():
            return [self.CTX_ACTIVE_COMMIT]
        return []

    def buildContextText(self, contextIds: List[str]) -> str:
        blocks: List[str] = []

        for cid in contextIds:
            if cid == self.CTX_ACTIVE_BRANCH:
                branch = self._activeBranch()
                if branch:
                    blocks.append(f"Active branch: {branch}")

            elif cid == self.CTX_ACTIVE_COMMIT:
                c = self._activeCommit()
                if c is not None and c.isValid():
                    blocks.append(
                        "Active commit:\n"
                        f"{c.sha1}\n"
                        f"Author: {c.author} {c.authorDate}\n"
                        f"Message:\n{c.comments}"
                    )

            elif cid == self.CTX_SELECTED_COMMITS:
                commits = self._selectedCommits()
                if commits:
                    lines = []
                    for c in commits[:20]:
                        subj = (c.comments or "").splitlines()[
                            0] if c.comments else ""
                        lines.append(f"- {c.sha1} {subj}".rstrip())
                    extra = "\n…" if len(commits) > 20 else ""
                    blocks.append(
                        f"Selected commits ({len(commits)}):\n" +
                        "\n".join(lines) + extra
                    )

            elif cid == self.CTX_SELECTED_FILES:
                files = self._selectedFiles()
                if files:
                    blocks.append(
                        f"Selected files ({len(files)}):\n" +
                        "\n".join(f"- {p}" for p in files[:200])
                    )

            elif cid == self.CTX_DIFF_SELECTION:
                text = self._diffSelection()
                if text:
                    blocks.append(
                        "Selected diff excerpt:\n```diff\n" + text + "\n```")

        return "\n\n".join(b for b in blocks if b).strip()
