# -*- coding: utf-8 -*-

from typing import List
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit


class CommitMessageEdit(QPlainTextEdit):

    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Tab and self._isTabToGroupEnabled():
            self._handleTabKey()
            return
        elif e.key() == Qt.Key_Backtab and self._isTabToGroupEnabled():
            self._handleTabKey(isBackward=True)
            return

        super().keyPressEvent(e)

    def _isTabToGroupEnabled(self):
        return qApp.settings().tabToNextGroup()

    def _handleTabKey(self, isBackward=False):
        if self.document().isEmpty():
            return

        groupChars = [groupChar.strip() for groupChar in qApp.settings(
        ).groupChars().split(" ") if len(groupChar.strip()) == 2]
        if not groupChars:
            return
        ignoreCommentLine = qApp.settings().ignoreCommentLine()

        cursor = self.textCursor()
        firstRound = True

        def _updateNotFoundCursor():
            if isBackward:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)

        while firstRound or not (cursor.atStart() if isBackward else cursor.atEnd()):
            lineText = self._curLineText(cursor)

            if not lineText or (ignoreCommentLine and lineText.startswith("#")):
                if self.blockCount() == 1:
                    _updateNotFoundCursor()
                    break
                firstRound = self._nextLine(cursor, isBackward, firstRound)
                continue

            cursorPos = cursor.positionInBlock()
            text = lineText[:cursorPos] if isBackward else lineText[cursorPos:]
            if self._doFind(cursor, text, groupChars, isBackward):
                break
            elif not firstRound and self.blockCount() == 1:
                _updateNotFoundCursor()
                break
            else:
                firstRound = self._nextLine(cursor, isBackward, firstRound)

    def _nextLine(self, cursor: QTextCursor, isBackward=False, firstRound=False):
        if isBackward:
            if cursor.block().blockNumber() == 0:
                if firstRound:
                    cursor.movePosition(QTextCursor.MoveOperation.End)
                    firstRound = False
            else:
                cursor.movePosition(QTextCursor.PreviousBlock)
                cursor.movePosition(QTextCursor.EndOfBlock)
        else:
            if cursor.block().blockNumber() == self.blockCount() - 1:
                if firstRound:
                    cursor.movePosition(QTextCursor.MoveOperation.Start)
                    firstRound = False
            else:
                cursor.movePosition(QTextCursor.NextBlock)
                cursor.movePosition(QTextCursor.StartOfBlock)

        return firstRound

    def _curLineText(self, cursor: QTextCursor):
        postion = cursor.position()
        cursor.select(QTextCursor.LineUnderCursor)
        lineText = cursor.selectedText()
        cursor.setPosition(postion)
        return lineText

    def _doFind(self, cursor: QTextCursor, text: str, groupChars: List[str], isBackward=False):
        if not text:
            return False

        findFunc = self._doFindPrev if isBackward else self._doFindNext
        for groupChar in groupChars:
            if findFunc(cursor, text, groupChar[0], groupChar[1]):
                return True

        return False

    def _doFindNext(self, cursor: QTextCursor, text: str, openChar: str, closeChar: str):
        begin = text.find(openChar)
        if begin != -1:
            end = text.find(closeChar, begin + 1)
            # maybe end in next line
            while not cursor.atEnd() and end == -1 and self.blockCount() > 1:
                self._nextLine(cursor, False)
                text = self._curLineText(cursor)
                end = text.find(closeChar)

            if end != -1:
                cursor.setPosition(cursor.position() + end)
                self.setTextCursor(cursor)
                return True

        return False

    def _doFindPrev(self, cursor: QTextCursor, text: str, openChar: str, closeChar: str):
        end = text.rfind(closeChar)
        if end != -1:
            begin = text.rfind(openChar, 0, end - 1)
            # maybe start in prev line
            while not cursor.atStart() and begin == -1 and self.blockCount() > 1:
                self._nextLine(cursor, True)
                text = self._curLineText(cursor)
                begin = text.rfind(openChar)

            if begin != -1:
                cursor.setPosition(cursor.position() - len(text[end:]))
                self.setTextCursor(cursor)
                return True

        return False
