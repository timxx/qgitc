# -*- coding: utf-8 -*-

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFontDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FontChooserWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)

        mainLayout.addWidget(QLabel(self.tr("Fonts:")))

        self._fontList = QListView()
        self._fontList.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._model = QStringListModel(self)
        self._fontList.setModel(self._model)

        self._fontList.setDragEnabled(True)
        self._fontList.setAcceptDrops(True)
        self._fontList.setDropIndicatorShown(True)
        self._fontList.setDragDropMode(QAbstractItemView.InternalMove)
        self._fontList.setDefaultDropAction(Qt.MoveAction)

        mainLayout.addWidget(self._fontList)

        btnLayout = QHBoxLayout()

        btnAdd = QPushButton(self.tr("&Add"))
        btnAdd.clicked.connect(self._onAddFont)
        btnLayout.addWidget(btnAdd)

        btnDel = QPushButton(self.tr("&Remove"))
        btnDel.clicked.connect(self._onRemoveFont)
        btnLayout.addWidget(btnDel)

        btnLayout.addStretch()
        mainLayout.addLayout(btnLayout)

        hbox = QHBoxLayout()
        hbox.addWidget(QLabel(self.tr("Font Size:")))
        self._cbFontSize = QComboBox(self)
        hbox.addWidget(self._cbFontSize)
        hbox.addStretch()

        mainLayout.addLayout(hbox)
        self._initFontSizes()

    def _onAddFont(self):
        ok, font = QFontDialog.getFont(self)
        if ok:
            family = font.family()
            if family not in self._model.stringList():
                self._model.insertRow(self._model.rowCount())
                self._model.setData(self._model.index(self._model.rowCount() - 1), family)

    def _onRemoveFont(self):
        selected = self._fontList.selectedIndexes()
        selected.sort()
        for item in reversed(selected):
            self._model.removeRow(item.row())

    def font(self):
        font = QFont()
        font.setPointSize(int(self._cbFontSize.currentText()))
        families = self._model.stringList()
        font.setFamilies(families)
        return font

    def setFont(self, font: QFont):
        index = self._cbFontSize.findData(font.pointSize())
        self._cbFontSize.setCurrentIndex(index)
        self._model.setStringList(font.families())

    def _initFontSizes(self):
        sizes = QFontDatabase.standardSizes()
        sizes.sort()

        for size in sizes:
            self._cbFontSize.addItem(str(size), size)
