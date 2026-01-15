import queue as queue
from typing import List, Union

from PySide6.QtCore import QEvent

from qgitc.aichatwidget import AiChatWidget
from qgitc.applicationbase import ApplicationBase
from qgitc.cancelevent import CancelEvent
from qgitc.common import fullRepoDir, logger, toSubmodulePath
from qgitc.gitutils import Git
from qgitc.statewindow import StateWindow
from qgitc.submoduleexecutor import SubmoduleExecutor


class DiffAvailableEvent(QEvent):
    Type = QEvent.User + 1

    def __init__(self, diff: str):
        super().__init__(QEvent.Type(DiffAvailableEvent.Type))
        self.diff = diff


class AiChatWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(self.tr("AI Assistant"))
        centralWidget = AiChatWidget(self)
        self.setCentralWidget(centralWidget)

        self._executor: SubmoduleExecutor = None
        self._diffs: List[str] = []

    def codeReview(self, commit, args=None):
        self.centralWidget().codeReview(commit, args)

    def codeReviewForStagedFiles(self, submodules: Union[list, dict]):
        self._ensureExecutor()
        self._diffs.clear()
        self._executor.submit(submodules, self._fetchDiff)

    def _ensureExecutor(self):
        if self._executor is None:
            self._executor = SubmoduleExecutor(self)
            self._executor.finished.connect(self._onExecuteFinished)

    def _onExecuteFinished(self):
        if self._diffs:
            diff = "\n".join(self._diffs)
            self.centralWidget().codeReviewForDiff(diff)

    def _fetchDiff(self, submodule: str, files, cancelEvent: CancelEvent):
        repoDir = fullRepoDir(submodule)
        repoFiles = [toSubmodulePath(submodule, file) for file in files]
        data: bytes = Git.commitRawDiff(
            Git.LCC_SHA1, repoFiles, repoDir=repoDir)
        if not data:
            logger.warning("AiChat: no diff for %s", repoDir)
            return

        if cancelEvent.isSet():
            return

        diff = data.decode("utf-8", errors="replace")
        ApplicationBase.instance().postEvent(self, DiffAvailableEvent(diff))

    def event(self, event: QEvent):
        if event.type() == DiffAvailableEvent.Type:
            if event.diff:
                self._diffs.append(event.diff)
            return True

        return super().event(event)

    def closeEvent(self, event):
        if self._executor:
            self._executor.cancel()
            self._executor = None
        self.centralWidget().queryClose()
        return super().closeEvent(event)
