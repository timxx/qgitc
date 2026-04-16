# -*- coding: utf-8 -*-

from typing import List, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QGuiApplication, QKeyEvent, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from qgitc.agent.slash_commands import SlashCommand


class SlashCommandItemDelegate(QStyledItemDelegate):
    """Render '/command' in bold and description in normal style."""

    CommandRole = Qt.UserRole + 101
    DescriptionRole = Qt.UserRole + 102

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, option, painter, option.widget)

        command = index.data(self.CommandRole) or ""
        desc = index.data(self.DescriptionRole) or ""

        rect = option.rect.adjusted(8, 0, -8, 0)
        painter.save()

        # Draw command part in bold.
        boldFont = option.font
        boldFont.setBold(True)
        painter.setFont(boldFont)
        metricsBold = QFontMetrics(boldFont)
        commandText = command
        commandWidth = metricsBold.horizontalAdvance(commandText)

        textColor = option.palette.color(
            option.palette.ColorRole.HighlightedText
            if option.state & QStyle.State_Selected
            else option.palette.ColorRole.Text
        )
        painter.setPen(textColor)
        baselineY = rect.y() + (rect.height() + metricsBold.ascent() - metricsBold.descent()) // 2
        painter.drawText(rect.x(), baselineY, commandText)

        if desc:
            # Draw description in normal font and elide right by available width.
            normalFont = option.font
            normalFont.setBold(False)
            painter.setFont(normalFont)
            metricsNormal = QFontMetrics(normalFont)
            prefix = " - "
            startX = rect.x() + commandWidth
            available = max(10, rect.width() - commandWidth)
            elided = metricsNormal.elidedText(prefix + desc, Qt.ElideRight, available)
            painter.drawText(startX, baselineY, elided)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        base = super().sizeHint(option, index)
        return QSize(base.width(), max(24, base.height() + 2))


class SlashCommandPopup(QWidget):
    """Inline non-blocking popup showing slash command suggestions."""

    MAX_WIDTH = 420
    MIN_WIDTH = 220
    ITEM_H_PADDING = 28
    MAX_VISIBLE_ROWS = 8

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
        self._delegate = SlashCommandItemDelegate(self._list)
        self._list.setItemDelegate(self._delegate)
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(self._onItemClicked)
        self._list.itemActivated.connect(self._onItemClicked)
        layout.addWidget(self._list)

    def setCommands(self, commands: List[SlashCommand]) -> None:
        self._commands = list(commands)
        self._list.clear()
        fm = QFontMetrics(self._list.font())
        widest = self.MIN_WIDTH

        for cmd in self._commands:
            text = self._formatItemText(cmd, fm)
            item = QListWidgetItem(text)
            item.setToolTip(cmd.description)
            item.setData(Qt.UserRole, cmd.name)
            item.setData(SlashCommandItemDelegate.CommandRole, "/{}".format(cmd.name))
            item.setData(SlashCommandItemDelegate.DescriptionRole, (cmd.description or "").strip())
            self._list.addItem(item)
            widest = max(widest, fm.horizontalAdvance(text) + self.ITEM_H_PADDING)

        width = min(self.MAX_WIDTH, widest)
        self.setFixedWidth(width)
        self._list.setFixedWidth(width)
        self._updatePopupHeight()

        if self._commands:
            self._list.setCurrentRow(0)

    def _updatePopupHeight(self) -> None:
        rows = min(len(self._commands), self.MAX_VISIBLE_ROWS)
        if rows <= 0:
            self.setFixedHeight(0)
            return

        rowHeight = self._list.sizeHintForRow(0)
        if rowHeight <= 0:
            rowHeight = max(24, self._list.fontMetrics().height() + 6)

        frame = self._list.frameWidth() * 2
        listHeight = rows * rowHeight + frame
        self._list.setFixedHeight(listHeight)

        margins = self.layout().contentsMargins()
        totalHeight = listHeight + margins.top() + margins.bottom()
        self.setFixedHeight(totalHeight)

    def _formatItemText(self, cmd: SlashCommand, fm: QFontMetrics) -> str:
        commandText = "/{}".format(cmd.name)
        desc = (cmd.description or "").strip()
        if not desc:
            return commandText

        separator = " - "
        reserved = fm.horizontalAdvance(commandText + separator)
        available = max(20, self.MAX_WIDTH - self.ITEM_H_PADDING - reserved)
        elidedDesc = fm.elidedText(desc, Qt.ElideRight, available)
        return commandText + separator + elidedDesc

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
