# -*- coding: utf-8 -*-

import json
from datetime import datetime
from typing import List

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from qgitc.aichathistory import AiChatHistory
from qgitc.applicationbase import qtVersion
from qgitc.colorediconbutton import ColoredIconButton
from qgitc.common import dataDirPath
from qgitc.llm import AiModelBase, AiModelFactory


class AiChatHistoryModel(QAbstractListModel):
    """Custom model for chat histories"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._histories: List[AiChatHistory] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._histories)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._histories):
            return None

        history = self._histories[index.row()]

        if role == Qt.DisplayRole:
            return history.title or self.tr("New Conversation")
        elif role == Qt.UserRole:
            return history
        elif role == Qt.ToolTipRole:
            modelStr = self.tr("Model: ")
            createdStr = self.tr("Created: ")
            return f"{modelStr}{history.modelId}\n{createdStr}{history.timestamp[:19]}"

        return None

    def setData(self, index, value, role=Qt.EditRole):
        if index.isValid() and role == Qt.UserRole:
            self._histories[index.row()] = value
            self.dataChanged.emit(index, index)
            return True
        return False

    def insertHistory(self, row, history: AiChatHistory):
        self.beginInsertRows(QModelIndex(), row, row)
        self._histories.insert(row, history)
        self.endInsertRows()

    def removeHistory(self, row):
        if 0 <= row < len(self._histories):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._histories[row]
            self.endRemoveRows()

    def clear(self):
        self.beginResetModel()
        self._histories.clear()
        self.endResetModel()

    def setHistories(self, histories: List[AiChatHistory]):
        self.beginResetModel()
        self._histories = histories.copy()
        self.endResetModel()

    def getHistory(self, row) -> AiChatHistory:
        if 0 <= row < len(self._histories):
            return self._histories[row]
        return None

    def findHistoryRow(self, historyId: str) -> int:
        for i, history in enumerate(self._histories):
            if history.historyId == historyId:
                return i
        return -1

    def moveToTop(self, row):
        if row > 0:
            newRow = 0
            # Check if we should keep "New Conversation" at top
            if len(self._histories) > 1:
                firstHistory = self._histories[0]
                if not firstHistory.messages and firstHistory.title in ['', self.tr("New Conversation")]:
                    newRow = 1

            if newRow != row:
                self.beginMoveRows(QModelIndex(), row, row,
                                   QModelIndex(), newRow)
                history = self._histories.pop(row)
                self._histories.insert(newRow, history)
                self.endMoveRows()
                return newRow
        return row


class AiChatHistoryFilterModel(QSortFilterProxyModel):
    """Filter model for searching chat histories"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._searchText = ""
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)

    def setSearchText(self, text: str):
        self._searchText = text.strip().lower()
        if qtVersion() >= (6, 10, 0):
            self.beginFilterChange()
            self.endFilterChange()
        else:
            self.invalidateFilter()

    def filterAcceptsRow(self, sourceRow, sourceParent):
        if not self._searchText:
            return True

        model = self.sourceModel()
        index = model.index(sourceRow, 0, sourceParent)
        history: AiChatHistory = model.data(index, Qt.UserRole)
        if not history:
            return False

        # Search in title
        if self._searchText in history.title.lower():
            return True

        # Search in messages
        for message in history.messages:
            content: str = message.get('content', '')
            if self._searchText in content.lower():
                return True

        return False


