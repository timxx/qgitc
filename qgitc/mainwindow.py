# -*- coding: utf-8 -*-

import os
import shlex
import sys
from datetime import datetime
from typing import List

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QComboBox, QCompleter, QFileDialog, QLineEdit, QMessageBox

from qgitc.aboutdialog import AboutDialog
from qgitc.applicationbase import ApplicationBase
from qgitc.diffview import PatchViewer
from qgitc.events import (
    RequestCommitEvent,
    ShowAiAssistantEvent,
    ShowBranchCompareEvent,
    ShowPickBranchEvent,
)
from qgitc.findwidget import FindWidget
from qgitc.gitutils import Git
from qgitc.gitview import GitView
from qgitc.llm import AiModelBase, AiParameters, AiResponse
from qgitc.llmprovider import AiModelProvider
from qgitc.logview import LogView
from qgitc.preferences import Preferences
from qgitc.statewindow import StateWindow
from qgitc.ui_mainwindow import Ui_MainWindow

GIT_LOG_SYSTEM_PROMPT = """You are a Git expert assistant. Convert natural language requests into git log command-line options.

Rules:
1. Return ONLY the git log options (flags and arguments), no explanations
2. Use standard git log options like --since, --until, --author, --grep, -n, --oneline, etc.
3. For date/time queries, use --since and --until with formats like '1 week ago', '2022-01-01', etc.
4. For limiting results, use -n <number> or --max-count=<number>
5. For author searches, use --author=<name>
6. For commit message searches, use --grep=<pattern>
7. For file filtering, use -- <filepath> at the end
8. If the request is unclear, return the most reasonable interpretation
9. If the option contains a space, wrap it in quotes

Current date: {current_date}
Current author: {current_author}

Examples:
- "show last 10 commits" → "-n 10"
- "commits from last week" → "--since='1 week ago'"
- "commits by John" → "--author=John"
- "commits about bug fixes" → "--grep=bug"
- "commits since January" → "--since='2025-09-13'"
- "last 5 commits with changes to main.py" → "-n 5 -- main.py"
- "my commits" → "--author='{current_author}'"

User query: {query}

Git log options:"""


