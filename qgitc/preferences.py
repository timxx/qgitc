# -*- coding: utf-8 -*-

# from PySide6.QtGui import (
# )
from PySide6.QtWidgets import (
    QMessageBox,
    QFileDialog)
from PySide6.QtCore import (
    QSize)

from .colorschema import ColorSchemaMode
from .commitactiontablemodel import CommitActionTableModel
from .ui_preferences import *
from .comboboxitemdelegate import ComboBoxItemDelegate
from .linkeditdialog import LinkEditDialog
from .gitutils import Git, GitProcess
from .tooltablemodel import ToolTableModel

import sys
import os
import subprocess


class Preferences(QDialog):

    def __init__(self, settings, parent=None):
        super(Preferences, self).__init__(parent)

        self.ui = Ui_Preferences()
        self.ui.setupUi(self)
        self.settings = settings

        self.resize(QSize(655, 396))

        model = ToolTableModel(self)
        self.ui.tableView.setModel(model)
        self.ui.tableView.horizontalHeader().setSectionResizeMode(
            ToolTableModel.Col_Tool,
            QHeaderView.Stretch)

        delegate = ComboBoxItemDelegate(model.getSceneNames(), self)
        self.ui.tableView.setItemDelegateForColumn(
            ToolTableModel.Col_Scenes, delegate)

        self.ui.cbFamilyLog.currentFontChanged.connect(
            self._onFamilyChanged)
        self.ui.cbFamilyDiff.currentFontChanged.connect(
            self._onFamilyChanged)

        self.ui.btnAdd.clicked.connect(
            self._onBtnAddClicked)
        self.ui.btnDelete.clicked.connect(
            self._onBtnDeleteClicked)

        self.ui.tableView.model().suffixExists.connect(
            self._onSuffixExists)

        self.ui.btnGlobal.clicked.connect(
            self._onBtnGlobalClicked)

        self.ui.lbConfigImgDiff.linkActivated.connect(
            self._onConfigImgDiff)

        # default to General tab
        self.ui.tabWidget.setCurrentIndex(0)
        self.ui.tabWidget.currentChanged.connect(
            self._onTabChanged)

        self.ui.buttonBox.accepted.connect(
            self._onAccepted)

        self.ui.cbCheckUpdates.toggled.connect(
            self._onCheckUpdatesChanged)

        self.ui.btnChooseGit.clicked.connect(
            self._onBtnChooseGitClicked)

        self.ui.cbCommitSince.addItem(self.tr("All"), 0)
        self.ui.cbCommitSince.addItem(self.tr("1 Year"), 365)
        self.ui.cbCommitSince.addItem(self.tr("2 Years"), 365 * 2)
        self.ui.cbCommitSince.addItem(self.tr("3 Years"), 365 * 3)
        self.ui.cbCommitSince.addItem(self.tr("5 Years"), 365 * 5)

        model = CommitActionTableModel(self)
        self.ui.tvActions.setModel(model)

        delegate = ComboBoxItemDelegate(model.getStatusNames(), self)
        self.ui.tvActions.setItemDelegateForColumn(
            CommitActionTableModel.Col_Status, delegate)

        delegate = ComboBoxItemDelegate(model.getConditionNames(), self)
        self.ui.tvActions.setItemDelegateForColumn(
            CommitActionTableModel.Col_Condition, delegate)

        self.ui.tvActions.horizontalHeader().setSectionResizeMode(
            CommitActionTableModel.Col_Cmd,
            QHeaderView.Stretch)

        self.ui.tvActions.horizontalHeader().resizeSection(
            CommitActionTableModel.Col_Condition,
            120)

        self.ui.btnAddAction.clicked.connect(
            self._onAddActionClicked)
        self.ui.btnDelAction.clicked.connect(
            self._onDeleteActionClicked)

        self._initedTabs = set()
        self._initSettings()

    def _initSettings(self):
        # TODO: delay load config for each tab
        checked = self.settings.checkUpdatesEnabled()
        self.ui.cbCheckUpdates.setChecked(checked)
        self._onCheckUpdatesChanged(checked)

        self.ui.sbDays.setValue(
            self.settings.checkUpdatesInterval())

        font = self.settings.logViewFont()
        self.ui.cbFamilyLog.setCurrentFont(font)
        self.ui.cbFamilyLog.currentFontChanged.emit(font)

        font = self.settings.diffViewFont()
        self.ui.cbFamilyDiff.setCurrentFont(font)
        self.ui.cbFamilyDiff.currentFontChanged.emit(font)

        self.ui.colorA.setColor(self.settings.commitColorA())
        self.ui.colorB.setColor(self.settings.commitColorB())

        repoName = qApp.repoName()
        self.ui.linkEditWidget.setCommitUrl(self.settings.commitUrl(repoName))

        self.ui.linkEditWidget.setBugPatterns(
            self.settings.bugPatterns(repoName))
        self.ui.cbFallback.setChecked(
            self.settings.fallbackGlobalLinks(repoName))

        self.ui.cbShowWhitespace.setChecked(self.settings.showWhitespace())
        self.ui.sbTabSize.setValue(self.settings.tabSize())

        self.ui.cbEsc.setChecked(self.settings.quitViaEsc())
        self.ui.cbState.setChecked(self.settings.rememberWindowState())

        index = self.settings.ignoreWhitespace()
        if index < 0 or index >= self.ui.cbIgnoreWhitespace.count():
            index = 0
        self.ui.cbIgnoreWhitespace.setCurrentIndex(index)

        tools = self.settings.mergeToolList()
        self.ui.tableView.model().setRawData(tools)

        name = self.settings.diffToolName()
        self.ui.cbDiffName.setCurrentText(name)
        self.ui.leDiffCmd.setText(Git.diffToolCmd(name))

        name = self.settings.mergeToolName()
        self.ui.cbMergeName.setCurrentText(name)
        self.ui.leMergeCmd.setText(Git.mergeToolCmd(name))

        git = self.settings.gitBinPath()
        if not git and GitProcess.GIT_BIN:
            git = GitProcess.GIT_BIN
        self.ui.leGitPath.setText(git)

        self.ui.leServerUrl.setText(self.settings.llmServer())

        days = self.settings.maxCompositeCommitsSince()
        for i in range(self.ui.cbCommitSince.count()):
            if self.ui.cbCommitSince.itemData(i) == days:
                self.ui.cbCommitSince.setCurrentIndex(i)
                break

        self.ui.cbShowPC.setChecked(self.settings.showParentChild())

        self.ui.cbColorSchema.addItem(self.tr("Auto"), ColorSchemaMode.Auto)
        self.ui.cbColorSchema.addItem(self.tr("Light"), ColorSchemaMode.Light)
        self.ui.cbColorSchema.addItem(self.tr("Dark"), ColorSchemaMode.Dark)

        index = self.ui.cbColorSchema.findData(self.settings.colorSchemaMode())
        self.ui.cbColorSchema.setCurrentIndex(index)

        for i in range(0, 5):
            self._initedTabs.add(i)

    def _updateFontSizes(self, family, size, cb):
        fdb = QFontDatabase()
        sizes = fdb.pointSizes(family)
        if not sizes:
            sizes = QFontDatabase.standardSizes()

        sizes.sort()
        cb.clear()
        cb.blockSignals(True)

        curIdx = -1
        for i in range(len(sizes)):
            s = sizes[i]
            cb.addItem(str(s))
            # find the best one for @size
            if curIdx == -1 and s >= size:
                if i > 0 and (size - sizes[i - 1] < s - size):
                    curIdx = i - 1
                else:
                    curIdx = i

        cb.blockSignals(False)
        cb.setCurrentIndex(0 if curIdx == -1 else curIdx)

    def _onFamilyChanged(self, font):
        cbSize = self.ui.cbSizeLog
        size = self.settings.logViewFont().pointSize()
        if self.sender() == self.ui.cbFamilyDiff:
            cbSize = self.ui.cbSizeDiff
            size = self.settings.diffViewFont().pointSize()

        self._updateFontSizes(font.family(), size, cbSize)

    def _onBtnAddClicked(self, checked=False):
        self._tableViewAddItem(self.ui.tableView, ToolTableModel.Col_Suffix)

    def _tableViewAddItem(self, tableView: QTableView, editCol: int):
        model = tableView.model()
        row = model.rowCount()
        if not model.insertRow(row):
            return
        index = model.index(row, editCol)
        tableView.edit(index)

    def _onBtnDeleteClicked(self, checked=False):
        self._tableViewAddItem(self.ui.tableView)

    def _tableViewDeleteItem(self, tableView: QTableView):
        indexes = tableView.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self,
                                    qApp.applicationName(),
                                    self.tr("Please select one row at least to delete."))
            return

        if len(indexes) > 1:
            text = self.tr(
                "You have selected more than one record, do you really want delete all of them?")
            r = QMessageBox.question(self, qApp.applicationName(),
                                     text,
                                     QMessageBox.Yes,
                                     QMessageBox.No)
            if r != QMessageBox.Yes:
                return

        indexes.sort(reverse=True)
        for index in indexes:
            tableView.model().removeRow(index.row())

    def _onSuffixExists(self, suffix):
        QMessageBox.information(self,
                                qApp.applicationName(),
                                self.tr("The suffix you specify is already exists."))

    def _onBtnGlobalClicked(self, clicked):
        linkEditDlg = LinkEditDialog(self)
        commitUrl = self.settings.commitUrl(None)
        bugPatterns = self.settings.bugPatterns(None)

        linkEdit = linkEditDlg.linkEdit
        linkEdit.setCommitUrl(commitUrl)
        linkEdit.setBugPatterns(bugPatterns)

        if linkEditDlg.exec() == QDialog.Accepted:
            self.settings.setCommitUrl(None, linkEdit.commitUrl())
            self.settings.setBugPatterns(None, linkEdit.bugPatterns())

    def _onConfigImgDiff(self, link):
        path = self._imgDiffBin()
        if not path:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                self.tr("Unable to find the path of imgdiff!"))
            return

        if os.name == "nt":
            path = path.replace("\\", "/")

        ret, error = Git.setDiffTool(
            "imgdiff", '%s "$LOCAL" "$REMOTE"' % path)
        if ret != 0:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                error)
            return

        ret, error = Git.setMergeTool(
            "imgdiff", '%s "$BASE" "$LOCAL" "$REMOTE" -o "$MERGED"' % path)
        if ret != 0:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                error)

    def _onAccepted(self):
        if not self._checkTool(True):
            QMessageBox.critical(
                self, self.window().windowTitle(),
                self.tr("The diff tool name can't be empty!"))
            self.ui.tabWidget.setCurrentWidget(self.ui.tabTools)
            self.ui.cbDiffName.setFocus()
            return

        if not self._checkTool(False):
            QMessageBox.critical(
                self, self.window().windowTitle(),
                self.tr("The merge tool name can't be empty!"))
            self.ui.tabWidget.setCurrentWidget(self.ui.tabTools)
            self.ui.cbMergeName.setFocus()
            return

        git = self.ui.leGitPath.text()
        if not self.isGitUsable(git):
            QMessageBox.critical(
                self, self.window().windowTitle(),
                self.tr("The git path you specified is invalid."))

            self.ui.tabWidget.setCurrentWidget(self.ui.tabGeneral)
            self.ui.leGitPath.setFocus()
            return

        self.accept()

    def isGitUsable(self, git):
        try:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.check_call([git, "--version"], stderr=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, startupinfo=startupinfo)
            return True
        except Exception:
            return False

    def _onCheckUpdatesChanged(self, checked):
        self.ui.sbDays.setEnabled(checked)

    def _onBtnChooseGitClicked(self, checked):
        f, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Choose Git"))
        if f:
            self.ui.leGitPath.setText(f)

    def _checkTool(self, isDiff):
        if isDiff:
            name = self.ui.cbDiffName.currentText().strip()
            cmd = self.ui.leDiffCmd.text().strip()
        else:
            name = self.ui.cbMergeName.currentText().strip()
            cmd = self.ui.leMergeCmd.text().strip()

        return not cmd or name

    def _imgDiffBin(self):
        def _quote(path):
            if " " in path:
                return '"' + path + '"'
            return path

        exeName = os.path.basename(sys.argv[0])
        exePath = os.path.abspath(os.path.dirname(sys.argv[0]))
        # source version
        if exeName == "qgitc.py":
            path = os.path.join(exePath, "mergetool", "imgdiff.py")
            if not os.path.exists(path):
                return None

            bin = sys.executable
            if bin.endswith(".exe") and not bin.endswith("w.exe"):
                bin = bin.replace(".exe", "w.exe")

            return _quote(bin) + " " + _quote(path)
        else:
            path = os.path.join(exePath, "imgdiff")
            if sys.platform == "win32":
                path += ".exe"
            if not os.path.exists(path):
                return None

            return _quote(path)

        return None

    def save(self):
        # TODO: only update those values that really changed
        value = self.ui.cbCheckUpdates.isChecked()
        self.settings.setCheckUpdatesEnabled(value)

        value = self.ui.sbDays.value()
        self.settings.setCheckUpdatesInterval(value)

        font = QFont(self.ui.cbFamilyLog.currentText(),
                     int(self.ui.cbSizeLog.currentText()))

        self.settings.setLogViewFont(font)

        font = QFont(self.ui.cbFamilyDiff.currentText(),
                     int(self.ui.cbSizeDiff.currentText()))

        self.settings.setDiffViewFont(font)

        color = self.ui.colorA.getColor()
        self.settings.setCommitColorA(color)

        color = self.ui.colorB.getColor()
        self.settings.setCommitColorB(color)

        value = self.ui.linkEditWidget.commitUrl().strip()
        repoName = qApp.repoName()
        self.settings.setCommitUrl(repoName, value)

        value = self.ui.linkEditWidget.bugPatterns()
        self.settings.setBugPatterns(repoName, value)

        value = self.ui.cbFallback.isChecked()
        self.settings.setFallbackGlobalLinks(repoName, value)

        value = self.ui.cbShowWhitespace.isChecked()
        self.settings.setShowWhitespace(value)

        value = self.ui.sbTabSize.value()
        self.settings.setTabSize(value)

        value = self.ui.cbEsc.isChecked()
        self.settings.setQuitViaEsc(value)

        value = self.ui.cbState.isChecked()
        self.settings.setRememberWindowState(value)

        value = self.ui.cbIgnoreWhitespace.currentIndex()
        self.settings.setIgnoreWhitespace(value)

        tools = self.ui.tableView.model().rawData()
        # TODO: validate if all tool isValid before saving
        self.settings.setMergeToolList(tools)

        name = self.ui.cbDiffName.currentText()
        self.settings.setDiffToolName(name)

        value = self.ui.leDiffCmd.text()
        ret, error = Git.setDiffTool(name, value)
        if ret != 0 and error:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                error)

        name = self.ui.cbMergeName.currentText()
        self.settings.setMergeToolName(name)

        value = self.ui.leMergeCmd.text()
        ret, error = Git.setMergeTool(name, value)

        if ret != 0 and error:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                error)

        value = self.ui.leGitPath.text()
        self.settings.setGitBinPath(value)

        self.settings.setLlmServer(self.ui.leServerUrl.text().strip())

        value = self.ui.cbCommitSince.currentData()
        self.settings.setMaxCompositeCommitsSince(value)

        value = self.ui.cbShowPC.isChecked()
        self.settings.setShowParentChild(value)

        value = self.ui.cbColorSchema.currentData()
        self.settings.setColorSchemaMode(value)

        self._saveCommitMessageTab()

    def _onTabChanged(self, index):
        if index in self._initedTabs:
            return

        self._initedTabs.add(index)

        if self.ui.tabWidget.indexOf(self.ui.tabCommitMessage) == index:
            self._initCommitMessageTab()

    def _initCommitMessageTab(self):
        self.ui.cbIgnoreComment.setChecked(self.settings.ignoreCommentLine())
        self.ui.cbTab.setChecked(self.settings.tabToNextGroup())
        self.ui.leGroupChars.setText(self.settings.groupChars())

        actions = self.settings.commitActions()
        self.ui.tvActions.model().setRawData(actions)

    def _saveCommitMessageTab(self):
        value = self.ui.cbIgnoreComment.isChecked()
        self.settings.setIgnoreCommentLine(value)

        value = self.ui.cbTab.isChecked()
        self.settings.setTabToNextGroup(value)

        value = self.ui.leGroupChars.text().strip()
        self.settings.setGroupChars(value)

        actions = self.ui.tvActions.model().rawData()
        self.settings.setCommitActions(actions)

    def _onAddActionClicked(self):
        self._tableViewAddItem(
            self.ui.tvActions, CommitActionTableModel.Col_Cmd)

    def _onDeleteActionClicked(self):
        self._tableViewDeleteItem(self.ui.tvActions)
