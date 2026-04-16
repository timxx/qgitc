# -*- coding: utf-8 -*-

from typing import List, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qgitc.agent.slash_commands import SlashCommand


class SlashCommandPopup(QWidget):
    """Inline non-blocking popup showing slash command suggestions."""

    commandSelected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)

        self._commands = []  # type: List[SlashCommand]
        self._keyTarget = None  # type: Optional[QWidget]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget(self)
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.itemClicked.connect(self._onItemClicked)
        self._list.itemActivated.connect(self._onItemClicked)
        layout.addWidget(self._list)

    def setCommands(self, commands: List[SlashCommand]) -> None:
        self._commands = list(commands)
        self._list.clear()

        for cmd in self._commands:
            item = QListWidgetItem("/{}".format(cmd.name))
            item.setToolTip(cmd.description)
            item.setData(Qt.UserRole, cmd.name)
            self._list.addItem(item)

        if self._commands:
            self._list.setCurrentRow(0)

    def currentCommand(self) -> Optional[SlashCommand]:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._commands):
            return None
        return self._commands[row]

    def commandCount(self) -> int:
        return len(self._commands)

    def selectNext(self) -> None:
        if not self._commands:
            return
        row = self._list.currentRow()
        if row < 0:
            self._list.setCurrentRow(0)
            return
        self._list.setCurrentRow(min(row + 1, len(self._commands) - 1))

    def selectPrevious(self) -> None:
        if not self._commands:
            return
        row = self._list.currentRow()
        if row < 0:
            self._list.setCurrentRow(0)
            return
        self._list.setCurrentRow(max(row - 1, 0))

    def activateCurrent(self) -> None:
        cmd = self.currentCommand()
        if cmd is not None:
            self.commandSelected.emit(cmd)

    def setKeyTarget(self, target: QWidget) -> None:
        self._keyTarget = target

    def showAt(self, pos: QPoint) -> None:
        popupSize = self.sizeHint()
        if popupSize.width() <= 0 or popupSize.height() <= 0:
            popupSize = QSize(max(200, self.width()), max(100, self.height()))

        screen = QGuiApplication.screenAt(pos)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        bounds = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)

        self.move(self.computePopupPos(pos, popupSize, bounds))
        self.show()

    @staticmethod
    def computePopupPos(anchorPos: QPoint, popupSize: QSize, bounds: QRect) -> QPoint:
        x = anchorPos.x()
        y = anchorPos.y()

        if y + popupSize.height() > bounds.bottom():
            y = anchorPos.y() - popupSize.height()

        if x + popupSize.width() > bounds.right():
            x = bounds.right() - popupSize.width()

        if x < bounds.left():
            x = bounds.left()
        if y < bounds.top():
            y = bounds.top()

        return QPoint(x, y)

    def _onItemClicked(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.UserRole)
        for cmd in self._commands:
            if cmd.name == name:
                self.commandSelected.emit(cmd)
                return

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._keyTarget is not None:
            forwarded = QKeyEvent(
                event.type(),
                event.key(),
                event.modifiers(),
                event.text(),
                event.isAutoRepeat(),
                event.count(),
            )
            self._keyTarget.setFocus()
            QApplication.sendEvent(self._keyTarget, forwarded)
            return
        super().keyPressEvent(event)
