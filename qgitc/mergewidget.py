# -*- coding: utf-8 -*-

from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PySide2.QtCore import *
from .gitutils import Git, GitProcess
from .stylehelper import dpiScaled
from .conflictlog import (
    ConflictLogExcel,
    ConflictLogXlsx,
    HAVE_EXCEL_API,
    HAVE_XLSX_WRITER,
    MergeInfo)
from .events import CopyConflictCommit
from .common import dataDirPath

from datetime import datetime

import shutil


STATE_CONFLICT = 0
STATE_RESOLVED = 1

RESOLVE_SUCCEEDED = 0
RESOLVE_FAILED = 1

StateRole = Qt.UserRole + 1


class MergeWidget(QWidget):
    requestResolve = Signal(str)
    resolveFinished = Signal(int)

    def __init__(self, parent=None):
        super(MergeWidget, self).__init__(parent)
        self.setWindowFlags(Qt.WindowMinMaxButtonsHint)
        self.setWindowTitle(self.tr("Conflict List"))

        self.resolvedCount = 0
        self.iconResolved = self.__makeTextIcon(chr(0x2714), Qt.green)
        self.iconConflict = self.__makeTextIcon('!', Qt.red)

        self.resolveIndex = -1
        self.process = None

        self._firstShown = True

        self.log = None

        self.__setupUi()
        self.__setupSignals()

        self._mergeInfo = None

    def __setupUi(self):
        self.view = QListView(self)
        self.model = QStandardItemModel(self)
        self.proxyModel = QSortFilterProxyModel(self)
        self.proxyModel.setSourceModel(self.model)

        self.view.setModel(self.proxyModel)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.leFilter = QLineEdit(self)
        self.lbFilter = QLabel("0", self)

        filterLayout = QHBoxLayout()
        filterLayout.addWidget(self.leFilter)
        filterLayout.addWidget(self.lbFilter)

        vlayout = QVBoxLayout(self)
        vlayout.addLayout(filterLayout)
        vlayout.addWidget(self.view)

        hlayout = QHBoxLayout()

        self.status = QLabel(self)
        self.status.setToolTip(self.tr("Click to refresh the list"))
        self.cbAutoNext = QCheckBox(self.tr("Continuous resolve"))
        self.btnResolve = QPushButton(self.tr("Resolve"))

        hlayout.addWidget(self.status)
        hlayout.addSpacerItem(QSpacerItem(
            20, 20, QSizePolicy.MinimumExpanding))
        hlayout.addWidget(self.cbAutoNext)
        hlayout.addWidget(self.btnResolve)

        vlayout.addLayout(hlayout)

        self.cbAutoLog = QCheckBox(self.tr("Log conflicts to"), self)
        self.leLogFile = QLineEdit(self)
        self.btnChooseLog = QPushButton(self.tr("Choose"), self)

        hlayout = QHBoxLayout()
        hlayout.addWidget(self.cbAutoLog)
        hlayout.addWidget(self.leLogFile)
        hlayout.addWidget(self.btnChooseLog)
        vlayout.addLayout(hlayout)

        self.cbAutoNext.setChecked(True)
        if HAVE_EXCEL_API or HAVE_XLSX_WRITER:
            self.cbAutoLog.setChecked(True)
            self.__onAutoLogChanged(Qt.Checked)
        else:
            self.cbAutoLog.setChecked(False)
            self.cbAutoLog.setEnabled(False)
            self.cbAutoLog.setToolTip(
                self.tr("No pywin32/pywpsrpc or openpyxl found, feature disabled."))
            self.__onAutoLogChanged(Qt.Unchecked)
        self.leLogFile.setText(self.__defaultLogFile())

        self.__setupMenu()

    def __defaultLogFile(self):
        dir = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        dt = datetime.now()
        fileName = "conflicts-{}.xlsx".format(dt.strftime("%Y%m%d%H%M%S"))
        return dir + QDir.separator() + fileName

    def __ensureLogWriter(self):
        if self.log is not None:
            return

        logFile = self.leLogFile.text()
        shutil.copy(dataDirPath() + "/templates/builtin.xlsx", logFile)

        if HAVE_EXCEL_API:
            self.log = ConflictLogExcel(logFile)
        elif HAVE_XLSX_WRITER:
            self.log = ConflictLogXlsx(logFile)

        if self._mergeInfo is not None:
            self.log.setMergeInfo(self._mergeInfo)

    def __setupMenu(self):
        self.menu = QMenu()
        self.acResolve = self.menu.addAction(
            self.tr("&Resolve"),
            self.__onMenuResolve)
        self.acUndoMerge = self.menu.addAction(
            self.tr("&Undo merge"),
            self.__onMenuUndoMerge)
        self.menu.addSeparator()

        self.acUseOurs = self.menu.addAction(
            self.tr("Use &ours"),
            self.__onMenuUseOurs)
        self.acUseTheirs = self.menu.addAction(
            self.tr("Use &theirs"),
            self.__onMenuUseTheirs)

        self.menu.addSeparator()
        self.menu.addAction(self.tr("&Copy Path"),
                            self.__onMenuCopyPath,
                            QKeySequence("Ctrl+C"))
        self.menu.addAction(self.tr("Copy &Windows Path"),
                            self.__onMenuCopyWinPath)

    def __setupSignals(self):
        self.btnResolve.clicked.connect(self.__onResolveClicked)
        self.view.doubleClicked.connect(self.__onItemDoubleClicked)
        self.status.linkActivated.connect(self.__onStatusRefresh)
        self.leFilter.textChanged.connect(self.__onFilterChanged)
        self.cbAutoLog.stateChanged.connect(self.__onAutoLogChanged)
        self.btnChooseLog.clicked.connect(self.__onChooseLogFile)

    def __makeTextIcon(self, text, color):
        img = QPixmap(dpiScaled(QSize(32, 32)))
        img.fill(Qt.transparent)

        painter = QPainter(img)
        painter.setPen(color)
        font = QFont()
        font.setPixelSize(dpiScaled(32))
        painter.setFont(font)
        painter.drawText(img.rect(), Qt.AlignCenter, text)
        painter = None

        return QIcon(img)

    def __updateStatus(self):
        # just don't wanna inherit a QLabel LoL
        total = self.model.rowCount()
        self.status.setText(
            "<a href='#refresh'>{}/{}</a>".format(self.resolvedCount,
                                                  total))

    def __updateFilterCount(self):
        text = self.proxyModel.filterRegExp().pattern()
        count = self.proxyModel.rowCount() if text else 0
        self.lbFilter.setText("{}".format(count))

    def __resolvedIndex(self, index):
        index = self.proxyModel.mapToSource(index)
        item = self.model.itemFromIndex(index)
        item.setData(STATE_RESOLVED, StateRole)
        item.setIcon(self.iconResolved)
        self.resolvedCount += 1
        self.__updateStatus()

    def __checkCurrentResolve(self, index):
        if self.resolveIndex == index.row():
            text = self.tr(
                "You are resolving this file, please close it first.")
            QMessageBox.information(self,
                                    qApp.applicationName(),
                                    text)
            return False

        return True

    def __onResolveClicked(self, checked=False):
        index = self.view.currentIndex()
        self.resolve(index)

    def __onItemDoubleClicked(self, index):
        self.resolve(index)

    def __onStatusRefresh(self, link):
        if self.process:
            QMessageBox.information(self,
                                    qApp.applicationName(),
                                    self.tr("You can't refresh before close the merge window."))
            return
        self.updateList()

    def __onFilterChanged(self, text):
        self.proxyModel.setFilterRegExp(text)
        self.__updateFilterCount()

    def __onAutoLogChanged(self, state):
        enabled = state == Qt.Checked
        self.leLogFile.setEnabled(enabled)
        self.btnChooseLog.setEnabled(enabled)

    def __onChooseLogFile(self, checked):
        f, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Choose file"),
            dir=QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation))
        if f:
            self.leLogFile.setText(f)

    def __onMenuResolve(self):
        self.__onResolveClicked()

    def __onMenuUndoMerge(self):
        index = self.view.currentIndex()
        if index.data(StateRole) != STATE_RESOLVED:
            return

        if Git.undoMerge(index.data()):
            index = self.proxyModel.mapToSource(index)
            item = self.model.itemFromIndex(index)
            item.setData(STATE_CONFLICT, StateRole)
            item.setIcon(self.iconConflict)
            self.resolvedCount -= 1
            self.__updateStatus()

    def __onMenuUseOurs(self):
        index = self.view.currentIndex()
        if not self.__checkCurrentResolve(index):
            return
        if index.data(StateRole) == STATE_CONFLICT:
            if Git.resolveBy(True, index.data()):
                self.__resolvedIndex(index)
                if self.logEnabled():
                    self.__ensureLogWriter()
                    self.log.setResolveMethod(
                        index.data(),
                        self.tr("Local Branch"))

    def __onMenuUseTheirs(self):
        index = self.view.currentIndex()
        if not self.__checkCurrentResolve(index):
            return
        if index.data(StateRole) == STATE_CONFLICT:
            if Git.resolveBy(False, index.data()):
                self.__resolvedIndex(index)
                if self.logEnabled():
                    self.__ensureLogWriter()
                    self.log.setResolveMethod(
                        index.data(),
                        self.tr("Remote Branch"))

    def __doCopyPath(self, asWin=False):
        index = self.view.currentIndex()
        if not index.isValid():
            return

        path = index.data(Qt.DisplayRole)
        qApp.clipboard().setText(path if not asWin else path.replace('/', '\\'))

    def __onMenuCopyPath(self):
        self.__doCopyPath()

    def __onMenuCopyWinPath(self):
        self.__doCopyPath(True)

    def __onReadyRead(self):
        # FIXME: since git might not flush all output at one time
        # delay some time to read all data for "Deleted merge"
        QTimer.singleShot(50, self.__onResolveReadyRead)

    def __onResolveReadyRead(self):
        if not self.process or not self.process.bytesAvailable():
            return

        data = self.process.readAllStandardOutput().data()
        # seems no options to control this buggy prompt
        if b'Continue merging other unresolved paths [y/n]?' in data:
            self.process.write(b"n\n")
        elif b'Deleted merge conflict for' in data:
            text = data.decode("utf-8")
            isCreated = "(c)reated" in text
            if isCreated:
                text = text.replace("(c)reated", "created")
            else:
                text = text.replace("(m)odified", "modified")
            text = text.replace("(d)eleted", "deleted")
            text = text.replace("(a)bort", "abort")

            msgBox = QMessageBox(
                QMessageBox.Question, qApp.applicationName(), text, QMessageBox.NoButton, self)
            msgBox.addButton(self.tr("Use &created") if isCreated
                             else self.tr("Use &modified"),
                             QMessageBox.AcceptRole)
            msgBox.addButton(self.tr("&Deleted file"), QMessageBox.RejectRole)
            msgBox.addButton(QMessageBox.Abort)
            r = msgBox.exec_()
            if r == QMessageBox.AcceptRole:
                if isCreated:
                    self.process.write(b"c\n")
                else:
                    self.process.write(b"m\n")
            elif r == QMessageBox.RejectRole:
                self.process.write(b"d\n")
            else:  # r == QMessageBox.Abort:
                self.process.write(b"a\n")
        elif b'Symbolic link merge conflict for' in data:
            text = data.decode("utf-8")
            text = text.replace("(l)ocal", "local")
            text = text.replace("(r)emote", "remote")
            text = text.replace("(a)bort", "abort")

            msgBox = QMessageBox(
                QMessageBox.Question, qApp.applicationName(), text, QMessageBox.NoButton, self)
            msgBox.addButton(self.tr("Use &local"), QMessageBox.AcceptRole)
            msgBox.addButton(self.tr("Use &remote"), QMessageBox.RejectRole)
            msgBox.addButton(QMessageBox.Abort)
            r = msgBox.exec_()
            if r == QMessageBox.AcceptRole:
                self.process.write(b"l\n")
            elif r == QMessageBox.RejectRole:
                self.process.write(b"r\n")
            else:
                self.process.write(b"a\n")
        elif b'Was the merge successful [y/n]?' in data:
            # TODO:
            self.process.write(b"n\n")
        elif b'?' in data:
            # TODO: might have other prompt need yes no
            print("unhandled prompt", data)

    def __onResolveFinished(self, exitCode, exitStatus):
        errorData = None
        if exitCode == 0:
            index = self.proxyModel.index(self.resolveIndex, 0)
            self.__resolvedIndex(index)
        else:
            errorData = self.process.readAllStandardError()

        self.process = None
        curRow = self.resolveIndex
        self.resolveIndex = -1

        self.resolveFinished.emit(RESOLVE_SUCCEEDED if exitCode == 0
                                  else RESOLVE_FAILED)

        self.leFilter.setEnabled(True)
        self.cbAutoLog.setEnabled(True)
        self.__onAutoLogChanged(self.cbAutoLog.checkState())
        # auto next only when success
        if exitCode != 0:
            if errorData:
                QMessageBox.critical(
                    self, self.window().windowTitle(),
                    errorData.data().decode("utf-8"))
            return

        if not self.cbAutoNext.isChecked():
            return

        if self.resolvedCount == self.model.rowCount():
            QMessageBox.information(self, qApp.applicationName(),
                                    self.tr("All resolved!"))
            return

        index = None
        allFilterResolved = True
        noEndConflicts = True
        # search to the end
        for i in range(curRow + 1, self.proxyModel.rowCount()):
            index = self.proxyModel.index(i, 0)
            if index.data(StateRole) == STATE_CONFLICT:
                allFilterResolved = False
                noEndConflicts = False
                break
            index = None

        # search from beginning
        if not index:
            for i in range(curRow):
                index = self.proxyModel.index(i, 0)
                if index.data(StateRole) == STATE_CONFLICT:
                    allFilterResolved = False
                    break
                index = None

        # to avoid show two messagebox if reach to the end
        if allFilterResolved:
            text = self.tr(
                "All filter conflicts are resolved, please clear the filter to resolve the rest.")
            QMessageBox.information(self, qApp.applicationName(), text)
            return
        elif noEndConflicts:
            text = self.tr(
                "Resolve reach to the end of list, do you want to resolve from beginning?")
            r = QMessageBox.question(
                self, qApp.applicationName(), text, QMessageBox.Yes, QMessageBox.No)
            if r == QMessageBox.No:
                return

        self.view.setCurrentIndex(index)
        self.resolve(index)

    def __onFirstShow(self):
        self.updateList()
        if self.model.rowCount() == 0:
            QMessageBox.information(
                self,
                self.window().windowTitle(),
                self.tr("No conflict files to resolve!"),
                QMessageBox.Ok)

    def contextMenuEvent(self, event):
        index = self.view.currentIndex()
        enabled = index.data(StateRole) == STATE_RESOLVED
        self.acResolve.setEnabled(not enabled)
        self.acUndoMerge.setEnabled(enabled)
        self.acUseOurs.setEnabled(not self.isResolving())
        self.acUseTheirs.setEnabled(not self.isResolving())
        self.menu.exec_(event.globalPos())

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._firstShown:
            self._firstShown = False
            QTimer.singleShot(0, self.__onFirstShow)

    def sizeHint(self):
        return dpiScaled(QSize(500, 700))

    def updateList(self):
        if not Git.available():
            return

        files = Git.conflictFiles()
        self.model.clear()
        if files:
            for f in files:
                item = QStandardItem(self.iconConflict, f)
                item.setData(STATE_CONFLICT, StateRole)
                self.model.appendRow(item)

            index = self.proxyModel.index(0, 0)
            self.view.setCurrentIndex(index)
        self.resolvedCount = 0
        self.__updateStatus()
        self.__updateFilterCount()

        for action in self.menu.actions():
            action.setEnabled(not files is None)
        self.btnResolve.setEnabled(not files is None)

    def resolve(self, index):
        if not index.isValid():
            return

        if index.data(StateRole) == STATE_RESOLVED:
            QMessageBox.information(self, qApp.applicationName(),
                                    self.tr("This file is already resolved."))
            return

        if self.process:
            QMessageBox.information(self, qApp.applicationName(),
                                    self.tr("Please resolve current conflicts before start a new one."))
            return

        # since we saved the index, so disabled ...
        self.leFilter.setEnabled(False)
        self.cbAutoLog.setEnabled(False)
        self.__onAutoLogChanged(Qt.Unchecked)
        self.resolveIndex = index.row()
        file = index.data()
        args = ["mergetool", "--no-prompt"]

        toolName = None
        tools = qApp.settings().mergeToolList()
        # ignored case even on Unix platform
        lowercase_file = file.lower()
        for tool in tools:
            if tool.canMerge() and tool.isValid():
                if lowercase_file.endswith(tool.suffix.lower()):
                    toolName = tool.command
                    break

        if not toolName:
            toolName = qApp.settings().mergeToolName()

        if toolName:
            args.append("--tool=%s" % toolName)

        args.append(file)

        # subprocess is not suitable here
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.__onReadyRead)
        self.process.finished.connect(self.__onResolveFinished)
        self.process.setWorkingDirectory(Git.REPO_DIR)
        self.process.start(GitProcess.GIT_BIN, args)

        self.requestResolve.emit(file)
        if self.logEnabled():
            self.__ensureLogWriter()
            self.log.addFile(file)

    def event(self, e):
        if e.type() == CopyConflictCommit.Type:
            if self.isResolving() and self.logEnabled():
                self.log.addCommit(e.commit)
            return True

        return super().event(e)

    def isResolving(self):
        return self.process is not None

    def logEnabled(self):
        return self.cbAutoLog.isChecked()

    def queryClose(self):
        if self.log:
            self.log.save()
            self.log = None
        return True

    def setBranches(self, localBranch, remoteBranch):
        self._mergeInfo = MergeInfo(
            localBranch,
            remoteBranch.replace("remotes/origin/", ""),
            Git.getConfigValue("user.name", False)
        )
