# -*- coding: utf-8 -*-

import re

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.gitutils import Git


class BugPattern:
    def __init__(self, pattern=None, url=None):
        self.pattern = pattern
        self.url = url
        self.error = None


class BugPatternModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []

    def columnCount(self, parent=QModelIndex()):
        return 2

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        if role != Qt.DisplayRole:
            return None

        if section == 0:
            return self.tr("Bug Pattern")
        if section == 1:
            return self.tr("Bug Url")

        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        f |= Qt.ItemIsEditable

        return f

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        data = self._data[index.row()]
        col = index.column()
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return data.pattern if col == 0 else data.url
        if col == 0:
            if role == Qt.ForegroundRole:
                return ApplicationBase.instance().palette().windowText() if data.error is None else ApplicationBase.instance().colorSchema().ErrorText
            elif role == Qt.ToolTipRole:
                return data.error

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False

        value = value.strip()
        if not value:
            return False

        row = index.row()
        col = index.column()

        if col == 0:
            try:
                if value:
                    re.compile(value)
                self._data[row].error = None
            except re.error as e:
                self._data[row].error = self.tr(
                    "Invalid regular expression: ") + e.msg
            self._data[row].pattern = value
        elif col == 1:
            self._data[row].url = value

        return True

    def insertRows(self, row, count, parent=QModelIndex()):
        self.beginInsertRows(parent, row, row + count - 1)

        for i in range(count):
            self._data.insert(row, BugPattern())

        self.endInsertRows()

        return True

    def removeRows(self, row, count, parent=QModelIndex()):
        if row >= len(self._data):
            return False

        self.beginRemoveRows(parent, row, row + count - 1)

        for i in range(count - 1 + row, row - 1, -1):
            if i < len(self._data):
                del self._data[i]

        self.endRemoveRows()

        return True

    def setPatterns(self, patterns):
        parent = QModelIndex()

        if self._data:
            self.beginRemoveRows(parent, 0, len(self._data) - 1)
            self._data = []
            self.endRemoveRows()

        if patterns:
            self.beginInsertRows(parent, 0, len(patterns) - 1)
            for pattern, url in patterns:
                self._data.append(BugPattern(pattern, url))
            self.endInsertRows()

    def getPatterns(self):
        patterns = []
        for d in self._data:
            if not d.pattern and not d.url:
                continue
            patterns.append((d.pattern, d.url))
        return patterns

    def addPattern(self, pattern, url):
        for d in self._data:
            if d.pattern == pattern and d.url == url:
                return

        parent = QModelIndex()
        last = len(self._data)
        self.beginInsertRows(parent, last, last)
        self._data.append(BugPattern(pattern, url))
        self.endInsertRows()


class LinkEditWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        gridLayout = QGridLayout()
        label = QLabel(self.tr("Co&mmit Url:"), self)
        gridLayout.addWidget(label, 0, 0, 1, 1)

        self.leCommitUrl = QLineEdit(self)
        gridLayout.addWidget(self.leCommitUrl, 0, 1, 1, 1)
        label.setBuddy(self.leCommitUrl)

        layout.addLayout(gridLayout)

        self._setupUi()

    def _setupUi(self):
        model = BugPatternModel()
        self.tableView = QTableView(self)
        self.tableView.setModel(model)
        self.tableView.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tableView.setSelectionBehavior(QTableView.SelectRows)

        self.layout().addWidget(self.tableView)

        hbox = QHBoxLayout()
        btnAdd = QPushButton(self.tr("&Add"), self)
        btnRemove = QPushButton(self.tr("&Remove"), self)
        btnDetect = QPushButton(self.tr("Auto &Detect"), self)
        hbox.addWidget(btnAdd)
        hbox.addWidget(btnRemove)
        hbox.addWidget(btnDetect)
        hbox.addSpacerItem(QSpacerItem(
            0, 0, QSizePolicy.Expanding, QSizePolicy.Fixed))
        self.layout().addLayout(hbox)

        btnAdd.clicked.connect(self._onBtnAddClicked)
        btnRemove.clicked.connect(self._onBtnRemoveClicked)

        btnDetect.clicked.connect(
            self._onBtnDetectClicked)

    def commitUrl(self):
        return self.leCommitUrl.text()

    def setCommitUrl(self, url):
        self.leCommitUrl.setText(url)

    def setBugPatterns(self, patterns):
        self.tableView.model().setPatterns(patterns)

    def bugPatterns(self):
        return self.tableView.model().getPatterns()

    def _onBtnAddClicked(self, checked=False):
        model = self.tableView.model()
        row = model.rowCount()
        if not model.insertRow(row):
            return
        index = model.index(row, 0)
        self.tableView.edit(index)

    def _onBtnRemoveClicked(self, checked=False):
        indexes = self.tableView.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(
                self,
                ApplicationBase.instance().applicationName(),
                self.tr("Please select one row at least to remove."))
            return

        if len(indexes) > 1:
            text = self.tr(
                "You have selected more than one row, do you really want remove all of them?")
            r = QMessageBox.question(self, ApplicationBase.instance().applicationName(),
                                     text,
                                     QMessageBox.Yes,
                                     QMessageBox.No)
            if r != QMessageBox.Yes:
                return

        indexes.sort(reverse=True)
        for index in indexes:
            self.tableView.model().removeRow(index.row())

    def _onBtnDetectClicked(self):
        url, name, user = self._parseRepo()
        if not url or not name:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                self.tr("Unable to detect current repo's name"))
            return

        model = self.tableView.model()
        if self._isQt5Repo(name):
            model.addPattern(
                "(QTBUG-[0-9]{5,6})", "https://bugreports.qt.io/browse/")
            if user and self._isGithubRepo(url):
                self.setCommitUrl(
                    "https://github.com/{}/{}/commit/".format(user, name))
        elif self._isGithubRepo(url):
            if user:
                model.addPattern(
                    "(#([0-9]+))", "https://github.com/{}/{}/issues/".format(user, name))
                self.setCommitUrl(
                    "https://github.com/{}/{}/commit/".format(user, name))
        elif self._isGiteeRepo(url):
            if user:
                model.addPattern(
                    "(I[A-Z0-9]{4,})", "https://gitee.com/{}/{}/issues/".format(user, name))
                self.setCommitUrl(
                    "https://gitee.com/{}/{}/commit/".format(user, name))
        elif self._isGitlabRepo(url):
            if user:
                model.addPattern(
                    "(#([0-9]+))", "https://gitlab.com/{}/{}/-/issues/".format(user, name))
                self.setCommitUrl(
                    "https://gitlab.com/{}/{}/-/commit/".format(user, name))
        else:
            QMessageBox.critical(
                self, self.window().windowTitle(),
                self.tr("Unsupported repository"))

    def _parseRepo(self):
        url = Git.repoUrl()
        name = None
        user = None
        if not url:
            return None, None, None

        index = url.rfind('/')
        if index != -1:
            name = url[index+1:]
            if name.endswith(".git"):
                name = name[:-4]

        # unsupported
        if index == -1 or url.startswith("ssh://"):
            return url, name, user

        if url.startswith("git@"):
            index2 = url.rfind(':', 0, index)
            if index2 != -1:
                user = url[index2+1:index]
        else:
            index2 = url.rfind('/', 0, index)
            if index2 != -1:
                user = url[index2+1:index]

        return url, name, user

    def _isQt5Repo(self, repoName):
        return repoName in [
            "qt5", "qt3d", "qtactiveqt", "qtandroidextras",
            "qtbase", "qtcanvas3d", "qtcharts",
            "qtconnectivity", "qtdatavis3d", "qtdeclarative",
            "qtdoc", "qtgamepad", "qtgraphicaleffects",
            "qtimageformats", "qtlocation", "qtmacextras",
            "qtmultimedia", "qtnetworkauth", "qtpurchasing",
            "qtqa", "qtquickcontrols", "qtquickcontrols2",
            "qtremoteobjects", "qtrepotools", "qtscript",
            "qtscxml", "qtsensors", "qtserialbus",
            "qtserialport", "qtspeech", "qtsvg",
            "qttools", "qttranslations", "qtvirtualkeyboard",
            "qtwayland", "qtwebchannel", "qtwebengine",
            "qtwebglplugin", "qtwebsockets", "qtwebview",
            "qtwinextras", "qtx11extras", "qtxmlpatterns"]

    def _isGithubRepo(self, repoUrl):
        return repoUrl.startswith("git@github.com:") or \
            repoUrl.startswith("https://github.com/")

    def _isGiteeRepo(self, repoUrl):
        return repoUrl.startswith("git@gitee.com:") or \
            repoUrl.startswith("https://gitee.com/")

    def _isGitlabRepo(self, repoUrl):
        return repoUrl.startswith("git@gitlab.com:") or \
            repoUrl.startswith("https://gitlab.com/")