class AiChatHistoryPanel(QWidget):

    requestNewChat = Signal()
    historySelectionChanged = Signal(AiChatHistory)
    historyRemoved = Signal(str)  # historyId

    def __init__(self, parent=None):
        super().__init__(parent)
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
        mainLayout.addWidget(self._searchEdit)

        # History list with model/view
        self._historyModel = AiChatHistoryModel(self)
        self._filterModel = AiChatHistoryFilterModel(self)
        self._filterModel.setSourceModel(self._historyModel)

        self._historyList = QListView(self)
        self._historyList.setModel(self._filterModel)
        self._historyList.setMinimumWidth(150)
        self._historyList.setContextMenuPolicy(Qt.CustomContextMenu)
        self._historyList.customContextMenuRequested.connect(
            self._showContextMenu)
        self._historyList.selectionModel().currentChanged.connect(
            self._onHistorySelectionChanged)
        mainLayout.addWidget(self._historyList)

    def _onSearchTextChanged(self, text: str):
        """Handle search text change"""
        self._filterModel.setSearchText(text)

        if (
            self._historyModel.rowCount() > 0
            and not self._historyList.currentIndex().isValid()
        ):
            self._historyList.setCurrentIndex(self._filterModel.index(0, 0))

    def _onHistorySelectionChanged(self, current: QModelIndex, previous: QModelIndex):
        """Handle history selection change"""
        chatHistory = None
        if current.isValid() and current != previous:
            chatHistory = self._filterModel.data(current, Qt.UserRole)

        self.historySelectionChanged.emit(chatHistory)

    def clear(self):
        self._historyModel.clear()
        self._searchEdit.clear()

    def loadHistories(self, histories: List[AiChatHistory]):
        self.clear()

        # Sort histories by timestamp (newest first)
        sorted_histories = sorted(
            histories,
            key=lambda h: h.timestamp,
            reverse=True
        )

        self._historyModel.setHistories(sorted_histories)

    def currentHistory(self) -> AiChatHistory:
        """Get the currently selected history item"""
        current = self._historyList.currentIndex()
        if current.isValid():
            return self._filterModel.data(current, Qt.UserRole)
        return None

    def updateTitle(self, historyId: str, newTitle: str):
        """Update the title of a history item"""
        row = self._historyModel.findHistoryRow(historyId)
        if row >= 0:
            sourceIndex = self._historyModel.index(row, 0)
            chatHistory: AiChatHistory = self._historyModel.data(
                sourceIndex, Qt.UserRole)
            if chatHistory:
                chatHistory.title = newTitle
                self._historyModel.setData(
                    sourceIndex, chatHistory, Qt.UserRole)
                return chatHistory
        return None

    def updateCurrentModelId(self, modelId: str):
        current = self._historyList.currentIndex()
        if not current.isValid():
            return None

        sourceIndex = self._filterModel.mapToSource(current)
        if not sourceIndex.isValid():
            return None

        chatHistory: AiChatHistory = self._historyModel.data(
            sourceIndex, Qt.UserRole)
        if chatHistory and chatHistory.modelId != modelId:
            chatHistory.modelId = modelId
            self._historyModel.setData(sourceIndex, chatHistory, Qt.UserRole)
            return chatHistory

        return None

    def updateCurrentHistory(self, model: AiModelBase):
        """Update the current selected history item"""
        current = self._historyList.currentIndex()
        if not current.isValid():
            return None

        # Get the source index from the filter model
        sourceIndex = self._filterModel.mapToSource(current)
        if not sourceIndex.isValid():
            return None

        messages = []
        for message in model.history:
            messages.append({
                'role': message.role.name.lower(),
                'content': message.message
            })

        chatHistory: AiChatHistory = self._historyModel.data(
            sourceIndex, Qt.UserRole)
        if chatHistory:
            chatHistory.messages = messages
            chatHistory.modelKey = AiModelFactory.modelKey(model)
            chatHistory.modelId = model.modelId or model.name
            chatHistory.timestamp = datetime.now().isoformat()
            self._historyModel.setData(sourceIndex, chatHistory, Qt.UserRole)

            # Move to top
            newRow = self._historyModel.moveToTop(sourceIndex.row())

            # Update selection to the new position
            newSourceIndex = self._historyModel.index(newRow, 0)
            newFilterIndex = self._filterModel.mapFromSource(newSourceIndex)
            if newFilterIndex.isValid():
                self._historyList.setCurrentIndex(newFilterIndex)

        return chatHistory

    def setCurrentHistory(self, historyId: str):
        """Set the current selected history by ID"""
        row = self._historyModel.findHistoryRow(historyId)
        if row >= 0:
            sourceIndex = self._historyModel.index(row, 0)
            filterIndex = self._filterModel.mapFromSource(sourceIndex)
            if filterIndex.isValid():
                self._historyList.setCurrentIndex(filterIndex)

    def insertHistoryAtTop(self, history: AiChatHistory, select: bool = True):
        self._historyModel.insertHistory(0, history)
        if select:
            # Select the newly inserted item
            sourceIndex = self._historyModel.index(0, 0)
            filterIndex = self._filterModel.mapFromSource(sourceIndex)
            if filterIndex.isValid():
                self._historyList.setCurrentIndex(filterIndex)

    def _showContextMenu(self, position):
        """Show context menu for history list"""
        index = self._historyList.indexAt(position)
        if not index.isValid():
            return

        chatHistory = self._filterModel.data(index, Qt.UserRole)
        if not chatHistory:
            return

        menu = QMenu(self)
        exportAction = menu.addAction(self.tr("Export Conversation"))
        exportAction.triggered.connect(
            lambda: self._exportHistory(chatHistory))

        menu.addSeparator()

        removeAction = menu.addAction(self.tr("Remove Conversation"))
        removeAction.triggered.connect(
            lambda: self._removeHistory(index, chatHistory))

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
            # Map filter index to source index
            sourceIndex = self._filterModel.mapToSource(filterIndex)
            if sourceIndex.isValid():
                # Remove from model
                self._historyModel.removeHistory(sourceIndex.row())
                # Emit signal for external handling (e.g., delete from storage)
                self.historyRemoved.emit(chatHistory.historyId)
