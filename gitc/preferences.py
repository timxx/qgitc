# -*- coding: utf-8 -*-

from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PySide2.QtCore import *

from .ui_preferences import *
from .mergetool import MergeTool
from .comboboxitemdelegate import ComboBoxItemDelegate
from .stylehelper import dpiScaled


class ToolTableModel(QAbstractTableModel):
    Col_Scenes = 0
    Col_Suffix = 1
    Col_Tool = 2

    suffixExists = Signal(str)

    def __init__(self, parent=None):
        super(ToolTableModel, self).__init__(parent)

        self._data = []
        self._scenes = {MergeTool.Nothing: self.tr("Disabled"),
                        MergeTool.CanDiff: self.tr("Diff"),
                        MergeTool.CanMerge: self.tr("Merge"),
                        MergeTool.Both: self.tr("Both")}

    def __checkSuffix(self, row, suffix):
        for i in range(len(self._data)):
            if i == row:
                continue
            tool = self._data[i]
            if tool.suffix == suffix:
                return False

        return True

    def columnCount(self, parent=QModelIndex()):
        return 3

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        if role != Qt.DisplayRole:
            return None

        if section == self.Col_Scenes:
            return self.tr("Scenes")
        if section == self.Col_Suffix:
            return self.tr("Suffix")
        if section == self.Col_Tool:
            return self.tr("Tool")

        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        f |= Qt.ItemIsEditable

        return f

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        tool = self._data[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == self.Col_Suffix:
                return tool.suffix
            if col == self.Col_Tool:
                return tool.command
            if col == self.Col_Scenes:
                return self._scenes[tool.capabilities]

        return None

    def setData(self, index, value, role=Qt.EditRole):
        row = index.row()
        col = index.column()
        tool = self._data[row]

        if role == Qt.EditRole:
            value = value.strip()
            if not value:
                return False
            if col == self.Col_Suffix:
                if not self.__checkSuffix(row, value):
                    self.suffixExists.emit(value)
                    return False
                tool.suffix = value
            elif col == self.Col_Tool:
                tool.command = value
            elif col == self.Col_Scenes:
                idx = list(self._scenes.values()).index(value)
                tool.capabilities = list(self._scenes.keys())[idx]
        else:
            return False

        self._data[row] = tool
        return True

    def insertRows(self, row, count, parent=QModelIndex()):
        self.beginInsertRows(parent, row, row + count - 1)

        for i in range(count):
            self._data.insert(row, MergeTool(MergeTool.Both))

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

    def rawData(self):
        return self._data

    def setRawData(self, data):
        parent = QModelIndex()

        if self._data:
            self.beginRemoveRows(parent, 0, len(self._data) - 1)
            self._data = []
            self.endRemoveRows()

        if data:
            self.beginInsertRows(parent, 0, len(data) - 1)
            self._data = data
            self.endInsertRows()

    def getSceneNames(self):
        return self._scenes.values()


class Preferences(QDialog):

    def __init__(self, settings, parent=None):
        super(Preferences, self).__init__(parent)

        self.ui = Ui_Preferences()
        self.ui.setupUi(self)
        self.settings = settings

        self.resize(dpiScaled(QSize(529, 316)))

        model = ToolTableModel(self)
        self.ui.tableView.setModel(model)
        self.ui.tableView.horizontalHeader().setSectionResizeMode(
            ToolTableModel.Col_Tool,
            QHeaderView.Stretch)

        delegate = ComboBoxItemDelegate(model.getSceneNames())
        self.ui.tableView.setItemDelegateForColumn(
            ToolTableModel.Col_Scenes, delegate)

        self.ui.cbFamilyLog.currentFontChanged.connect(
            self.__onFamilyChanged)
        self.ui.cbFamilyDiff.currentFontChanged.connect(
            self.__onFamilyChanged)

        self.ui.btnAdd.clicked.connect(
            self.__onBtnAddClicked)
        self.ui.btnDelete.clicked.connect(
            self.__onBtnDeleteClicked)

        self.ui.tableView.model().suffixExists.connect(
            self.__onSuffixExists)

        # default to General tab
        self.ui.tabWidget.setCurrentIndex(0)

        self.__initSettings()

    def __initSettings(self):
        # TODO: delay load config for each tab
        font = self.settings.logViewFont()
        self.ui.cbFamilyLog.setCurrentFont(font)
        self.ui.cbFamilyLog.currentFontChanged.emit(font)

        font = self.settings.diffViewFont()
        self.ui.cbFamilyDiff.setCurrentFont(font)
        self.ui.cbFamilyDiff.currentFontChanged.emit(font)

        self.ui.colorA.setColor(self.settings.commitColorA())
        self.ui.colorB.setColor(self.settings.commitColorB())

        self.ui.leCommitUrl.setText(self.settings.commitUrl())
        self.ui.leBugUrl.setText(self.settings.bugUrl())
        self.ui.leBugPattern.setText(self.settings.bugPattern())

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

    def __updateFontSizes(self, family, size, cb):
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

    def __onFamilyChanged(self, font):
        cbSize = self.ui.cbSizeLog
        size = self.settings.logViewFont().pointSize()
        if self.sender() == self.ui.cbFamilyDiff:
            cbSize = self.ui.cbSizeDiff
            size = self.settings.diffViewFont().pointSize()

        self.__updateFontSizes(font.family(), size, cbSize)

    def __onBtnAddClicked(self, checked=False):
        model = self.ui.tableView.model()
        row = model.rowCount()
        if not model.insertRow(row):
            return
        index = model.index(row, ToolTableModel.Col_Suffix)
        self.ui.tableView.edit(index)

    def __onBtnDeleteClicked(self, checked=False):
        indexes = self.ui.tableView.selectionModel().selectedRows()
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
            self.ui.tableView.model().removeRow(index.row())

    def __onSuffixExists(self, suffix):
        QMessageBox.information(self,
                                qApp.applicationName(),
                                self.tr("The suffix you specify is already exists."))

    def save(self):
        # TODO: only update those values that really changed
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

        value = self.ui.leCommitUrl.text().strip()
        self.settings.setCommitUrl(value)

        value = self.ui.leBugUrl.text().strip()
        self.settings.setBugUrl(value)

        value = self.ui.leBugPattern.text().strip()
        self.settings.setBugPattern(value)

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
