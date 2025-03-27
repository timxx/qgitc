# -*- coding: utf-8 -*-

from PySide6.QtCore import QTimer

from .findsubmodules import FindSubmoduleThread
from .gitutils import Git
from .statewindow import StateWindow
from .statusfetcher import StatusFetcher
from .ui_commitwindow import Ui_CommitWindow


class CommitWindow(StateWindow):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_CommitWindow()
        self.ui.setupUi(self)

        width = self.ui.splitterMain.sizeHint().width()
        sizes = [width * 2 / 5, width * 3 / 5]
        self.ui.splitterMain.setSizes(sizes)

        height = self.ui.splitterRight.sizeHint().height()
        sizes = [height * 3 / 5, height * 2 / 5]
        self.ui.splitterRight.setSizes(sizes)

        self.setWindowTitle(self.tr("QGitc Commit"))

        self._fetcher = StatusFetcher(self)
        self._fetcher.resultAvailable.connect(self._onStatusAvailable)
        self._fetcher.finished.connect(self._onFetchFinished)

        QTimer.singleShot(0, self._loadLocalChanges)

        self._findSubmoduleThread = FindSubmoduleThread(Git.REPO_DIR, self)
        self._findSubmoduleThread.finished.connect(
            self._onFindSubmoduleFinished)
        self._findSubmoduleThread.start()

    def _loadLocalChanges(self):
        submodules = qApp.settings().submodulesCache(Git.REPO_DIR)
        self._fetcher.fetch(submodules)

    def _onFindSubmoduleFinished(self):
        submodules = self._findSubmoduleThread.submodules
        if not submodules:
            return

        # TODO: only fetch newly added submodules
        self._fetcher.fetch(submodules)

    def _onStatusAvailable(self, repoDir, status):
        print(repoDir, status)

    def _onFetchFinished(self):
        print("Fetch finished")
