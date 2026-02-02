# -*- coding: utf-8 -*-

from typing import List, Optional

from PySide6.QtCore import QObject, QSize, QTimer
from PySide6.QtGui import QIcon

from qgitc.aichatcontextprovider import AiChatContextProvider, AiContextDescriptor
from qgitc.applicationbase import ApplicationBase
from qgitc.common import Commit, dataDirPath
from qgitc.diffview import FileListModel
from qgitc.drawutils import makeColoredIconPixmap


class MainWindowContextProvider(AiChatContextProvider):
    """Context provider for the embedded AI chat inside MainWindow."""

    CTX_ACTIVE_COMMIT = "commit.active"
    CTX_SELECTED_COMMITS = "commit.selected"
    CTX_SELECTED_FILES = "files.selected"
    CTX_DIFF_SELECTION = "diff.selection"

    def __init__(self, mainWindow, parent: QObject = None):
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

        cbSub = self._mainWindow.ui.cbSubmodule
        cbSub.currentIndexChanged.connect(self._scheduleChanged)
        ApplicationBase.instance().submoduleAvailable.connect(
            lambda *_: self._scheduleChanged())

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

    def _submodules(self) -> List[str]:
        return ApplicationBase.instance().submodules or []

    def _activeSubmodule(self) -> str:
        cb = self._mainWindow.ui.cbSubmodule
        return cb.currentText()

    def _selectedCommits(self) -> List[Commit]:
        gitView = self._gitView()
        if not gitView:
            return []
        return gitView.ui.logView.getSelectedCommits()

    def _activeCommit(self) -> Optional[Commit]:
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
        icoSelect = self._themedIcon("select-all.svg")

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
        blocks: List[str] = self.commonContext()
        branch = self._activeBranch()
        if branch:
            blocks.append(f"Active branch (UI): {branch}")

        submodules = [s for s in (self._submodules() or []) if s]
        submoduleCount = len([s for s in submodules if s != "."])
        activeSub = self._activeSubmodule()
        if submoduleCount > 0 or activeSub:
            blocks.append(f"Submodules: {submoduleCount}")
            if activeSub:
                blocks.append(f"Active submodule (UI): {activeSub}")

        for cid in contextIds:
            if cid == self.CTX_ACTIVE_COMMIT:
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

        return "\n".join(b for b in blocks if b).strip()

    def agentSystemPrompt(self) -> Optional[str]:
        return """You are a Git assistant inside QGitc log view.

In log view user can explore git logs (commit sha1, messages, author, dates etc) and the selected commit's diff (and its file list). User can also switch branches and submodules (if any).

When the user provides context (inside <context></context> tags), use it first.
- If the question can be answered from context (especially UI state like active branch/submodule), answer directly and do NOT call tools.
- Only call tools when context is missing/unclear or when the user explicitly asks you to run a git command.

Branch/submodule semantics:
- Prefer 'Active branch (UI)' from context when asked about the current/active branch.
- Do NOT call git_current_branch just to answer branch questions if the UI branch is present, unless explicitly requested.
- The repository's checked-out HEAD branch may differ from the UI-selected branch.

If you need repo information or to perform git actions, call tools. Never assume.
"""
