# -*- coding: utf-8 -*-

from typing import List, Optional

from PySide6.QtCore import QObject, QSize, QTimer
from PySide6.QtGui import QIcon

from qgitc.aichatcontextprovider import AiChatContextProvider, AiContextDescriptor
from qgitc.common import dataDirPath, toSubmodulePath
from qgitc.drawutils import makeColoredIconPixmap
from qgitc.filestatus import StatusFileListModel


class CommitContextProvider(AiChatContextProvider):
    """Context provider for the embedded AI chat inside CommitWindow."""

    CTX_STAGED_FILES = "commit.staged"
    CTX_UNSTAGED_FILES = "commit.unstaged"
    CTX_SELECTED_DIFF = "commit.diff"
    CTX_COMMIT_MESSAGE = "commit.message"

    def __init__(self, commitWindow, parent: QObject = None):
        super().__init__(parent or commitWindow)
        from qgitc.commitwindow import CommitWindow
        self._commitWindow: CommitWindow = commitWindow

        self._iconsDir = dataDirPath() + "/icons"

        self._emitTimer = QTimer(self)
        self._emitTimer.setSingleShot(True)
        self._emitTimer.timeout.connect(self.contextsChanged.emit)

        self._installHooks()

    def _scheduleChanged(self):
        if not self._emitTimer.isActive():
            self._emitTimer.start(0)

    def _installHooks(self):
        """Install hooks to detect context changes"""
        # Staged/unstaged file list changes
        self._commitWindow._stagedModel.rowsInserted.connect(
            lambda *_: self._scheduleChanged())
        self._commitWindow._stagedModel.rowsRemoved.connect(
            lambda *_: self._scheduleChanged())
        self._commitWindow._filesModel.rowsInserted.connect(
            lambda *_: self._scheduleChanged())
        self._commitWindow._filesModel.rowsRemoved.connect(
            lambda *_: self._scheduleChanged())

        # File selection changes
        self._commitWindow.ui.lvFiles.selectionModel().currentRowChanged.connect(
            lambda *_: self._scheduleChanged())
        self._commitWindow.ui.lvStaged.selectionModel().currentRowChanged.connect(
            lambda *_: self._scheduleChanged())

        # Commit message changes
        self._commitWindow.ui.teMessage.textChanged.connect(
            self._scheduleChanged)

        # Diff viewer selection
        self._commitWindow.ui.viewer.selectionChanged.connect(
            self._scheduleChanged)

        self._scheduleChanged()

    def _themedIcon(self, iconFile: str, size: int = 16) -> QIcon:
        icon = QIcon(self._iconsDir + "/" + iconFile)
        pixmap = makeColoredIconPixmap(
            self._commitWindow, icon, QSize(size, size))
        return QIcon(pixmap)

    def _getStagedFiles(self) -> List[str]:
        """Get list of staged files"""
        files = []
        model = self._commitWindow._stagedModel
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            repoDir = model.data(index, StatusFileListModel.RepoDirRole)
            file = toSubmodulePath(repoDir, model.data(index))
            files.append(file.replace("\\", "/"))
        return files

    def _getUnstagedFiles(self) -> List[str]:
        """Get list of unstaged files"""
        files = []
        model = self._commitWindow._filesModel
        for row in range(model.rowCount()):
            index = model.index(row, 0)
            repoDir = model.data(index, StatusFileListModel.RepoDirRole)
            file = toSubmodulePath(repoDir, model.data(index))
            files.append(file.replace("\\", "/"))
        return files

    def _getSelectedDiff(self) -> str:
        """Get the diff of currently selected file"""
        viewer = self._commitWindow.ui.viewer
        if viewer and viewer.hasSelection():
            return viewer.selectedText or ""
        return ""

    def _getCommitMessage(self) -> str:
        """Get the current commit message"""
        doc = self._commitWindow.ui.teMessage.document()
        message = self._commitWindow.ui.teMessage.toPlainText().strip()

        # This is template message
        if not doc.isEmpty() and not doc.isUndoAvailable():
            return message

        return self._commitWindow._filterMessage(message)

    def availableContexts(self) -> List[AiContextDescriptor]:
        contexts: List[AiContextDescriptor] = []

        icoStage = self._themedIcon("stage.svg")
        icoFile = self._themedIcon("filter-list.svg")
        icoSelect = self._themedIcon("select-all.svg")
        icoMessage = self._themedIcon("commit.svg")

        stagedFiles = self._getStagedFiles()
        if stagedFiles:
            contexts.append(AiContextDescriptor(
                id=self.CTX_STAGED_FILES,
                label=self.tr("Staged files ({0})").format(len(stagedFiles)),
                icon=icoStage,
                tooltip="\n".join(stagedFiles[:12]) +
                ("\n…" if len(stagedFiles) > 12 else ""),
            ))

        unstagedFiles = self._getUnstagedFiles()
        if unstagedFiles:
            contexts.append(AiContextDescriptor(
                id=self.CTX_UNSTAGED_FILES,
                label=self.tr("Unstaged files ({0})").format(
                    len(unstagedFiles)),
                icon=icoFile,
                tooltip="\n".join(unstagedFiles[:12]) +
                ("\n…" if len(unstagedFiles) > 12 else ""),
            ))

        diffSelection = self._getSelectedDiff()
        if diffSelection:
            contexts.append(AiContextDescriptor(
                id=self.CTX_SELECTED_DIFF,
                label=self.tr("Selected diff"),
                icon=icoSelect,
                tooltip=self.tr("Selected diff text from viewer"),
            ))

        commitMessage = self._getCommitMessage()
        if commitMessage:
            label = self.tr("Commit message")

            preview = commitMessage.splitlines()[0] if commitMessage else ""
            if len(preview) > 60:
                preview = preview[:57] + "..."

            contexts.append(AiContextDescriptor(
                id=self.CTX_COMMIT_MESSAGE,
                label=label,
                icon=icoMessage,
                tooltip=preview,
            ))

        return contexts

    def defaultContextIds(self) -> List[str]:
        """Default contexts to include"""
        defaults = []

        # Always include staged files if available
        if self._getStagedFiles():
            defaults.append(self.CTX_STAGED_FILES)

        # Include commit message if it exists
        if self._getCommitMessage():
            defaults.append(self.CTX_COMMIT_MESSAGE)

        return defaults

    def buildContextText(self, contextIds: List[str]) -> str:
        blocks: List[str] = self.commonContext()
        blocks.append(f"Current branch: {self._commitWindow.currentBranch()}")

        for cid in contextIds:
            if cid == self.CTX_STAGED_FILES:
                files = self._getStagedFiles()
                if files:
                    blocks.append(
                        f"Staged files ({len(files)}):\n" +
                        "\n".join(f"- {f}" for f in files[:100])
                    )

            elif cid == self.CTX_UNSTAGED_FILES:
                files = self._getUnstagedFiles()
                if files:
                    blocks.append(
                        f"Unstaged files ({len(files)}):\n" +
                        "\n".join(f"- {f}" for f in files[:100])
                    )

            elif cid == self.CTX_SELECTED_DIFF:
                diff = self._getSelectedDiff()
                if diff:
                    blocks.append(
                        "Selected diff excerpt:\n```diff\n" + diff + "\n```")

            elif cid == self.CTX_COMMIT_MESSAGE:
                message = self._getCommitMessage()
                if message:
                    doc = self._commitWindow.ui.teMessage.document()
                    isTemplate = not doc.isUndoAvailable()
                    status = "template" if isTemplate else "draft"
                    blocks.append(
                        f"Current commit message ({status}):\n{message}")

        return "\n".join(b for b in blocks if b).strip()

    def agentSystemPrompt(self) -> Optional[str]:
        return """You are a Git assistant inside QGitc commit window.

In commit window user can:
- View and manage staged files (files ready to commit)
- View and manage unstaged files (modified files not yet staged)
- View diffs of selected files
- Write/edit commit messages
- Perform git operations like stage, unstage, commit

When the user provides context (inside <context></context> tags), use it first.
- If the question can be answered from context (like list of staged files, commit message), answer directly.
- Only call tools when context is missing/unclear or when the user explicitly asks you to run a git command.

Common tasks:
- Help write/improve commit messages based on staged changes
- Analyze diffs and suggest what to stage/unstage
- Review code changes before committing
- Suggest conventional commit formats
- Explain what changes are about to be committed

IMPORTANT - Commit Message Format:
- Lines starting with '#' are comment lines and will be ignored by Git
- When referring to or generating commit messages, exclude lines that start with '#'
- These comment lines are typically used for instructions or templates
- Only include actual commit content (non-comment lines) in your responses

If you need repo information or to perform git actions, call tools. Never assume.
"""
