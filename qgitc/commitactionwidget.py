# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QHeaderView, QMessageBox, QTableView, QWidget

from qgitc.applicationbase import ApplicationBase
from qgitc.comboboxitemdelegate import ComboBoxItemDelegate
from qgitc.commitactiontablemodel import CommitActionTableModel
from qgitc.ui_commitactionwidget import Ui_CommitActionWidget


class CommitActionWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ui = Ui_CommitActionWidget()
        self.ui.setupUi(self)

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

    def _onAddActionClicked(self):
        self._tableViewAddItem(
            self.ui.tvActions, CommitActionTableModel.Col_Cmd)

    def _onDeleteActionClicked(self):
        self._tableViewDeleteItem(self.ui.tvActions)

    def _tableViewAddItem(self, tableView: QTableView, editCol: int):
        model = tableView.model()
        row = model.rowCount()
        if not model.insertRow(row):
            return
        index = model.index(row, editCol)
        tableView.edit(index)

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

    def setActions(self, actions):
        model: CommitActionTableModel = self.ui.tvActions.model()
        model.setRawData(actions)

    def actions(self):
        model: CommitActionTableModel = self.ui.tvActions.model()
        return model.rawData()
