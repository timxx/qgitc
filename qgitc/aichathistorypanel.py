# -*- coding: utf-8 -*-

from datetime import datetime
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qgitc.aichathistory import AiChatHistory
from qgitc.llm import AiModelBase, AiModelFactory


class AiChatHistoryPanel(QWidget):

    requestNewChat = Signal()
    historySelectionChanged = Signal(AiChatHistory)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setupUi()

    def _setupUi(self):
        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.setSpacing(4)

        # History header with new chat button
        headerLayout = QHBoxLayout()

        headerLayout.addWidget(QLabel(self.tr("Chat History")))
        self._btnNewChat = QPushButton(self.tr("New Conversation"), self)
        self._btnNewChat.clicked.connect(self.requestNewChat)
        headerLayout.addWidget(self._btnNewChat)

        mainLayout.addLayout(headerLayout)

        # History list
        self._historyList = QListWidget(self)
        self._historyList.setMinimumWidth(150)
        self._historyList.currentItemChanged.connect(
            self._onHistorySelectionChanged)
        mainLayout.addWidget(self._historyList)

    def _onHistorySelectionChanged(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Handle history selection change"""
        if current and current != previous:
            chatHistory = current.data(Qt.UserRole)
            self.historySelectionChanged.emit(chatHistory)

    def clear(self):
        self._historyList.clear()

    def loadHistories(self, histories: List[AiChatHistory]):
        self.clear()

        # Sort histories by timestamp (newest first)
        sorted_histories = sorted(
            histories,
            key=lambda h: h.timestamp,
            reverse=True
        )

        for history in sorted_histories:
            item = self._makeItem(history)
            self._historyList.addItem(item)

    def currentHistory(self) -> AiChatHistory:
        """Get the currently selected history item"""
        currentItem = self._historyList.currentItem()
        if currentItem:
            return currentItem.data(Qt.UserRole)
        return None

    def updateTitle(self, historyId: str, newTitle: str):
        """Update the title of a history item"""
        for index in range(self._historyList.count()):
            item = self._historyList.item(index)
            chatHistory: AiChatHistory = item.data(Qt.UserRole)
            if chatHistory.historyId == historyId:
                item.setText(newTitle)
                chatHistory.title = newTitle
                item.setData(Qt.UserRole, chatHistory)
                return chatHistory
        return None

    def updateCurrentHistory(self, model: AiModelBase):
        """Update the current selected history item"""
        currentItem = self._historyList.currentItem()
        if not currentItem:
            return None

        messages = []
        for message in model.history:
            messages.append({
                'role': message.role,
                'content': message.message
            })

        chatHistory: AiChatHistory = currentItem.data(Qt.UserRole)
        chatHistory.messages = messages
        chatHistory.modelKey = AiModelFactory.modelKey(model)
        chatHistory.modelId = model.modelId or model.name
        chatHistory.timestamp = datetime.now().isoformat()
        currentItem.setData(Qt.UserRole, chatHistory)

        self._moveItemToTop(currentItem)

        return chatHistory

    def _moveItemToTop(self, item: QListWidgetItem):
        row = self._historyList.row(item)
        if row == 0:
            return

        newRow = 0
        if self._historyList.count() > 1:
            firstHistory: AiChatHistory = self._historyList.item(0).data(Qt.UserRole)
            # keep new conversation at top
            if not firstHistory.messages and firstHistory.title in ['', self.tr("New Conversation")]:
                newRow = 1

        if newRow != row:
            self.blockSignals(True)
            item = self._historyList.takeItem(row)
            self._historyList.insertItem(newRow, item)
            self._historyList.setCurrentItem(item)
            self.blockSignals(False)

    def setCurrentHistory(self, historyId: str):
        """Set the current selected history by ID"""
        for index in range(self._historyList.count()):
            item = self._historyList.item(index)
            chatHistory: AiChatHistory = item.data(Qt.UserRole)
            if chatHistory.historyId == historyId:
                self._historyList.setCurrentItem(item)
                break

    def insertHistoryAtTop(self, history: AiChatHistory, select: bool = True):
        item = self._makeItem(history)
        self._historyList.insertItem(0, item)
        if select:
            self._historyList.setCurrentItem(item)

    def _makeItem(self, history: AiChatHistory) -> QListWidgetItem:
        item = QListWidgetItem(history.title or self.tr("New Conversation"))
        item.setData(Qt.UserRole, history)
        modelStr = self.tr("Model: ")
        createdStr = self.tr("Created: ")
        item.setToolTip(
            f"{modelStr}{history.modelKey}\n{createdStr}{history.timestamp[:19]}")
        return item