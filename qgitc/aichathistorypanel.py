# -*- coding: utf-8 -*-

import json

from PySide6.QtCore import QEvent, QItemSelectionModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from qgitc.aichathistory import AiChatHistory
from qgitc.aichathistorymodel import AiChatHistoryFilterModel, AiChatHistoryModel
from qgitc.aichathistorystore import AiChatHistoryStore
from qgitc.colorediconbutton import ColoredIconButton
from qgitc.common import dataDirPath


class AiChatHistoryPanel(QWidget):

    requestNewChat = Signal()
    historySelectionChanged = Signal(AiChatHistory)
    historyActivated = Signal(AiChatHistory)

    def __init__(self, store: AiChatHistoryStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._setupUi()

    def _setupUi(self):
        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.setSpacing(4)

        icon = QIcon(dataDirPath() + "/icons/chat-add-on.svg")
        self._btnNewChat = ColoredIconButton(
            icon, self.tr("New Conversation"), self)
        self._btnNewChat.clicked.connect(self.requestNewChat)
        mainLayout.addWidget(self._btnNewChat)

        self._btnNewChat.setShortcut(QKeySequence.New)
        shortcut = self._btnNewChat.shortcut().toString(QKeySequence.NativeText)
        self._btnNewChat.setToolTip(
            self.tr("Start a new conversation ({})").format(shortcut))

        # Search bar
        self._searchEdit = QLineEdit(self)
        self._searchEdit.setPlaceholderText(self.tr("Search conversations..."))
        self._searchEdit.setClearButtonEnabled(True)
        self._searchEdit.textChanged.connect(self._onSearchTextChanged)
        self._searchEdit.installEventFilter(self)
        mainLayout.addWidget(self._searchEdit)

        # History list with model/view
        self._historyModel = self._store.model()
        self._filterModel = AiChatHistoryFilterModel(self)
        self._filterModel.setSourceModel(self._historyModel)

        self._historyList = QListView(self)
        self._historyList.setModel(self._filterModel)
        self._historyList.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._historyList.setContextMenuPolicy(Qt.CustomContextMenu)
        self._historyList.customContextMenuRequested.connect(
            self._showContextMenu)
        self._historyList.selectionModel().currentChanged.connect(
            self._onHistorySelectionChanged)
        self._historyList.clicked.connect(self._onHistoryActivated)
        self._historyList.activated.connect(self._onHistoryActivated)
        mainLayout.addWidget(self._historyList)

        self._compactMode = False

    def clearFilter(self, preserveSelection: bool = True):
        """Clear the search filter; optionally keep the currently selected history."""
        keepId = None
        if preserveSelection:
            cur = self.currentHistory()
            keepId = cur.historyId if cur else None

        # Avoid triggering the default selection auto-behavior from textChanged.
        self._searchEdit.blockSignals(True)
        self._searchEdit.setText("")
        self._searchEdit.blockSignals(False)

        self._filterModel.setSearchText("")

        if keepId:
            self.setCurrentHistory(keepId)
        elif (
            self._historyModel.rowCount() > 0
            and not self._historyList.currentIndex().isValid()
        ):
            self._selectSingleIndex(self._filterModel.index(0, 0))

    def _moveSelection(self, deltaRows: int):
        if self._filterModel.rowCount() <= 0:
            return

        cur = self._historyList.currentIndex()
        row = cur.row() if cur.isValid() else 0
        newRow = max(
            0, min(self._filterModel.rowCount() - 1, row + int(deltaRows)))
        self._selectSingleIndex(self._filterModel.index(newRow, 0))

    def eventFilter(self, obj, event):
        if obj == self._searchEdit and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
                if key == Qt.Key_Up:
                    self._moveSelection(-1)
                elif key == Qt.Key_Down:
                    self._moveSelection(1)
                else:
                    # Approximate page size based on visible rows.
                    rowHeight = self._historyList.sizeHintForRow(0)
                    if rowHeight <= 0:
                        rowHeight = 30
                    page = max(
                        1, int(self._historyList.viewport().height() / rowHeight))
                    self._moveSelection(-page if key ==
                                        Qt.Key_PageUp else page)
                return True

            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._onHistoryActivated(self._historyList.currentIndex())
                return True

        return super().eventFilter(obj, event)

    def setCompactMode(self, compact: bool):
        """Compact mode for embedded UI: hides controls and reduces vertical chrome."""
        self._compactMode = compact
        self._btnNewChat.setVisible(not self._compactMode)
        self._searchEdit.setVisible(not self._compactMode)

        layout: QVBoxLayout = self.layout()
        layout.setContentsMargins(0, 0, 0, 0)
        if self._compactMode:
            layout.setSpacing(0)
        else:
            layout.setSpacing(4)

    def historyModel(self) -> AiChatHistoryModel:
        """Access the underlying history model (for shared views)."""
        return self._historyModel

    def setMaxVisibleRows(self, maxRows: int):
        """Limit the list height so only ~maxRows are visible (with scroll for the rest)."""
        maxRows = max(1, int(maxRows))
        rowHeight = self._historyList.sizeHintForRow(0)
        if rowHeight <= 0:
            rowHeight = 30
        self._historyList.setVerticalScrollMode(
            QAbstractItemView.ScrollPerPixel)
        height = maxRows * rowHeight + (maxRows - 1) + 4
        self._historyList.setFixedHeight(height)

    def setSelectionMode(self, mode: QAbstractItemView.SelectionMode):
        """Set the selection mode for the history list view."""
        self._historyList.setSelectionMode(mode)

    def _onSearchTextChanged(self, text: str):
        """Handle search text change"""
        self._filterModel.setSearchText(text)

        if (
            self._historyModel.rowCount() > 0
            and not self._historyList.currentIndex().isValid()
        ):
            self._selectSingleIndex(self._filterModel.index(0, 0))

    def _selectSingleIndex(self, filterIndex: QModelIndex):
        """Select exactly one row in the filtered view.

        The history list uses ExtendedSelection to support multi-delete, but
        programmatic navigation (switching chats) should behave like a single
        selection and clear any previous selection highlights.
        """
        if not filterIndex.isValid():
            return

        selModel = self._historyList.selectionModel()
        if selModel is None:
            self._historyList.setCurrentIndex(filterIndex)
            return

        selModel.setCurrentIndex(
            filterIndex,
            QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Current,
        )

    def _onHistorySelectionChanged(self, current: QModelIndex, previous: QModelIndex):
        """Handle history selection change"""
        chatHistory = None
        if current.isValid() and current != previous:
            chatHistory = self._filterModel.data(current, Qt.UserRole)

        self.historySelectionChanged.emit(chatHistory)

    def _onHistoryActivated(self, index: QModelIndex):
        """Emit explicit activation (click/enter) without relying on selection changes."""
        if not index or not index.isValid():
            return
        chatHistory = self._filterModel.data(index, Qt.UserRole)
        if chatHistory:
            self.historyActivated.emit(chatHistory)

    def clear(self):
        self._searchEdit.clear()

        # Clear selection without affecting the shared model.
        selModel = self._historyList.selectionModel()
        if selModel is not None:
            selModel.clearSelection()

    def currentHistory(self) -> AiChatHistory:
        """Get the currently selected history item"""
        current = self._historyList.currentIndex()
        if current.isValid():
            return self._filterModel.data(current, Qt.UserRole)
        return None

    def updateTitle(self, historyId: str, newTitle: str):
        return self._store.updateTitle(historyId, newTitle)

    def updateCurrentModelId(self, modelId: str):
        current = self._historyList.currentIndex()
        if not current.isValid():
            return None

        sourceIndex = self._filterModel.mapToSource(current)
        if not sourceIndex.isValid():
            return None

        chatHistory: AiChatHistory = self._historyModel.data(
            sourceIndex, Qt.UserRole)
        if not chatHistory:
            return None

        return self._store.updateCurrentModelId(chatHistory.historyId, modelId)

    def setCurrentHistory(self, historyId: str):
        """Set the current selected history by ID"""
        row = self._historyModel.findHistoryRow(historyId)
        if row >= 0:
            sourceIndex = self._historyModel.index(row, 0)
            filterIndex = self._filterModel.mapFromSource(sourceIndex)
            if filterIndex.isValid():
                self._selectSingleIndex(filterIndex)

    def insertHistoryAtTop(self, history: AiChatHistory, select: bool = True):
        self._store.insertHistoryAtTop(history)
        if select:
            # Select the newly inserted item
            sourceIndex = self._historyModel.index(0, 0)
            filterIndex = self._filterModel.mapFromSource(sourceIndex)
            if filterIndex.isValid():
                self._selectSingleIndex(filterIndex)

    def _showContextMenu(self, position):
        """Show context menu for history list"""
        index = self._historyList.indexAt(position)
        selectedIndexes = self._historyList.selectionModel().selectedIndexes()

        menu = QMenu(self)

        # Export action (only for single selection)
        if index.isValid() and len(selectedIndexes) == 1:
            chatHistory = self._filterModel.data(index, Qt.UserRole)
            if chatHistory:
                exportAction = menu.addAction(self.tr("Export Conversation"))
                exportAction.triggered.connect(
                    lambda: self._exportHistory(chatHistory))
                menu.addSeparator()

        # Delete selected conversations
        if selectedIndexes:
            if len(selectedIndexes) == 1:
                deleteText = self.tr("Delete Conversation")
            else:
                deleteText = self.tr("Delete {} Conversations").format(
                    len(selectedIndexes))
            deleteSelectedAction = menu.addAction(deleteText)
            deleteSelectedAction.triggered.connect(
                self._removeSelectedHistories)

        # Delete all conversations
        if self._historyModel.rowCount() > 0:
            if selectedIndexes:
                menu.addSeparator()
            deleteAllAction = menu.addAction(
                self.tr("Delete All Conversations"))
            deleteAllAction.triggered.connect(self._removeAllHistories)

        if menu.actions():
            menu.exec(self._historyList.mapToGlobal(position))

    def _exportHistory(self, chatHistory: AiChatHistory):
        """Export a chat history to JSON file"""
        try:
            # Create a safe filename from the title
            safe_title = "".join(
                c for c in chatHistory.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            if not safe_title:
                safe_title = "conversation"

            suggested_filename = f"{safe_title}_{chatHistory.timestamp[:10]}.json"

            filename, _ = QFileDialog.getSaveFileName(
                self,
                self.tr("Export Conversation"),
                suggested_filename,
                self.tr("JSON Files (*.json);;All Files (*)")
            )

            if filename:
                data = chatHistory.toDict()
                del data['historyId']
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.warning(
                self,
                self.tr("Export Error"),
                self.tr("Failed to export conversation:\n{}").format(str(e))
            )

    def _removeHistory(self, filterIndex: QModelIndex, chatHistory: AiChatHistory):
        """Remove a chat history item"""
        reply = QMessageBox.question(
            self,
            self.tr("Remove Conversation"),
            self.tr("Are you sure you want to remove the conversation '{}'?\n\nThis action cannot be undone.").format(
                chatHistory.title or self.tr("Untitled")),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._store.remove(chatHistory.historyId)

    def _removeSelectedHistories(self):
        """Remove all selected chat history items"""
        selectedIndexes = self._historyList.selectionModel().selectedIndexes()
        if not selectedIndexes:
            return

        # Confirm deletion
        if len(selectedIndexes) == 1:
            chatHistory = self._filterModel.data(
                selectedIndexes[0], Qt.UserRole)
            message = self.tr("Are you sure you want to delete the conversation '{}'?\n\nThis action cannot be undone.").format(
                chatHistory.title or self.tr("Untitled"))
            title = self.tr("Delete Conversation")
        else:
            message = self.tr("Are you sure you want to delete {} conversations?\n\nThis action cannot be undone.").format(
                len(selectedIndexes))
            title = self.tr("Delete Conversations")

        reply = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            historyIds = []
            for filterIndex in selectedIndexes:
                chatHistory = self._filterModel.data(filterIndex, Qt.UserRole)
                if chatHistory:
                    historyIds.append(chatHistory.historyId)
            if historyIds:
                self._store.removeMany(historyIds)

    def _removeAllHistories(self):
        """Remove all chat history items"""
        totalCount = self._historyModel.rowCount()
        if totalCount == 0:
            return

        reply = QMessageBox.question(
            self,
            self.tr("Delete All Conversations"),
            self.tr("Are you sure you want to delete all {} conversations?\n\nThis action cannot be undone.").format(
                totalCount),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._store.clearAll()
