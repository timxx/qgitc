# -*- coding: utf-8 -*-

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


class AiChatHistoryPanel(QWidget):

    requestNewChat = Signal()
    historySelectionChanged = Signal(str)  # historyId

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
        if current:
            historyId = current.data(Qt.UserRole)
            self.historySelectionChanged.emit(historyId)

    def clear(self):
        self._historyList.clear()

    def refreshHistories(self, histories: List[AiChatHistory]):
        self.clear()

        # Sort histories by timestamp (newest first)
        sorted_histories = sorted(
            histories,
            key=lambda h: h.timestamp,
            reverse=True
        )

        modelStr = self.tr("Model: ")
        createdStr = self.tr("Created: ")

        defaultTitle = self.tr("New Conversation")
        for history in sorted_histories:
            item = QListWidgetItem(history.title or defaultTitle)
            item.setData(Qt.UserRole, history.historyId)

            item.setToolTip(
                f"{modelStr}{history.modelKey}\n{createdStr}{history.timestamp[:19]}")
            self._historyList.addItem(item)

    def updateTitle(self, historyId: str, newTitle: str):
        """Update the title of a history item"""
        for index in range(self._historyList.count()):
            item = self._historyList.item(index)
            if item.data(Qt.UserRole) == historyId:
                item.setText(newTitle)
                break

    def setCurrentHistory(self, historyId: str):
        """Set the current selected history by ID"""
        for index in range(self._historyList.count()):
            item = self._historyList.item(index)
            if item.data(Qt.UserRole) == historyId:
                self._historyList.setCurrentItem(item)
                break
