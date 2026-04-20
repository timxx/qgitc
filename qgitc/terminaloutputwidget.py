# -*- coding: utf-8 -*-

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import QTextEdit

_ANSI_COLORS = {
    30: QColor("black").name(),
    31: QColor("red").name(),
    32: QColor("green").name(),
    33: QColor("yellow").name(),
    34: QColor("blue").name(),
    35: QColor("magenta").name(),
    36: QColor("cyan").name(),
    37: QColor("white").name(),
}


@dataclass
class _BlockState:
    title: str
    lines: List[List[Tuple[str, Optional[str]]]] = field(default_factory=list)
    currentLine: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    currentFg: Optional[str] = None
    ansiBuffer: str = ""
    pendingCarriageReturn: bool = False


class TerminalOutputWidget(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocks: "OrderedDict[str, _BlockState]" = OrderedDict()

        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setWordWrapMode(QTextOption.NoWrap)

    def ensureBlock(self, key: str, title: str):
        if key not in self._blocks:
            self._blocks[key] = _BlockState(title=title)
            self._render()
        else:
            self._blocks[key].title = title
            self._render()

    def appendOutput(self, key: str, data: bytes, isError: bool):
        if key not in self._blocks:
            self._blocks[key] = _BlockState(title=key)

        _ = isError
        state = self._blocks[key]
        text = state.ansiBuffer + data.decode("utf-8", errors="replace")
        tokens, state.ansiBuffer = self._parseAnsi(text)

        for tokenType, tokenValue in tokens:
            if tokenType == "sgr":
                self._applySgr(state, tokenValue)
            else:
                self._appendText(state, tokenValue)

        self._render()

    def _parseAnsi(self, text: str):
        tokens = []
        pos = 0

        while pos < len(text):
            escPos = text.find("\x1b", pos)
            if escPos < 0:
                if pos < len(text):
                    tokens.append(("text", text[pos:]))
                return tokens, ""

            if escPos > pos:
                tokens.append(("text", text[pos:escPos]))

            if escPos + 1 >= len(text):
                return tokens, text[escPos:]

            if text[escPos + 1] != "[":
                tokens.append(("text", text[escPos]))
                pos = escPos + 1
                continue

            end = escPos + 2
            while end < len(text) and (text[end].isdigit() or text[end] == ";"):
                end += 1

            if end >= len(text):
                return tokens, text[escPos:]

            if text[end] == "m":
                params = text[escPos + 2: end]
                if not params:
                    tokens.append(("sgr", [0]))
                else:
                    tokens.append(
                        ("sgr", [int(p) if p else 0 for p in params.split(";")]))
                pos = end + 1
                continue

            tokens.append(("text", text[escPos: end + 1]))
            pos = end + 1

        return tokens, ""

    def _applySgr(self, state: _BlockState, params: List[int]):
        for code in params:
            if code == 0:
                state.currentFg = None
            elif code in _ANSI_COLORS:
                state.currentFg = _ANSI_COLORS[code]

    def _appendText(self, state: _BlockState, text: str):
        for ch in text:
            if ch == "\r":
                state.pendingCarriageReturn = True
                continue

            if ch == "\n":
                state.lines.append(list(state.currentLine))
                state.currentLine = []
                state.pendingCarriageReturn = False
                continue

            if state.pendingCarriageReturn:
                # Rewrite only when non-newline text follows a carriage return.
                state.currentLine = []
                state.pendingCarriageReturn = False

            self._appendSegment(state, ch)

    def _appendSegment(self, state: _BlockState, text: str):
        if not text:
            return

        if state.currentLine and state.currentLine[-1][1] == state.currentFg:
            prevText, prevColor = state.currentLine[-1]
            state.currentLine[-1] = (prevText + text, prevColor)
            return

        state.currentLine.append((text, state.currentFg))

    def _render(self):
        self.clear()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        titleFmt = QTextCharFormat()
        titleFmt.setFontWeight(700)

        firstBlock = True
        for state in self._blocks.values():
            if not firstBlock:
                cursor.insertText("\n")
            firstBlock = False

            cursor.insertText(state.title, titleFmt)
            cursor.insertText("\n")

            for line in state.lines:
                self._insertSegments(cursor, line)
                cursor.insertText("\n")

            self._insertSegments(cursor, state.currentLine)

        self.setTextCursor(cursor)

    def _insertSegments(self, cursor: QTextCursor, segments: List[Tuple[str, Optional[str]]]):
        defaultFmt = QTextCharFormat()
        for text, colorName in segments:
            if colorName is None:
                cursor.insertText(text, defaultFmt)
                continue

            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colorName))
            cursor.insertText(text, fmt)
