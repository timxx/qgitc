# -*- coding: utf-8 -*-

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDockWidget, QHBoxLayout, QMenu, QWidget

from qgitc.aichatwidget import AiChatWidget
from qgitc.applicationbase import ApplicationBase
from qgitc.coloredicontoolbutton import ColoredIconToolButton
from qgitc.common import dataDirPath
from qgitc.elidedlabel import ElidedLabel
from qgitc.separatorwidget import SeparatorWidget


class AiChatDockWidget(QDockWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(self.tr("Chat"))
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._aiChatWidget = AiChatWidget(self, embedded=True)
        self.setWidget(self._aiChatWidget)

        # Create custom title bar with title and combo button
        self._titleBarWidget = QWidget(self)
        self._titleBarLayout = QHBoxLayout(self._titleBarWidget)
        self._titleBarLayout.setContentsMargins(8, 2, 4, 2)
        self._titleBarLayout.setSpacing(4)

        # Add title label on the left
        titleLabel = ElidedLabel(self.tr("Chat"), self._titleBarWidget)
        self._titleBarLayout.addWidget(titleLabel)

        self._chatTitleLabel = ElidedLabel(self._titleBarWidget)
        self._chatTitleLabel.setTextColor(Qt.gray)
        self._titleBarLayout.addWidget(self._chatTitleLabel)

        self._titleBarLayout.addStretch()

        icon = QIcon(dataDirPath() + "/icons/add.svg")
        self._btnNewConversation = ColoredIconToolButton(
            icon, QSize(20, 20), self._titleBarWidget)
        self._btnNewConversation.setIcon(icon)
        self._btnNewConversation.setToolTip(self.tr("New Conversation"))
        self._btnNewConversation.clicked.connect(
            self._aiChatWidget.onNewChatRequested)

        newMenu = QMenu(self._btnNewConversation)
        acNewConversation = newMenu.addAction(self.tr("New Conversation"))
        acNewConversation.triggered.connect(
            self._aiChatWidget.onNewChatRequested)

        acNewChatWindow = newMenu.addAction(self.tr("New Chat Window"))
        acNewChatWindow.triggered.connect(self._onNewChatWindow)

        self._btnNewConversation.setMenu(newMenu)
        self._btnNewConversation.setPopupMode(
            ColoredIconToolButton.MenuButtonPopup)

        self._titleBarLayout.addWidget(self._btnNewConversation)

        settingsIcon = QIcon(dataDirPath() + "/icons/settings.svg")
        btnSettings = ColoredIconToolButton(
            settingsIcon, QSize(16, 16), self)
        btnSettings.setFixedSize(QSize(20, 20))
        btnSettings.setToolTip(self.tr("Configure Chat"))
        btnSettings.clicked.connect(self._aiChatWidget.onOpenSettings)
        self._titleBarLayout.addWidget(btnSettings)

        separator = SeparatorWidget(self._titleBarWidget)
        separator.setFixedSize(QSize(8, 16))
        self._titleBarLayout.addWidget(separator)

        closeIcon = QIcon(dataDirPath() + "/icons/close.svg")
        btnClose = ColoredIconToolButton(
            closeIcon, QSize(20, 20), self._titleBarWidget)
        btnClose.setToolTip(self.tr("Close"))
        btnClose.clicked.connect(self.hide)

        self._titleBarLayout.addWidget(btnClose)
        self.setTitleBarWidget(self._titleBarWidget)

        self._chatWindows = []

        self._aiChatWidget._historyPanel.historySelectionChanged.connect(
            self._onHistorySelectionChanged)
        self._aiChatWidget.chatTitleReady.connect(
            self._onChatTitleReady)

    def chatWidget(self):
        """Get the embedded AI chat widget"""
        return self._aiChatWidget

    def _onNewChatWindow(self):
        """Open a new AI chat window"""
        from qgitc.aichatwindow import AiChatWindow
        chatWindow = AiChatWindow()
        if chatWindow.restoreState():
            chatWindow.show()
        else:
            chatWindow.showMaximized()
        chatWindow.destroyed.connect(
            lambda: self._chatWindows.remove(chatWindow))
        self._chatWindows.append(chatWindow)

    def saveState(self, window):
        """Save the visibility state"""
        settings = ApplicationBase.instance().settings()
        key = f"{window.__class__.__name__}/aiChatDockVisible"
        settings.setValue(key, self.isVisible())

    def restoreState(self, window, visible=True):
        """Restore the visibility state"""
        settings = ApplicationBase.instance().settings()
        key = f"{window.__class__.__name__}/aiChatDockVisible"
        isVisible = settings.value(key, visible, type=bool)
        self.setVisible(isVisible)

    def queryClose(self):
        """Clean up when closing"""
        self._aiChatWidget.queryClose()

    def _onHistorySelectionChanged(self, chatHistory):
        """Update title when chat history changes"""
        if chatHistory and chatHistory.title:
            self._updateChatTitle(chatHistory.title)
        else:
            self._updateChatTitle("")

    def _onChatTitleReady(self):
        """Update title when history data changes (e.g., title generated)"""
        currentHistory = self._aiChatWidget._historyPanel.currentHistory()
        if currentHistory and currentHistory.title:
            self._updateChatTitle(currentHistory.title)
        else:
            self._updateChatTitle("")

    def _updateChatTitle(self, title: str):
        """Update the chat title label with elided text"""
        if not title:
            self._chatTitleLabel.setText("")
        else:
            self._chatTitleLabel.setText(f"- {title}")
            self._chatTitleLabel.setToolTip(title)
