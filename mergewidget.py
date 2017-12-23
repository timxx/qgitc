# -*- coding: utf-8 -*-

from PyQt4.QtGui import *
from PyQt4.QtCore import *
from git import Git


STATE_CONFLICT = 0
STATE_RESOLVED = 1

RESOLVE_SUCCEEDED = 0
RESOLVE_FAILED = 1

StateRole = Qt.UserRole + 1


class MergeWidget(QWidget):
    requestResolve = pyqtSignal(str)
    resolveFinished = pyqtSignal(int)

    def __init__(self, parent=None):
        super(MergeWidget, self).__init__(parent,
                                          Qt.Tool | Qt.CustomizeWindowHint
                                          | Qt.WindowTitleHint)
        self.setWindowTitle(self.tr("Conflict List"))
        self.resize(450, 700)

        self.resolvedCount = 0
        self.iconResolved = self.__makeTextIcon(chr(0x2714), Qt.green)
        self.iconConflict = self.__makeTextIcon('!', Qt.red)

        self.resolveIndex = -1
        self.process = None

        self.__setupUi()
        self.__setupSignals()

        self.updateList()

    def __setupUi(self):
        self.status = QLabel()
        self.status.setToolTip(self.tr("Click to refresh the list"))
        self.view = QListView()
        self.view.setModel(QStandardItemModel())
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)

        vlayout = QVBoxLayout(self)
        vlayout.addWidget(self.status)
        vlayout.addWidget(self.view)

        hlayout = QHBoxLayout()
        self.cbAutoNext = QCheckBox(self.tr("Continuous resolve"))
        self.btnResolve = QPushButton(self.tr("Resolve"))
        hlayout.addWidget(self.cbAutoNext)
        hlayout.addSpacerItem(QSpacerItem(
            20, 20, QSizePolicy.MinimumExpanding))
        hlayout.addWidget(self.btnResolve)
        vlayout.addLayout(hlayout)

        self.cbAutoNext.setChecked(True)

        self.__setupMenu()

    def __setupMenu(self):
        self.menu = QMenu()
        self.menu.addAction(self.tr("&Resolve"),
                            self.__onMenuResolve)
        self.menu.addSeparator()

        self.menu.addAction(self.tr("Use &ours"),
                            self.__onMenuUseOurs)
        self.menu.addAction(self.tr("Use &theirs"),
                            self.__onMenuUseTheirs)

    def __setupSignals(self):
        self.btnResolve.clicked.connect(self.__onResolveClicked)
        self.view.doubleClicked.connect(self.__onItemDoubleClicked)
        self.status.linkActivated.connect(self.__onStatusRefresh)

    def __makeTextIcon(self, text, color):
        img = QPixmap(32, 32)
        img.fill(Qt.transparent)

        painter = QPainter(img)
        painter.setPen(color)
        font = QFont()
        font.setPixelSize(32)
        painter.setFont(font)
        painter.drawText(img.rect(), Qt.AlignCenter, text)
        painter = None

        return QIcon(img)

    def __updateStatus(self):
        # just don't wanna inherit a QLabel LoL
        total = self.view.model().rowCount()
        self.status.setText(
            "<a href='#refresh'>{}/{}</a>".format(self.resolvedCount,
                                                  total))

    def __resolvedIndex(self, index):
        item = self.view.model().itemFromIndex(index)
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

    def __onMenuResolve(self):
        self.__onResolveClicked()

    def __onMenuUseOurs(self):
        index = self.view.currentIndex()
        if not self.__checkCurrentResolve(index):
            return
        if index.data(StateRole) == STATE_CONFLICT:
            if Git.resolveBy(True, index.data()):
                self.__resolvedIndex(index)

    def __onMenuUseTheirs(self):
        index = self.view.currentIndex()
        if not self.__checkCurrentResolve(index):
            return
        if index.data(StateRole) == STATE_CONFLICT:
            if Git.resolveBy(False, index.data()):
                self.__resolvedIndex(index)

    def __onResolveReadyRead(self):
        data = self.process.readAllStandardOutput()
        # seems no options to control this buggy prompt
        if b'Continue merging other unresolved paths [y/n]?' in data:
            self.process.write('n\n')
        elif b'Deleted merge conflict for' in data:
            text = data.data().decode("utf-8")
            isCreated = text.find("(c)reated")
            if isCreated:
                text = text.replace("(c)reated", "created")
            else:
                text = text.replace("(m)odified", "modified")
            text = text.replace("(d)eleted", "deleted")
            text = text.replace("(a)bort", "abort")
            r = QMessageBox.question(self,
                                     qApp.applicationName(),
                                     text,
                                     self.tr("Use &created") if isCreated
                                     else self.tr("Use &modified"),
                                     self.tr("&Deleted file"),
                                     self.tr("&Abort"))
            if r == 0:
                if isCreated:
                    self.process.write("c\n")
                else:
                    self.process.write("m\n")
            elif r == 1:
                self.process.write("d\n")
            else:  # r == 2:
                self.process.write("a\n")
        elif b'Symbolic link merge conflict for' in data:
            text = data.data().decode("utf-8")
            text = text.replace("(l)ocal", "local")
            text = text.replace("(r)emote", "remote")
            text = text.replace("(a)bort", "abort")
            r = QMessageBox.question(self,
                                     qApp.applicationName(),
                                     text,
                                     self.tr("Use &local"),
                                     self.tr("Use &remote"),
                                     self.tr("&Abort"))
            if r == 0:
                self.process.write("l\n")
            elif r == 1:
                self.process.write("r\n")
            else:
                self.process.write("a\n")
        elif b'Was the merge successful [y/n]?' in data:
            # TODO:
            self.process.write("n\n")
        elif b'?' in data:
            # TODO: might have other prompt need yes no
            print(data)

    def __onResolveFinished(self, exitCode, exitStatus):
        if exitCode == 0:
            index = self.view.model().index(self.resolveIndex, 0)
            self.__resolvedIndex(index)

        self.process = None
        curRow = self.resolveIndex
        self.resolveIndex = -1

        self.resolveFinished.emit(RESOLVE_SUCCEEDED if exitCode == 0
                                  else RESOLVE_FAILED)

        # auto next only when success
        if exitCode != 0:
            return

        if not self.cbAutoNext.isChecked():
            return

        if self.resolvedCount == self.view.model().rowCount():
            QMessageBox.information(self, qApp.applicationName(),
                                    self.tr("All resolved!"))
            return

        index = None
        for i in range(curRow + 1, self.view.model().rowCount()):
            index = self.view.model().index(i, 0)
            if index.data(StateRole) == STATE_CONFLICT:
                break
            index = None

        if not index:
            text = self.tr(
                "Resolve reach to the end of list, do you want to resolve from beginning?")
            r = QMessageBox.question(
                self, qApp.applicationName(), text, QMessageBox.Yes, QMessageBox.No)
            if r == QMessageBox.No:
                return
            for i in range(self.view.model().rowCount()):
                index = self.view.model().index(i, 0)
                if index.data(StateRole) == STATE_CONFLICT:
                    break

        # index should not resolved when reach here
        self.view.setCurrentIndex(index)
        self.resolve(index)

    def __onResolveError(self):
        data = self.process.readAllStandardError()
        if b'Unknown merge tool' in data:
            text = self.tr(
                "Unknown merge tool, please check your configuration.")
            QMessageBox.information(self,
                                    qApp.applicationName(),
                                    text)
        else:
            print(data)

    def contextMenuEvent(self, event):
        self.menu.exec(event.globalPos())

    def updateList(self):
        files = Git.conflictFiles()
        self.view.model().clear()
        if files:
            for f in files:
                item = QStandardItem(self.iconConflict, f)
                item.setData(STATE_CONFLICT, StateRole)
                self.view.model().appendRow(item)

            index = self.view.model().index(0, 0)
            self.view.setCurrentIndex(index)
        self.resolvedCount = 0
        self.__updateStatus()

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

        self.resolveIndex = index.row()
        file = index.data()
        args = ["mergetool", "--no-prompt"]

        tools = qApp.instance().settings().mergeToolList()
        # ignored case even on Unix platform
        lowercase_file = file.lower()
        for tool in tools:
            if tool.enabled and tool.isValid():
                if lowercase_file.endswith(tool.suffix.lower()):
                    args.append("--tool={}".format(tool.command))
                    break
        args.append(file)

        # subprocess is not suitable here
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.__onResolveReadyRead)
        self.process.readyReadStandardError.connect(self.__onResolveError)
        self.process.finished.connect(self.__onResolveFinished)
        self.process.setWorkingDirectory(Git.REPO_DIR)
        self.process.start("git", args)

        self.requestResolve.emit(file)
