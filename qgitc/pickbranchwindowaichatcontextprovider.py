# -*- coding: utf-8 -*-

from typing import List

from PySide6.QtCore import QObject

from qgitc.aichatcontextprovider import AiChatContextProvider, AiContextDescriptor
from qgitc.gitutils import Git


class PickBranchWindowAiChatContextProvider(AiChatContextProvider):
    """AI chat context provider for the Pick Branch window."""

    def __init__(self, pickBranchWindow: QObject, parent=None):
        super().__init__(parent)
        from qgitc.pickbranchwindow import PickBranchWindow
        self._window: PickBranchWindow = pickBranchWindow

    def buildContextText(self, contextIds: List[str]) -> str:
        ui = self._window.ui
        sourceBranch = ui.cbSourceBranch.currentText()
        sourceDir = Git.branchDir(sourceBranch) or Git.REPO_DIR
        targetBranch = ui.cbTargetBranch.currentText()
        targetDir = Git.branchDir(targetBranch) or Git.REPO_DIR
        baseBranch = ui.cbBaseBranch.currentText()
        baseDir = Git.branchDir(baseBranch) or Git.REPO_DIR
        return (
            f"Source branch: {sourceBranch}\n"
            f"Source repo dir: {sourceDir}\n"
            f"Target branch: {targetBranch}\n"
            f"Target repo dir: {targetDir}\n"
            f"Base branch: {baseBranch}\n"
            f"Base repo dir: {baseDir}\n"
        )
