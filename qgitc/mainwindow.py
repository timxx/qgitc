# -*- coding: utf-8 -*-

import os
import shlex
import sys

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QIcon
from PySide6.QtWidgets import QComboBox, QCompleter, QFileDialog, QLineEdit, QMessageBox

from qgitc.aboutdialog import AboutDialog
from qgitc.applicationbase import ApplicationBase
from qgitc.coloredicontoolbutton import ColoredIconToolButton
from qgitc.common import dataDirPath, logger
from qgitc.diffview import PatchViewer
from qgitc.events import RequestCommitEvent, ShowAiAssistantEvent
from qgitc.findsubmodules import FindSubmoduleThread
from qgitc.findwidget import FindWidget
from qgitc.gitutils import Git
from qgitc.gitview import GitView
from qgitc.logview import LogView
from qgitc.preferences import Preferences
from qgitc.statewindow import StateWindow
from qgitc.ui_mainwindow import Ui_MainWindow


class MainWindow(StateWindow):
    LogMode = 1
    CompareMode = 2
    MergeMode = 3

    submoduleAvailable = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.resize(QSize(800, 600))

        self.gitViewB = None

        self.isWindowReady = False
        self.findSubmoduleThread = None
        self._threads = []

        self.mergeWidget = None

        self._delayTimer = QTimer(self)
        self._delayTimer.setSingleShot(True)

        self._repoTopDir = None

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

        icon = QIcon(dataDirPath() + "/icons/assistant.svg")
        assistantButton = ColoredIconToolButton(icon, QSize(16, 16), self)
        assistantButton.setIcon(icon)
        assistantButton.clicked.connect(
            self._onShowAiAssistant)
        assistantButton.setToolTip(self.tr("Show AI Assistant"))

        self.statusBar().addPermanentWidget(assistantButton)

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
        ApplicationBase.instance().focusChanged.connect(self.__updateEditMenu)

        self.ui.cbSubmodule.currentIndexChanged.connect(
            self.__onSubmoduleChanged)

        self._delayTimer.timeout.connect(
            self.__onDelayTimeout)

        self.ui.cbSelfCommits.stateChanged.connect(
            self.__onSelfCommitsStateChanged)

        self.ui.acCommit.triggered.connect(
            self.__onCommitTriggered)

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

    def __onRepoChanged(self, repoDir):
        self.ui.cbSubmodule.clear()
        self.ui.cbSubmodule.setVisible(False)
        self.ui.lbSubmodule.setVisible(False)

        if not Git.available():
            return

        topLevelDir = Git.repoTopLevelDir(repoDir)
        if not topLevelDir:
            msg = self.tr("'{0}' is not a git repository")
            self.ui.statusbar.showMessage(
                msg.format(repoDir),
                5000)  # 5 seconds
            # let gitview clear the old branches
            repoDir = None
            # clear
            ApplicationBase.instance().updateRepoDir(None)
            self._repoTopDir = None
            if Git.REF_MAP:
                Git.REF_MAP.clear()
            Git.REV_HEAD = None
        else:
            ApplicationBase.instance().updateRepoDir(topLevelDir)
            self._repoTopDir = topLevelDir
            Git.REF_MAP = Git.refs()
            Git.REV_HEAD = Git.revHead()

        self.cancel()
        if repoDir:
            self.ui.leRepo.setReadOnly(True)
            self.ui.btnRepoBrowse.setDisabled(True)
            self.findSubmoduleThread = FindSubmoduleThread(topLevelDir, self)
            self.findSubmoduleThread.finished.connect(
                self.__onFindSubmoduleFinished)
            self.findSubmoduleThread.finished.connect(
                self.__onThreadFinished)
            self._threads.append(self.findSubmoduleThread)
            self.findSubmoduleThread.start()

            self.initSubmodulesFromCache()

        branch = Git.mergeBranchName() if self.mergeWidget else None
        if branch and branch.startswith("origin/"):
            branch = "remotes/" + branch
        self.ui.gitViewA.reloadBranches(self.ui.gitViewA.currentBranch())
        if self.gitViewB:
            self.gitViewB.reloadBranches(
                branch or self.gitViewB.currentBranch())

        if self.mergeWidget:
            # cache in case changed later
            self.mergeWidget.setBranches(
                self.ui.gitViewA.currentBranch(),
                self.gitViewB.currentBranch())

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
            ApplicationBase.instance().updateRepoDir(self._repoTopDir)
        elif self.ui.cbSubmodule.count() > 0 and self.ui.cbSubmodule.currentIndex() > 0:
            newRepo = os.path.join(
                self._repoTopDir, self.ui.cbSubmodule.currentText())
            ApplicationBase.instance().updateRepoDir(newRepo)

        self.ui.cbSubmodule.setEnabled(not checked)
        ApplicationBase.instance().settings().setCompositeMode(checked)

    def __onOptsReturnPressed(self):
        opts = self.ui.leOpts.text().strip()
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
        newRepo = self._repoTopDir
        if index > 0:
            newRepo = os.path.join(
                self._repoTopDir, self.ui.cbSubmodule.currentText())
        if os.path.normcase(os.path.normpath(newRepo)) == os.path.normcase(os.path.normpath(Git.REPO_DIR)):
            return

        ApplicationBase.instance().updateRepoDir(newRepo)
        self.ui.gitViewA.reloadBranches(
            self.ui.gitViewA.currentBranch())
        if self.gitViewB:
            self.gitViewB.reloadBranches(
                self.gitViewB.currentBranch())

    def __onFindSubmoduleFinished(self):
        submodules = self.findSubmoduleThread.submodules

        # check if the cache is reusable
        caches = []
        for i in range(self.ui.cbSubmodule.count()):
            caches.append(self.ui.cbSubmodule.itemText(i))

        isCacheValid = len(submodules) == len(caches)
        if isCacheValid:
            for i in range(len(submodules)):
                if submodules[i] not in caches:
                    isCacheValid = False
                    break

        if not isCacheValid:
            self.ui.cbSubmodule.clear()
            for submodule in submodules:
                self.ui.cbSubmodule.addItem(submodule)

        if not self.mergeWidget:
            self.ui.leRepo.setReadOnly(False)
            self.ui.btnRepoBrowse.setEnabled(True)
        hasSubmodule = len(submodules) > 0
        self.ui.cbSubmodule.setVisible(hasSubmodule)
        self.ui.lbSubmodule.setVisible(hasSubmodule)
        if not isCacheValid and submodules:
            self.submoduleAvailable.emit(False)

        ApplicationBase.instance().settings().setSubmodulesCache(Git.REPO_DIR, submodules)

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

    def filterOpts(self, opts, gitView):
        if not gitView:
            return

        # don't knonw if cygwin works or not
        args = shlex.split(opts, posix=sys.platform != "win32")
        if self.ui.cbSelfCommits.isChecked():
            args.insert(0, f"--author={Git.userName()}")
        gitView.filterLog(args)

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
        repoDir = self.ui.leRepo.text()
        self.__onRepoChanged(repoDir)

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

    def submodules(self):
        if not self.ui.cbSubmodule.isVisible():
            return []

        submodules = []
        count = self.ui.cbSubmodule.count()
        for i in range(count):
            submodules.append(self.ui.cbSubmodule.itemText(i))

        return submodules

    def initSubmodulesFromCache(self):
        submodules = ApplicationBase.instance().settings().submodulesCache(Git.REPO_DIR)
        if not submodules:
            return

        # first, check if cache is valid
        for submodule in submodules:
            if not os.path.exists(os.path.join(Git.REPO_DIR, submodule)):
                ApplicationBase.instance().settings().setSubmodulesCache(Git.REPO_DIR, [])
                return

        for submodule in submodules:
            self.ui.cbSubmodule.addItem(submodule)

        self.ui.cbSubmodule.setVisible(True)
        self.ui.lbSubmodule.setVisible(True)
        self.submoduleAvailable.emit(True)

    def __onCommitTriggered(self):
        # we can't import application here, because it will cause circular import
        ApplicationBase.instance().postEvent(
            ApplicationBase.instance(), RequestCommitEvent())

    def reloadLocalChanges(self):
        self.ui.gitViewA.ui.logView.reloadLogs()
        if self.gitViewB:
            self.gitViewB.ui.logView.reloadLogs()

    def _onShowAiAssistant(self):
        ApplicationBase.instance().postEvent(
            ApplicationBase.instance(), ShowAiAssistantEvent())

    def cancel(self, force=False):
        self._delayTimer.stop()

        if self.findSubmoduleThread and self.findSubmoduleThread.isRunning():
            self.findSubmoduleThread.finished.disconnect(
                self.__onFindSubmoduleFinished)
            self.findSubmoduleThread.requestInterruption()
            if force and ApplicationBase.instance().terminateThread(self.findSubmoduleThread):
                self._threads.remove(self.findSubmoduleThread)
                self.findSubmoduleThread.finished.disconnect(self.__onThreadFinished)
                logger.warning("Terminating find submodule thread")
            self.findSubmoduleThread = None

        if not force:
            return

        for thread in self._threads:
            thread.finished.disconnect(self.__onThreadFinished)
            ApplicationBase.instance().terminateThread(thread)
        self._threads.clear()

    def __onThreadFinished(self):
        thread = self.sender()
        if thread in self._threads:
            self._threads.remove(thread)
