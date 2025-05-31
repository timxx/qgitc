# -*- coding: utf-8 -*-

import logging
import os
import subprocess
import sys

from PySide6.QtWidgets import QFileDialog, QMessageBox, QStyleFactory

from qgitc.applicationbase import ApplicationBase
from qgitc.colorschema import ColorSchemaMode
from qgitc.comboboxitemdelegate import ComboBoxItemDelegate
from qgitc.commitactioneditdialog import CommitActionEditDialog
from qgitc.common import logger
from qgitc.events import GitBinChanged
from qgitc.githubcopilotlogindialog import GithubCopilotLoginDialog
from qgitc.gitutils import Git, GitProcess
from qgitc.linkeditdialog import LinkEditDialog
from qgitc.llm import AiModelBase, AiModelFactory
from qgitc.settings import Settings
from qgitc.tooltablemodel import ToolTableModel
from qgitc.ui_preferences import *


class Preferences(QDialog):

    def __init__(self, settings: Settings, parent=None):
        super(Preferences, self).__init__(parent)

        self.ui = Ui_Preferences()
        self.ui.setupUi(self)
        self.settings = settings
        self._repoName: str = ApplicationBase.instance().repoName()

        model = ToolTableModel(self)
        self.ui.tableView.setModel(model)
        self.ui.tableView.horizontalHeader().setSectionResizeMode(
            ToolTableModel.Col_Tool,
            QHeaderView.Stretch)

        delegate = ComboBoxItemDelegate(model.getSceneNames(), self)
        self.ui.tableView.setItemDelegateForColumn(
            ToolTableModel.Col_Scenes, delegate)

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

        self.ui.btnGithubCopilot.clicked.connect(
            self._onGithubCopilotClicked)

        self._initedTabs = set()
        # FIXME: we'd better use interface to implement tabs
        self._tabs = {
            self.ui.tabGeneral: (self._initGeneralTab, self._saveGeneralTab),
            self.ui.tabFonts: (self._initFontsTab, self._saveFontsTab),
            self.ui.tabSummary: (self._initSummaryTab, self._saveSummaryTab),
            self.ui.tabTools: (self._initToolsTab, self._saveToolsTab),
            self.ui.tabLLM: (self._initLLMTab, self._saveLLMTab),
            self.ui.tabCommitMessage: (self._initCommitMessageTab, self._saveCommitMessageTab),
        }

        self._onTabChanged(self.ui.tabWidget.currentIndex())

        self.ui.btnEditGlobalActions.clicked.connect(
            self._onEditGlobalActionsClicked)

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
                                    ApplicationBase.instance().applicationName(),
                                    self.tr("Please select one row at least to delete."))
            return

        if len(indexes) > 1:
            text = self.tr(
                "You have selected more than one record, do you really want delete all of them?")
            r = QMessageBox.question(self, ApplicationBase.instance().applicationName(),
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
                                ApplicationBase.instance().applicationName(),
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

        self.save()
        self.accept()

    def isGitUsable(self, git):
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW
            subprocess.check_call([git, "--version"], stderr=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, creationflags=creationflags)
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
        for tab in self._initedTabs:
            self._tabs[tab][1]()

        if self.ui.tabGeneral in self._initedTabs:
            logging.getLogger().setLevel(
                self.ui.cbLogLevel.currentData())

        if self.settings.gitBinPath() != GitProcess.GIT_BIN:
            ApplicationBase.instance().postEvent(ApplicationBase.instance(), GitBinChanged())

    def _onTabChanged(self, index):
        tab = self.ui.tabWidget.widget(index)
        if tab in self._initedTabs:
            return

        self._initedTabs.add(tab)

        assert tab in self._tabs
        self._tabs[tab][0]()

    def _initGeneralTab(self):
        self.ui.cbEsc.setChecked(self.settings.quitViaEsc())
        self.ui.cbState.setChecked(self.settings.rememberWindowState())

        checked = self.settings.checkUpdatesEnabled()
        self.ui.cbCheckUpdates.setChecked(checked)
        self._onCheckUpdatesChanged(checked)
        self.ui.sbDays.setValue(self.settings.checkUpdatesInterval())

        self.ui.cbLogLevel.addItem(self.tr("Critical"), logging.CRITICAL)
        self.ui.cbLogLevel.addItem(self.tr("Error"), logging.ERROR)
        self.ui.cbLogLevel.addItem(self.tr("Warning"), logging.WARNING)
        self.ui.cbLogLevel.addItem(self.tr("Info"), logging.INFO)
        self.ui.cbLogLevel.addItem(self.tr("Debug"), logging.DEBUG)

        index = self.ui.cbLogLevel.findData(self.settings.logLevel())
        self.ui.cbLogLevel.setCurrentIndex(index)

        self.ui.cbColorSchema.addItem(self.tr("Auto"), ColorSchemaMode.Auto)
        self.ui.cbColorSchema.addItem(self.tr("Light"), ColorSchemaMode.Light)
        self.ui.cbColorSchema.addItem(self.tr("Dark"), ColorSchemaMode.Dark)
        index = self.ui.cbColorSchema.findData(self.settings.colorSchemaMode())
        self.ui.cbColorSchema.setCurrentIndex(index)

        langs = self._uiLanguages()
        for lang, desc in langs:
            self.ui.cbLanguage.addItem(desc, lang)

        index = self.ui.cbLanguage.findData(self.settings.language())
        if index == -1:
            index = 0
        self.ui.cbLanguage.setCurrentIndex(index)

        styles = QStyleFactory.keys()
        for style in styles:
            self.ui.cbStyle.addItem(style.capitalize())

        def _findStyle(styleName):
            for i in range(self.ui.cbStyle.count()):
                if self.ui.cbStyle.itemText(i).lower() == styleName.lower():
                    return i
            return -1

        index = _findStyle(self.settings.styleName())
        if index == -1:
            index = _findStyle(ApplicationBase.instance().style().name())
        if index != -1:
            self.ui.cbStyle.setCurrentIndex(index)
        else:
            logger.warning("No style found in [%s]", ",".join(styles))

        git = self.settings.gitBinPath()
        if not git and GitProcess.GIT_BIN:
            git = GitProcess.GIT_BIN
        self.ui.leGitPath.setText(git)

        self.ui.cbShowWhitespace.setChecked(self.settings.showWhitespace())
        self.ui.sbTabSize.setValue(self.settings.tabSize())

        index = self.settings.ignoreWhitespace()
        if index < 0 or index >= self.ui.cbIgnoreWhitespace.count():
            index = 0
        self.ui.cbIgnoreWhitespace.setCurrentIndex(index)

        self.ui.cbShowPC.setChecked(self.settings.showParentChild())

    def _saveGeneralTab(self):
        value = self.ui.cbEsc.isChecked()
        self.settings.setQuitViaEsc(value)

        value = self.ui.cbState.isChecked()
        self.settings.setRememberWindowState(value)

        value = self.ui.cbCheckUpdates.isChecked()
        self.settings.setCheckUpdatesEnabled(value)

        value = self.ui.sbDays.value()
        self.settings.setCheckUpdatesInterval(value)

        value = self.ui.cbLogLevel.currentData()
        self.settings.setLogLevel(value)

        value = self.ui.cbColorSchema.currentData()
        self.settings.setColorSchemaMode(value)

        value = self.ui.cbStyle.currentText()
        self.settings.setStyleName(value)
        ApplicationBase.instance().setStyle(value)

        value = self.ui.cbLanguage.currentData()
        self.settings.setLanguage(value)

        value = self.ui.leGitPath.text()
        self.settings.setGitBinPath(value)

        value = self.ui.cbShowWhitespace.isChecked()
        self.settings.setShowWhitespace(value)

        value = self.ui.sbTabSize.value()
        self.settings.setTabSize(value)

        value = self.ui.cbIgnoreWhitespace.currentIndex()
        self.settings.setIgnoreWhitespace(value)

        value = self.ui.cbShowPC.isChecked()
        self.settings.setShowParentChild(value)

    def _initFontsTab(self):
        font = self.settings.logViewFont()
        self.ui.logFonts.setFont(font)

        font = self.settings.diffViewFont()
        self.ui.diffFonts.setFont(font)

    def _saveFontsTab(self):
        font = self.ui.logFonts.font()
        self.settings.setLogViewFont(font)

        font = self.ui.diffFonts.font()
        self.settings.setDiffViewFont(font)

    def _initSummaryTab(self):
        self.ui.colorA.setColor(self.settings.commitColorA())
        self.ui.colorB.setColor(self.settings.commitColorB())

        self.ui.linkEditWidget.setCommitUrl(
            self.settings.commitUrl(self._repoName))
        self.ui.linkEditWidget.setBugPatterns(
            self.settings.bugPatterns(self._repoName))
        self.ui.cbFallback.setChecked(
            self.settings.fallbackGlobalLinks(self._repoName))

        days = self.settings.maxCompositeCommitsSince()
        for i in range(self.ui.cbCommitSince.count()):
            if self.ui.cbCommitSince.itemData(i) == days:
                self.ui.cbCommitSince.setCurrentIndex(i)
                break
        self.ui.linkGroup.setTitle(
            self.tr("Links") + (" (" + self._repoName + ")"))

    def _saveSummaryTab(self):
        color = self.ui.colorA.getColor()
        self.settings.setCommitColorA(color)

        color = self.ui.colorB.getColor()
        self.settings.setCommitColorB(color)

        value = self.ui.linkEditWidget.commitUrl().strip()
        self.settings.setCommitUrl(self._repoName, value)

        value = self.ui.linkEditWidget.bugPatterns()
        self.settings.setBugPatterns(self._repoName, value)

        value = self.ui.cbFallback.isChecked()
        self.settings.setFallbackGlobalLinks(self._repoName, value)

        value = self.ui.cbCommitSince.currentData()
        self.settings.setMaxCompositeCommitsSince(value)

    def _initToolsTab(self):
        tools = self.settings.mergeToolList()
        self.ui.tableView.model().setRawData(tools)

        name = self.settings.diffToolName()
        self.ui.cbDiffName.setCurrentText(name)
        self.ui.leDiffCmd.setText(Git.diffToolCmd(name))

        name = self.settings.mergeToolName()
        self.ui.cbMergeName.setCurrentText(name)
        self.ui.leMergeCmd.setText(Git.mergeToolCmd(name))

    def _saveToolsTab(self):
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

    def _initLLMTab(self):
        self.ui.leServerUrl.setText(self.settings.localLlmServer())
        token = self.settings.githubCopilotAccessToken()
        text = self.tr("Logout") if token else self.tr("Login")
        self.ui.btnGithubCopilot.setText(text)

        prefer = self.settings.defaultLlmModel()
        for i, modelClass in enumerate(AiModelFactory.models()):
            model = modelClass(parent=self)
            model.modelsReady.connect(self._onModelsReady)

            self.ui.cbModels.addItem(model.name, model)
            if AiModelFactory.modelKey(model) == prefer:
                self.ui.cbModels.setCurrentIndex(i)

        self.ui.cbModels.currentIndexChanged.connect(self._onModelChanged)
        self._onModelChanged(self.ui.cbModels.currentIndex())

        exts = self.settings.aiExcludedFileExtensions()
        if exts:
            self.ui.leExcludedFiles.setText(", ".join(exts))

    def _onModelsReady(self):
        model: AiModelBase = self.sender()
        if model == self.ui.cbModels.currentData():
            self._onModelChanged(self.ui.cbModels.currentIndex())

    def _onModelChanged(self, index):
        model: AiModelBase = self.ui.cbModels.currentData()
        if not model:
            return
        self.ui.cbModelIds.clear()
        defaultId = self.settings.defaultLlmModelId(
            AiModelFactory.modelKey(model))
        if not defaultId:
            defaultId = model.modelId
        for id, name in model.models():
            self.ui.cbModelIds.addItem(name, id)
            if id == defaultId:
                self.ui.cbModelIds.setCurrentText(name)

    def _saveLLMTab(self):
        self.settings.setLocalLlmServer(self.ui.leServerUrl.text().strip())

        model: AiModelBase = self.ui.cbModels.currentData()
        modelKey = AiModelFactory.modelKey(model)
        self.settings.setDefaultLlmModel(modelKey)

        self.settings.setDefaultLlmModelId(
            modelKey, self.ui.cbModelIds.currentData())

        exts = set()
        for ext in self.ui.leExcludedFiles.text().strip().split(","):
            ext = ext.strip()
            if ext:
                exts.add(ext)

        self.settings.setAiExcludedFileExtensions(list(exts))

    def _initCommitMessageTab(self):
        self.ui.cbIgnoreComment.setChecked(self.settings.ignoreCommentLine())
        self.ui.cbTab.setChecked(self.settings.tabToNextGroup())
        self.ui.leGroupChars.setText(self.settings.groupChars())
        self.ui.cbUseNTP.setChecked(self.settings.useNtpTime())

        actions = self.settings.commitActions(self._repoName)
        self.ui.commitAction.setActions(actions)

        self.ui.cbUseGlobalActions.setChecked(
            self.settings.useGlobalCommitActions())

        self.ui.commitActionGroup.setTitle(
            self.tr("Commit Actions") + (" (" + self._repoName + ")"))

    def _saveCommitMessageTab(self):
        value = self.ui.cbIgnoreComment.isChecked()
        self.settings.setIgnoreCommentLine(value)

        value = self.ui.cbTab.isChecked()
        self.settings.setTabToNextGroup(value)

        value = self.ui.leGroupChars.text().strip()
        self.settings.setGroupChars(value)

        value = self.ui.cbUseNTP.isChecked()
        self.settings.setUseNtpTime(value)

        actions = self.ui.commitAction.actions()
        self.settings.setCommitActions(self._repoName, actions)

        self.settings.setUseGlobalCommitActions(
            self.ui.cbUseGlobalActions.isChecked())

    def _onGithubCopilotClicked(self):
        if self.ui.btnGithubCopilot.text() == self.tr("Logout"):
            self.settings.setGithubCopilotAccessToken("")
            self.settings.setGithubCopilotToken("")
            self.ui.btnGithubCopilot.setText(self.tr("Login"))
        else:
            dialog = GithubCopilotLoginDialog(self)
            dialog.exec()
            if dialog.isLoginSuccessful():
                self.ui.btnGithubCopilot.setText(self.tr("Logout"))

    def _onEditGlobalActionsClicked(self):
        dialog = CommitActionEditDialog(self)
        dialog.widget.setActions(self.settings.globalCommitActions())
        if dialog.exec() == QDialog.Accepted:
            self.settings.setGlobalCommitActions(dialog.widget.actions())

    def _uiLanguages(self):
        return [
            ("", self.tr("System Default")),
            ("en_US", self.tr("English")),
            ("zh_CN", self.tr("Simplified Chinese")),
        ]
