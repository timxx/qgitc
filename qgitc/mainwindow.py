# -*- coding: utf-8 -*-

from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QLineEdit,
    QMessageBox,
    QFileDialog,
    QDialog)

from PySide6.QtGui import (
    QActionGroup)

from PySide6.QtCore import (
    QThread,
    QSize,
    QTimer,
    Qt,
    QEvent,
    Signal)

from .findwidget import FindWidget

from .ui_mainwindow import Ui_MainWindow
from .gitview import GitView
from .preferences import Preferences
from .gitutils import Git, GitProcess
from .diffview import PatchViewer
from .aboutdialog import AboutDialog
from .mergewidget import MergeWidget
from .statewindow import StateWindow
from .logview import LogView
from .events import GitBinChanged

import os
import sys
import shlex


class FindSubmoduleThread(QThread):
    def __init__(self, repoDir, parent=None):
        super(FindSubmoduleThread, self).__init__(parent)

        self._repoDir = os.path.normcase(os.path.normpath(repoDir))
        self._submodules = []

    @property
    def submodules(self):
        if self.isFinished() and not self.isInterruptionRequested():
            return self._submodules
        return []

    def run(self):
        self._submodules.clear()
        if self.isInterruptionRequested():
            return

        # try git submodule first
        process = GitProcess(self._repoDir,
                             ["submodule", "foreach", "--quiet", "echo $name"],
                             True)
        data = process.communicate()[0]
        if self.isInterruptionRequested():
            return
        if process.returncode == 0 and data:
            self._submodules = data.rstrip().split('\n')
            self._submodules.insert(0, ".")
            return

        submodules = []
        # some projects may not use submodule or subtree
        max_level = 5 + self._repoDir.count(os.path.sep)
        for root, subdirs, files in os.walk(self._repoDir, topdown=True):
            if self.isInterruptionRequested():
                return
            if os.path.normcase(root) == self._repoDir:
                continue

            if ".git" in subdirs or ".git" in files:
                dir = root.replace(self._repoDir + os.sep, "")
                if dir:
                    submodules.append(dir)

            if root.count(os.path.sep) >= max_level or root.endswith(".git"):
                del subdirs[:]
            else:
                # ignore all '.dir'
                subdirs[:] = [d for d in subdirs if not d.startswith(".")]

        if submodules:
            submodules.insert(0, '.')

        self._submodules = submodules


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

        self.mergeWidget = None

        self._delayTimer = QTimer(self)
        self._delayTimer.setSingleShot(True)

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
            qApp.aboutQt)

        # settings
        sett = qApp.instance().settings()

        sett.ignoreWhitespaceChanged.connect(
            self.__onIgnoreWhitespaceChanged)

        sett.showWhitespaceChanged.connect(
            self.ui.acVisualizeWhitespace.setChecked)

        # application
        qApp.focusChanged.connect(self.__updateEditMenu)

        self.ui.cbSubmodule.currentIndexChanged.connect(self.__onSubmoduleChanged)

        self._delayTimer.timeout.connect(
            self.__onDelayTimeout)

        self.ui.cbSelfCommits.stateChanged.connect(self.__onSelfCommitsStateChanged)

    def __setupMenus(self):
        acGroup = QActionGroup(self)
        acGroup.addAction(self.ui.acIgnoreNone)
        acGroup.addAction(self.ui.acIgnoreEOL)
        acGroup.addAction(self.ui.acIgnoreAll)
        self.ui.menu_Merge.menuAction().setVisible(False)

    def __updateEditMenu(self):
        fw = qApp.focusWidget()

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
                self.ui.acFindPrevious.setEnabled(fw.parentWidget().canFindPrevious())
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
            Git.REPO_DIR = None
            Git.REPO_TOP_DIR = None
            if Git.REF_MAP:
                Git.REF_MAP.clear()
            Git.REV_HEAD = None
        else:
            Git.REPO_DIR = topLevelDir
            Git.REPO_TOP_DIR = topLevelDir
            Git.REF_MAP = Git.refs()
            Git.REV_HEAD = Git.revHead()

        if self.findSubmoduleThread and self.findSubmoduleThread.isRunning():
            self.findSubmoduleThread.disconnect(self)
            self.findSubmoduleThread.requestInterruption()
            self.findSubmoduleThread.wait()

        if repoDir:
            self.ui.leRepo.setReadOnly(True)
            self.ui.btnRepoBrowse.setDisabled(True)
            self.findSubmoduleThread = FindSubmoduleThread(topLevelDir, self)
            self.findSubmoduleThread.finished.connect(
                self.__onFindSubmoduleFinished)
            self.findSubmoduleThread.start()

            self.initSubmodulesFromCache()

        branch = Git.mergeBranchName() if self.mergeWidget else None
        if branch and branch.startswith("origin/"):
            branch = "remotes/" + branch
        self.ui.gitViewA.reloadBranches( self.ui.gitViewA.currentBranch())
        if self.gitViewB:
            self.gitViewB.reloadBranches(branch or self.gitViewB.currentBranch())

        if self.mergeWidget:
            # cache in case changed later
            self.mergeWidget.setBranches(
                self.ui.gitViewA.currentBranch(),
                self.gitViewB.currentBranch())

    def __onAcPreferencesTriggered(self):
        settings = qApp.instance().settings()
        preferences = Preferences(settings, self)
        if preferences.exec() == QDialog.Accepted:
            preferences.save()
            if settings.gitBinPath() != GitProcess.GIT_BIN:
                qApp.postEvent(qApp, GitBinChanged())

    def __onIgnoreWhitespaceChanged(self, index):
        actions = [self.ui.acIgnoreNone,
                   self.ui.acIgnoreEOL,
                   self.ui.acIgnoreAll]
        if index < 0 or index >= len(actions):
            index = 0

        actions[index].setChecked(True)

    def __onAcIgnoreNoneTriggered(self, checked):
        sett = qApp.instance().settings()
        sett.setIgnoreWhitespace(0)

    def __onAcIgnoreEOLTriggered(self, checked):
        sett = qApp.instance().settings()
        sett.setIgnoreWhitespace(1)

    def __onAcIgnoreAllTriggered(self, checked):
        sett = qApp.instance().settings()
        sett.setIgnoreWhitespace(2)

    def __onAcVisualizeWhitespaceTriggered(self, checked):
        sett = qApp.instance().settings()
        sett.setShowWhitespace(checked)

    def __onAcCompareTriggered(self, checked):
        if checked:
            self.setMode(MainWindow.CompareMode)
        else:
            self.setMode(MainWindow.LogMode)

    def __onAcFullCommitMsgTriggered(self, checked):
        qApp.settings().setFullCommitMessage(checked)
        self.ui.gitViewA.logView.updateView()
        if self.gitViewB:
            self.gitViewB.logView.updateView()

    def __onAcCompositeModeTriggered(self, checked):
        if checked:
            # use top level repo dir
            Git.REPO_DIR = Git.REPO_TOP_DIR
        elif self.ui.cbSubmodule.count() > 0 and self.ui.cbSubmodule.currentIndex() > 0:
            newRepo = os.path.join(
                Git.REPO_TOP_DIR, self.ui.cbSubmodule.currentText())
            Git.REPO_DIR = newRepo

        self.ui.cbSubmodule.setEnabled(not checked)
        qApp.settings().setCompositeMode(checked)

    def __onOptsReturnPressed(self):
        opts = self.ui.leOpts.text().strip()
        self.filterOpts(opts, self.ui.gitViewA)
        self.filterOpts(opts, self.gitViewB)

    def __onCopyTriggered(self):
        fw = qApp.focusWidget()
        assert fw
        fw.copy()

    def __onCopyPlainTextTriggered(self):
        fw = qApp.focusWidget()
        assert fw
        fw.copyPlainText()

    def __onCopyLogTriggered(self):
        fw = qApp.focusWidget()
        assert fw
        fw.copyToLog()

    def __onCopyLogATriggered(self):
        self.ui.gitViewA.logView.copyToLog()

    def __onCopyLogBTriggered(self):
        self.gitViewB.logView.copyToLog()

    def __onSelectAllTriggered(self):
        fw = qApp.focusWidget()
        assert fw
        fw.selectAll()

    def __onFindTriggered(self):
        fw = qApp.focusWidget()
        assert fw and isinstance(fw, PatchViewer)
        fw.executeFind()

    def __onFindNextTriggered(self):
        fw = qApp.focusWidget()
        if isinstance(fw, QLineEdit) and isinstance(fw.parentWidget(), FindWidget):
            fw.parentWidget().findNext()
        else:
            fw.findNext()

    def __onFindPreviousTriggered(self):
        fw = qApp.focusWidget()
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
        newRepo = Git.REPO_TOP_DIR
        if index > 0:
            newRepo = os.path.join(Git.REPO_TOP_DIR, self.ui.cbSubmodule.currentText())
        if os.path.normcase(os.path.normpath(newRepo)) == os.path.normcase(os.path.normpath(Git.REPO_DIR)):
            return

        Git.REPO_DIR = newRepo
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

        qApp.settings().setSubmodulesCache(Git.REPO_DIR, submodules)

    def __onDelayTimeout(self):
        repoDir = self.ui.leRepo.text()
        self.__onRepoChanged(repoDir)

    def __onDelayRepoChanged(self, text):
        self._delayTimer.start(500)

    def saveState(self):
        sett = qApp.instance().settings()
        if not sett.rememberWindowState():
            return False

        super().saveState()

        self.ui.gitViewA.saveState(sett, True)
        if self.gitViewB:
            self.gitViewB.saveState(sett, False)

        return True

    def restoreState(self):
        sett = qApp.instance().settings()
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
                if qApp.lastFocusWidget():
                    qApp.lastFocusWidget().setFocus()
                return
            sett = qApp.instance().settings()
            if sett.quitViaEsc():
                self.close()
                return

        super(MainWindow, self).keyPressEvent(event)

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

        super().closeEvent(event)

    def setFilterFile(self, filePath):
        if filePath and not filePath.startswith("-- "):
            self.ui.leOpts.setText("-- " + filePath)
        else:
            self.ui.leOpts.setText(filePath)
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
        submodules = qApp.settings().submodulesCache(Git.REPO_DIR)
        if not submodules:
            return

        # first, check if cache is valid
        for submodule in submodules:
            if not os.path.exists(os.path.join(Git.REPO_DIR, submodule)):
                qApp.settings().setSubmodulesCache(Git.REPO_DIR, [])
                return

        for submodule in submodules:
            self.ui.cbSubmodule.addItem(submodule)

        self.ui.cbSubmodule.setVisible(True)
        self.ui.lbSubmodule.setVisible(True)
        self.submoduleAvailable.emit(True)
