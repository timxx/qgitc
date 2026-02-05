# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QObject

from qgitc.aichatcontextprovider import AiChatContextProvider


class CherryPickContextProvider(AiChatContextProvider):
    """Context provider for the embedded AI chat in CherryPickProgressDialog."""

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        self._targetBaseRepoDir: str = ""
        self._sourceBaseRepoDir: str = ""

        self._currentSha1: str = ""
        self._currentRepoDir: str = ""
        self._currentFile: str = ""

        self._operation: str = ""
        self._conflictFiles: List[str] = []

    def setBaseDirs(self, *, targetBaseRepoDir: str, sourceBaseRepoDir: str):
        self._targetBaseRepoDir = targetBaseRepoDir or ""
        self._sourceBaseRepoDir = sourceBaseRepoDir or ""
        self.contextsChanged.emit()

    def setCurrentItem(self, *, sha1: str, repoDir: str):
        self._currentSha1 = sha1 or ""
        self._currentRepoDir = repoDir or ""
        self.contextsChanged.emit()

    def setCurrentFile(self, path: str):
        self._currentFile = path or ""
        self.contextsChanged.emit()

    def setConflicts(self, *, operation: str, files: List[str]):
        self._operation = operation or ""
        self._conflictFiles = list(files or [])
        self.contextsChanged.emit()

    def buildContextText(self, contextIds: List[str]) -> str:
        blocks: List[str] = self.commonContext()

        if self._sourceBaseRepoDir:
            blocks.append(f"Source repo dir: {self._sourceBaseRepoDir}")
        if self._targetBaseRepoDir:
            blocks.append(f"Target repo dir: {self._targetBaseRepoDir}")

        if self._currentSha1:
            blocks.append(f"Current commit sha1: {self._currentSha1}")
        if self._currentRepoDir:
            blocks.append(f"Current repo dir: {self._currentRepoDir}")

        if self._operation:
            blocks.append(f"Operation: {self._operation}")

        if self._currentFile:
            blocks.append(f"Current conflicted file: {self._currentFile}")

        if self._conflictFiles:
            preview = "\n".join(f"- {p}" for p in self._conflictFiles[:50])
            suffix = "\n…" if len(self._conflictFiles) > 50 else ""
            blocks.append(
                f"Conflict files ({len(self._conflictFiles)}):\n{preview}{suffix}")

        return "\n".join(b for b in blocks if b).strip()