class MainWindow(StateWindow):
    LogMode = 1
    CompareMode = 2
    MergeMode = 3

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.resize(QSize(800, 600))

        self.gitViewB = None

        self.isWindowReady = False

        self.mergeWidget = None

        self._delayTimer = QTimer(self)
        self._delayTimer.setSingleShot(True)

        self._repoTopDir = None
        self._reloadingRepo = False

        self._aiModel: AiModelBase = None

        self.ui.cbSubmodule.setVisible(False)
        self.ui.lbSubmodule.setVisible(False)

        self.ui.cbSubmodule.setInsertPolicy(QComboBox.NoInsert)
        self.ui.cbSubmodule.setEditable(True)

        self.ui.cbSubmodule.completer().setFilterMode(Qt.MatchContains)
        self.ui.cbSubmodule.completer().setCompletionMode(
            QCompleter.PopupCompletion)
        self.ui.cbSubmodule.installEventFilter(self)

        self.__setupSignals()
        self.__setupMenus()

    def __setupSignals(self):
        self.ui.acReload.triggered.connect(self.reloadRepo)
        self.ui.acQuit.triggered.connect(self.close)

        self.ui.acPreferences.triggered.connect(
            self.__onAcPreferencesTriggered)

        self.ui.btnRepoBrowse.clicked.connect(self.__onBtnRepoBrowseClicked)

        self.ui.leRepo.textChanged.connect(self.__onDelayRepoChanged)

        self.ui.acIgnoreNone.triggered.connect(
            self.__onAcIgnoreNoneTriggered)
        self.ui.acIgnoreEOL.triggered.connect(
            self.__onAcIgnoreEOLTriggered)
        self.ui.acIgnoreAll.triggered.connect(
            self.__onAcIgnoreAllTriggered)

        self.ui.acCompare.triggered.connect(
            self.__onAcCompareTriggered)

        self.ui.acCopy.triggered.connect(
            self.__onCopyTriggered)
        self.ui.acCopyPlainText.triggered.connect(
            self.__onCopyPlainTextTriggered)

        self.ui.acCopyLog.triggered.connect(
            self.__onCopyLogTriggered)
        self.ui.acCopyLogA.triggered.connect(
            self.__onCopyLogATriggered)
        self.ui.acCopyLogB.triggered.connect(
            self.__onCopyLogBTriggered)

        self.ui.acSelectAll.triggered.connect(
            self.__onSelectAllTriggered)

        self.ui.acFind.triggered.connect(
            self.__onFindTriggered)

        self.ui.acFindNext.triggered.connect(
            self.__onFindNextTriggered)

        self.ui.acFindPrevious.triggered.connect(
            self.__onFindPreviousTriggered)

        self.ui.menu_Edit.aboutToShow.connect(
            self.__updateEditMenu)

        self.ui.acVisualizeWhitespace.triggered.connect(
            self.__onAcVisualizeWhitespaceTriggered)

        self.ui.acFullCommitMsg.triggered.connect(
            self.__onAcFullCommitMsgTriggered)

        self.ui.acCompositeMode.triggered.connect(
            self.__onAcCompositeModeTriggered)

        self.ui.leOpts.returnPressed.connect(
            self.__onOptsReturnPressed)

        self.ui.acAbout.triggered.connect(
            self.__onAboutTriggered)

        self.ui.acAboutQt.triggered.connect(
            ApplicationBase.instance().aboutQt)

        # settings
        sett = ApplicationBase.instance().settings()

        sett.ignoreWhitespaceChanged.connect(
            self.__onIgnoreWhitespaceChanged)

        sett.showWhitespaceChanged.connect(
            self.ui.acVisualizeWhitespace.setChecked)

        # application
        app = ApplicationBase.instance()
        app.focusChanged.connect(self.__updateEditMenu)
        app.submoduleAvailable.connect(self._onSubmoduleAvailable)

        submodules = app.submodules
        if submodules:
            self._onSubmoduleAvailable(submodules, True)

        self.ui.cbSubmodule.currentIndexChanged.connect(
            self.__onSubmoduleChanged)

        self._delayTimer.timeout.connect(
            self.__onDelayTimeout)

        self.ui.cbSelfCommits.stateChanged.connect(
            self.__onSelfCommitsStateChanged)

        self.ui.acCommit.triggered.connect(
            self.__onCommitTriggered)
        self.ui.acBranchCompare.triggered.connect(
            self._onBranchCompareTriggered)
        self.ui.acBranchPick.triggered.connect(
            self._onPickBranchTriggered)

        self.ui.acShowAIAssistant.triggered.connect(
            self._onShowAiAssistant)
        self.ui.acCodeReview.triggered.connect(
            self._onCodeReview)
        self.ui.acChangeCommitAuthor.triggered.connect(
            self._onChangeCommitAuthor)

    def __setupMenus(self):
        acGroup = QActionGroup(self)
        acGroup.addAction(self.ui.acIgnoreNone)
        acGroup.addAction(self.ui.acIgnoreEOL)
        acGroup.addAction(self.ui.acIgnoreAll)
        self.ui.menu_Merge.menuAction().setVisible(False)

    def __updateEditMenu(self):
        fw = ApplicationBase.instance().focusWidget()

        self.ui.acCopy.setEnabled(False)
        self.ui.acSelectAll.setEnabled(False)
        self.ui.acFind.setEnabled(False)
        self.ui.acFindNext.setEnabled(False)
        self.ui.acFindPrevious.setEnabled(False)
        enabled = self.mergeWidget is not None and self.mergeWidget.isResolving()
        self.ui.acCopyLog.setEnabled(False)
        self.ui.acCopyLogA.setEnabled(enabled)
        self.ui.acCopyLogB.setEnabled(enabled)
        self.ui.acCopyPlainText.setVisible(False)
        self.ui.acCopyPlainText.setEnabled(False)

        if not fw:
            pass
        elif isinstance(fw, PatchViewer):
            self.ui.acCopy.setEnabled(fw.hasSelection())
            self.ui.acSelectAll.setEnabled(True)
            self.ui.acFind.setEnabled(True)
            self.ui.acFindNext.setEnabled(fw.canFindNext())
            self.ui.acFindPrevious.setEnabled(fw.canFindPrevious())
            self.ui.acCopyPlainText.setVisible(True)
            self.ui.acCopyPlainText.setEnabled(fw.hasSelection())
        elif isinstance(fw, QLineEdit):
            self.ui.acCopy.setEnabled(fw.hasSelectedText())
            self.ui.acSelectAll.setEnabled(True)
            self.ui.acFind.setEnabled(False)
            if isinstance(fw.parentWidget(), FindWidget):
                self.ui.acFindNext.setEnabled(fw.parentWidget().canFindNext())
                self.ui.acFindPrevious.setEnabled(
                    fw.parentWidget().canFindPrevious())
        elif isinstance(fw, LogView):
            self.ui.acCopy.setEnabled(fw.isCurrentCommitted())
            self.ui.acCopyLog.setEnabled(enabled)
        elif isinstance(fw, FindWidget):
            self.ui.acFindNext.setEnabled(fw.canFindNext())
            self.ui.acFindPrevious.setEnabled(fw.canFindPrevious())

    def __onBtnRepoBrowseClicked(self, checked):
        repoDir = QFileDialog.getExistingDirectory(self,
                                                   self.tr(
                                                       "Choose repository directory"),
                                                   "",
                                                   QFileDialog.ShowDirsOnly)
        if not repoDir:
            return

        repoDir = Git.repoTopLevelDir(repoDir)
        if not repoDir:
            QMessageBox.critical(self, self.windowTitle(),
                                 self.tr("The directory you choosen is not a git repository!"))
            return

        self.ui.leRepo.setText(repoDir)
        self._updateRecentRepos(repoDir)

    def __onRepoChanged(self, repoDir):
        def _clearSubmodules():
            self.ui.cbSubmodule.clear()
            self.ui.cbSubmodule.setVisible(False)
            self.ui.lbSubmodule.setVisible(False)

        if not Git.available():
            _clearSubmodules()
            return

        app = ApplicationBase.instance()
        isCompositeMode = app.settings().isCompositeMode()

        span = app.telemetry().startTrace("reloadRepo")
        span.addTag("compositeMode", isCompositeMode)

        topLevelDir = Git.repoTopLevelDir(repoDir)
        if not topLevelDir:
            msg = self.tr("'{0}' is not a git repository")
            self.ui.statusbar.showMessage(
                msg.format(repoDir),
                5000)  # 5 seconds
            # let gitview clear the old branches
            repoDir = None
            # clear
            app.updateRepoDir(None)
            self._repoTopDir = None
            if Git.REF_MAP:
                Git.REF_MAP.clear()
            Git.REV_HEAD = None
        else:
            changed = app.updateRepoDir(topLevelDir)
            self._repoTopDir = topLevelDir
            self._updateRecentRepos(topLevelDir)

            compositeModeEnabled = isCompositeMode and (
                changed or len(app.submodules) > 0)
            if not compositeModeEnabled:
                if changed or not Git.REF_MAP:
                    Git.REF_MAP = Git.refs()
                    Git.REV_HEAD = Git.revHead()
            elif changed:
                Git.REF_MAP = {}
                Git.REV_HEAD = None

        self.cancel()

        branch = Git.mergeBranchName() if self.mergeWidget else None
        if branch and branch.startswith("origin/"):
            branch = "remotes/" + branch

        span.addEvent("reloadBranches.begin")
        self.ui.gitViewA.reloadBranches(self.ui.gitViewA.currentBranch())
        if self.gitViewB:
            self.gitViewB.reloadBranches(
                branch or self.gitViewB.currentBranch())
        span.addEvent("reloadBranches.end")

        if self.mergeWidget:
            # cache in case changed later
            self.mergeWidget.setBranches(
                self.ui.gitViewA.currentBranch(),
                self.gitViewB.currentBranch())

        span.end()

    def __onAcPreferencesTriggered(self):
        settings = ApplicationBase.instance().settings()
        preferences = Preferences(settings, self)
        preferences.exec()

    def __onIgnoreWhitespaceChanged(self, index):
        actions = [self.ui.acIgnoreNone,
                   self.ui.acIgnoreEOL,
                   self.ui.acIgnoreAll]
        if index < 0 or index >= len(actions):
            index = 0

        actions[index].setChecked(True)

    def __onAcIgnoreNoneTriggered(self, checked):
        sett = ApplicationBase.instance().settings()
        sett.setIgnoreWhitespace(0)

    def __onAcIgnoreEOLTriggered(self, checked):
        sett = ApplicationBase.instance().settings()
        sett.setIgnoreWhitespace(1)

    def __onAcIgnoreAllTriggered(self, checked):
        sett = ApplicationBase.instance().settings()
        sett.setIgnoreWhitespace(2)

    def __onAcVisualizeWhitespaceTriggered(self, checked):
        sett = ApplicationBase.instance().settings()
        sett.setShowWhitespace(checked)

    def __onAcCompareTriggered(self, checked):
        if checked:
            self.setMode(MainWindow.CompareMode)
        else:
            self.setMode(MainWindow.LogMode)

    def __onAcFullCommitMsgTriggered(self, checked):
        ApplicationBase.instance().settings().setFullCommitMessage(checked)
        self.ui.gitViewA.logView.updateView()
        if self.gitViewB:
            self.gitViewB.logView.updateView()

    def __onAcCompositeModeTriggered(self, checked):
        if checked:
            # use top level repo dir
            ApplicationBase.instance().updateRepoDir(self._repoTopDir, False)
        elif self.ui.cbSubmodule.count() > 0 and self.ui.cbSubmodule.currentIndex() > 0:
            newRepo = os.path.join(
                self._repoTopDir, self.ui.cbSubmodule.currentText())
            ApplicationBase.instance().updateRepoDir(newRepo, False)

        if not checked and not Git.REF_MAP:
            Git.REF_MAP = Git.refs()
            Git.REV_HEAD = Git.revHead()

        self.ui.cbSubmodule.setEnabled(not checked)
        ApplicationBase.instance().settings().setCompositeMode(checked)

    def __onOptsReturnPressed(self):
        opts = self.ui.leOpts.text().strip()

        self._cancelAiFilter()

        # Check if this is an AI query
        if opts.lower().startswith("@ai "):
            self._handleAiFilterQuery(opts)
            return

        # Regular git log filter processing
        self.filterOpts(opts, self.ui.gitViewA)
        self.filterOpts(opts, self.gitViewB)

    def __onCopyTriggered(self):
        fw = ApplicationBase.instance().focusWidget()
        assert fw
        fw.copy()

    def __onCopyPlainTextTriggered(self):
        fw = ApplicationBase.instance().focusWidget()
        assert fw
        fw.copyPlainText()

    def __onCopyLogTriggered(self):
        fw = ApplicationBase.instance().focusWidget()
        assert fw
        fw.copyToLog()

    def __onCopyLogATriggered(self):
        self.ui.gitViewA.logView.copyToLog()

    def __onCopyLogBTriggered(self):
        self.gitViewB.logView.copyToLog()

    def __onSelectAllTriggered(self):
        fw = ApplicationBase.instance().focusWidget()
        assert fw
        fw.selectAll()

    def __onFindTriggered(self):
        fw = ApplicationBase.instance().focusWidget()
        assert fw and isinstance(fw, PatchViewer)
        fw.executeFind()

    def __onFindNextTriggered(self):
        fw = ApplicationBase.instance().focusWidget()
        if isinstance(fw, QLineEdit) and isinstance(fw.parentWidget(), FindWidget):
            fw.parentWidget().findNext()
        else:
            fw.findNext()

    def __onFindPreviousTriggered(self):
        fw = ApplicationBase.instance().focusWidget()
        if isinstance(fw, QLineEdit) and isinstance(fw.parentWidget(), FindWidget):
            fw.parentWidget().findPrevious()
        else:
            fw.findPrevious()

    def __onAboutTriggered(self):
        aboutDlg = AboutDialog(self)
        aboutDlg.exec()

    def __onRequestResolve(self, filePath):
        self.setFilterFile(filePath)

    def __onSubmoduleChanged(self, index):
        if not Git.REPO_DIR or not self._repoTopDir:
            return

        newRepo = self._repoTopDir
        if index > 0:
            newRepo = os.path.join(
                self._repoTopDir, self.ui.cbSubmodule.currentText())
        if os.path.normcase(os.path.normpath(newRepo)) == os.path.normcase(os.path.normpath(Git.REPO_DIR)):
            return

        ApplicationBase.instance().updateRepoDir(newRepo, False)
        self.ui.gitViewA.reloadBranches(
            self.ui.gitViewA.currentBranch())
        if self.gitViewB:
            self.gitViewB.reloadBranches(
                self.gitViewB.currentBranch())

    def _onSubmoduleAvailable(self, submodules: List[str], fromCache: bool):
        self.ui.cbSubmodule.blockSignals(True)
        if fromCache:
            self.ui.cbSubmodule.clear()

        for submodule in submodules:
            self.ui.cbSubmodule.addItem(submodule)
        index = self.ui.cbSubmodule.findText(".")
        if index > 0:
            self.ui.cbSubmodule.removeItem(index)
            self.ui.cbSubmodule.insertItem(0, ".")
            self.ui.cbSubmodule.setCurrentIndex(0)
        self.ui.cbSubmodule.blockSignals(False)

        hasSubmodule = self.ui.cbSubmodule.count() > 0
        self.ui.cbSubmodule.setVisible(hasSubmodule)
        self.ui.lbSubmodule.setVisible(hasSubmodule)

        settings = ApplicationBase.instance().settings()
        if settings.isCompositeMode() and not hasSubmodule and not Git.REF_MAP:
            Git.REF_MAP = Git.refs()
            Git.REV_HEAD = Git.revHead()
            self.ui.gitViewA.logView.update()
            if self.gitViewB:
                self.gitViewB.logView.update()

    def __onDelayTimeout(self):
        repoDir = self.ui.leRepo.text()
        self.__onRepoChanged(repoDir)

    def __onDelayRepoChanged(self, text):
        self._delayTimer.start(500)

    def saveState(self):
        sett = ApplicationBase.instance().settings()
        if not sett.rememberWindowState():
            return False

        super().saveState()

        self.ui.gitViewA.saveState(sett, True)
        if self.gitViewB:
            self.gitViewB.saveState(sett, False)

        return True

    def restoreState(self):
        sett = ApplicationBase.instance().settings()
        if not sett.rememberWindowState():
            return False

        super().restoreState()

        self.ui.gitViewA.restoreState(sett, True)
        if self.gitViewB:
            self.gitViewB.restoreState(sett, False)

        self.__onIgnoreWhitespaceChanged(sett.ignoreWhitespace())
        self.ui.acVisualizeWhitespace.setChecked(
            sett.showWhitespace())

        self.ui.acFullCommitMsg.setChecked(
            sett.isFullCommitMessage())

        isCompositeMode = sett.isCompositeMode()
        self.ui.acCompositeMode.setChecked(isCompositeMode)
        self.ui.cbSubmodule.setEnabled(not isCompositeMode)

        return True

    def filterOpts(self, opts: str, gitView: GitView):
        if not gitView:
            return

        args = shlex.split(self._fixSeparator(opts), posix=True)
        if self.ui.cbSelfCommits.isChecked():
            args.insert(0, f"--author={Git.userName()}")
        gitView.filterLog(args)

    @staticmethod
    def _fixSeparator(opts: str):
        if os.name == "nt":
            return opts.replace("\\", "\\\\")
        return opts

    def showMessage(self, msg, timeout=5000):
        self.ui.statusbar.showMessage(msg, timeout)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.closeFindWidget():
                if ApplicationBase.instance().lastFocusWidget():
                    ApplicationBase.instance().lastFocusWidget().setFocus()
                return

        super().keyPressEvent(event)

    def showEvent(self, event):
        super(MainWindow, self).showEvent(event)
        if not self.isWindowReady:
            self.isWindowReady = True
            if Git.REPO_DIR:
                self.ui.leRepo.setText(Git.REPO_DIR)
            self._setupRepoPathInput()

    def closeEvent(self, event):
        if self.mergeWidget:
            if not self.mergeWidget.queryClose():
                return
            self.mergeWidget.close()

        self.ui.gitViewA.queryClose()
        if self.gitViewB is not None:
            self.gitViewB.queryClose()

        self.cancel(True)
        super().closeEvent(event)

    def setFilterFile(self, filePath):
        if filePath and not filePath.startswith("-- "):
            self.ui.leOpts.setText("-- " + filePath)
        else:
            self.ui.leOpts.setText(filePath)
        self.__onOptsReturnPressed()

    def setFilterOptions(self, options: str):
        self.ui.leOpts.setText(options)
        self.__onOptsReturnPressed()

    def getFilterArgs(self):
        text = self.ui.leOpts.text().strip()
        args = shlex.split(text, posix=sys.platform != "win32")
        return args

    def setMode(self, mode):
        hasMergeMenu = False
        if mode == MainWindow.LogMode:
            self.ui.gitViewA.setBranchDesc(self.tr("Branch"))

            if self.gitViewB:
                self.gitViewB.deleteLater()
                self.gitViewB = None

            self.ui.acCompare.setChecked(False)
        elif mode == MainWindow.CompareMode:
            self.gitViewB = GitView(self)
            self.ui.splitter.addWidget(self.gitViewB)

            self.ui.gitViewA.setBranchDesc(self.tr("Branch A:"))
            self.gitViewB.setBranchDesc(self.tr("Branch B:"))
            self.gitViewB.setBranchB()

            opts = self.ui.leOpts.text().strip()
            if opts:
                self.filterOpts(opts, self.gitViewB)

            branch = self.ui.gitViewA.currentBranch()
            if branch.startswith("remotes/origin/"):
                branch = branch[15:]
            elif branch:
                branch = "remotes/origin/" + branch

            if not self.mergeWidget:
                self.gitViewB.reloadBranches(branch)
            self.ui.acCompare.setChecked(True)
        elif mode == MainWindow.MergeMode:
            from qgitc.mergewidget import MergeWidget
            self.mergeWidget = MergeWidget()
            self.mergeWidget.requestResolve.connect(
                self.__onRequestResolve)

            # delay a while to let it show front to mainwindow
            QTimer.singleShot(0, self.mergeWidget.show)
            if not self.gitViewB:
                self.setMode(MainWindow.CompareMode)
            # not allowed changed in this mode
            self.ui.leRepo.setReadOnly(True)
            self.ui.acCompare.setEnabled(False)
            self.ui.btnRepoBrowse.setEnabled(False)
            hasMergeMenu = True
        self.ui.menu_Merge.menuAction().setVisible(hasMergeMenu)

    def showCommit(self, sha1):
        if not sha1:
            return

        # Ugly code
        self.ui.gitViewA.ui.logView.switchToCommit(sha1, True)
        if self.gitViewB:
            self.gitViewB.ui.logView.switchToCommit(sha1, True)

    def reloadRepo(self):
        if self._reloadingRepo:
            return
        self._reloadingRepo = True
        try:
            repoDir = self.ui.leRepo.text()
            self.__onRepoChanged(repoDir)
        finally:
            self._reloadingRepo = False

    def closeFindWidget(self):
        if self.ui.gitViewA.closeFindWidget():
            return True
        if self.gitViewB and self.gitViewB.closeFindWidget():
            return True

        return False

    def __onSelfCommitsStateChanged(self, state):
        self.__onOptsReturnPressed()

    def eventFilter(self, obj, event):
        if obj == self.ui.cbSubmodule:
            if event.type() == QEvent.FocusIn and event.reason() == Qt.MouseFocusReason:
                QTimer.singleShot(150, obj.showPopup)
        return super().eventFilter(obj, event)

    def __onCommitTriggered(self):
        # we can't import application here, because it will cause circular import
        app = ApplicationBase.instance()
        app.postEvent(app, RequestCommitEvent())
        app.trackFeatureUsage("menu.commit")

    def reloadLocalChanges(self):
        self.ui.gitViewA.ui.logView.reloadLogs()
        if self.gitViewB:
            self.gitViewB.ui.logView.reloadLogs()

    def _onShowAiAssistant(self):
        ApplicationBase.instance().postEvent(
            ApplicationBase.instance(), ShowAiAssistantEvent())

    def cancel(self, force=False):
        self._delayTimer.stop()

        # Cancel AI processing if active
        if self._aiModel and self._aiModel.isRunning():
            self._aiModel.responseAvailable.disconnect(
                self._onAiFilterResponse)
            self._aiModel.serviceUnavailable.disconnect(
                self._onAiServiceUnavailable)
            self._aiModel.finished.disconnect(self._onAiFilterFinished)
            self._aiModel.requestInterruption()
            self._aiModel = None

    def _handleAiFilterQuery(self, query: str):
        """Handle AI query for git log filtering"""
        self.showMessage(self.tr("Processing AI query..."))

        # remove @ai prefix
        aiQuery = query[3:].strip()

        self._aiModel = AiModelProvider.createModel(self)
        self._aiModel.responseAvailable.connect(self._onAiFilterResponse)
        self._aiModel.serviceUnavailable.connect(self._onAiServiceUnavailable)
        self._aiModel.finished.connect(self._onAiFilterFinished)

        params = AiParameters()
        params.sys_prompt = GIT_LOG_SYSTEM_PROMPT.format(
            current_date=datetime.now().strftime("%Y-%m-%d"),
            current_author=Git.userName(),
            query=aiQuery)
        params.prompt = aiQuery
        params.temperature = 0.1
        params.max_tokens = 512
        params.stream = False

        self._aiModel.queryAsync(params)

        ApplicationBase.instance().trackFeatureUsage("ai_log_filter")

    def _onAiFilterResponse(self, response: AiResponse):
        """Handle AI response for filter options"""
        if response.message:
            # Clean up the response
            filterOptions = response.message.strip()

            # Remove any markdown formatting
            if filterOptions.startswith("```"):
                lines = filterOptions.split('\n')
                filterOptions = '\n'.join(
                    lines[1:-1] if len(lines) > 2 else lines[1:])

            filterOptions = filterOptions.strip()

            # Apply the AI-generated filter options
            if filterOptions:
                leOpts = self.ui.leOpts
                leOpts.selectAll()
                leOpts.insert(filterOptions)
                self.filterOpts(filterOptions, self.ui.gitViewA)
                self.filterOpts(filterOptions, self.gitViewB)
                self.showMessage(
                    self.tr("Applied AI-generated filter: {0}").format(filterOptions))
            else:
                self.showMessage(
                    self.tr("AI could not generate valid filter options"))

    def _onAiServiceUnavailable(self):
        QMessageBox.warning(
            self, self.windowTitle(),
            self.tr("AI service is currently unavailable. Please check your settings or try again later."))

    def _onAiFilterFinished(self):
        self._aiModel = None

    def _cancelAiFilter(self):
        """Cancel any ongoing AI filter processing"""
        if self._aiModel:
            self._aiModel.responseAvailable.disconnect(
                self._onAiFilterResponse)
            self._aiModel.serviceUnavailable.disconnect(
                self._onAiServiceUnavailable)
            self._aiModel.finished.disconnect(self._onAiFilterFinished)
            self._aiModel.requestInterruption()
            self._aiModel = None

    def _setupRepoPathInput(self):
        # Load recent repositories from settings
        settings = ApplicationBase.instance().settings()
        recentRepos = settings.recentRepositories()
        self.ui.leRepo.setRecentRepositories(recentRepos)
        self.ui.leRepo.repositorySelected.connect(self._onRepoSelected)

    def _onRepoSelected(self, repoPath: str):
        """Handle repository selection from completion"""
        self._updateRecentRepos(repoPath)

    def _updateRecentRepos(self, repo: str):
        settings = ApplicationBase.instance().settings()
        settings.addRecentRepository(repo)
        recentRepos = settings.recentRepositories()
        for repo in recentRepos[:]:
            if not os.path.exists(repo) or not os.path.isdir(repo):
                recentRepos.remove(repo)
        settings.setRecentRepositories(recentRepos)
        self.ui.leRepo.setRecentRepositories(recentRepos)

    def _onCodeReview(self):
        app = ApplicationBase.instance()
        fw = app.focusWidget()
        if isinstance(fw, LogView):
            fw.codeReviewOnCurrent()
        else:
            self.ui.gitViewA.logView.codeReviewOnCurrent()

        app.trackFeatureUsage("menu.code_review")

    def _onChangeCommitAuthor(self):
        """Handle changing commit author from Git menu"""
        gitView = self.ui.gitViewA
        if not gitView:
            return

        logView = gitView.ui.logView
        if not logView:
            return

        curIdx = logView.currentIndex()
        if curIdx == -1:
            QMessageBox.information(
                self, self.windowTitle(),
                self.tr("Please select a commit first."))
            return

        logView.changeAuthor()

    def _onBranchCompareTriggered(self):
        targetBranch = None
        baseBranch = None

        if self.gitViewB:
            targetBranch = self.gitViewB.currentBranch()
            baseBranch = self.ui.gitViewA.currentBranch()
        else:
            targetBranch = self.ui.gitViewA.currentBranch()

        app = ApplicationBase.instance()
        app.postEvent(app, ShowBranchCompareEvent(targetBranch, baseBranch))
        app.trackFeatureUsage("menu.branch_compare")

    def _onPickBranchTriggered(self):
        """Handle pick branch menu action"""
        # Get current branch as target (where commits will be picked to)
        if self.gitViewB:
            targetBranch = self.ui.gitViewA.currentBranch()
            sourceBranch = self.gitViewB.currentBranch()
        else:
            targetBranch = self.ui.gitViewA.currentBranch()
            sourceBranch = None

        app = ApplicationBase.instance()
        app.postEvent(app, ShowPickBranchEvent(sourceBranch, targetBranch))
        app.trackFeatureUsage("menu.pick_branch")
