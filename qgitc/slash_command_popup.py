# -*- coding: utf-8 -*-

from typing import List, Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from qgitc.agent.slash_commands import SlashCommand


class SlashCommandPopup(QWidget):
    """Inline non-blocking popup showing slash command suggestions."""

    commandSelected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)

        self._commands = []  # type: List[SlashCommand]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget(self)
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

    def showAt(self, pos: QPoint) -> None:
        self.move(pos)
        self.show()

    def _onItemClicked(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.UserRole)
        for cmd in self._commands:
            if cmd.name == name:
                self.commandSelected.emit(cmd)
                return
