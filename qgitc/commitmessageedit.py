# -*- coding: utf-8 -*-

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from qgitc.applicationbase import ApplicationBase
from qgitc.common import findInlineSpans
from qgitc.textline import Link, TextLine
from qgitc.textviewer import TextViewer


class CommitMessageHighlighter(QSyntaxHighlighter):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bugPatterns = []
        self.reloadBugPattern()

    def highlightBlock(self, text):
        if ApplicationBase.instance().settings().ignoreCommentLine() and text.startswith("#"):
            self.setFormat(
                0, len(text), ApplicationBase.instance().colorSchema().Comment)
            return

        inlineFmt = QTextCharFormat()
        inlineFmt.setForeground(
            ApplicationBase.instance().colorSchema().InlineCode)
        for start, length in findInlineSpans(text):
            self.setFormat(start, length, inlineFmt)

        builtinPatterns = TextLine.builtinPatterns()
        patterns = list(self._bugPatterns)
        for type, pattern in builtinPatterns.items():
            patterns.append((type, pattern, None))
        links: List[Link] = TextLine.findLinks(text, patterns)
        if not links:
            return

        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        fmt.setForeground(
            ApplicationBase.instance().palette().color(QPalette.Link))

        for link in links:
            self.setFormat(link.start, link.end - link.start, fmt)

    def reloadBugPattern(self):
        self._bugPatterns = TextViewer.reloadBugPattern()


class CommitMessageEdit(QPlainTextEdit):

    def __init__(self, parent=None):
        super().__init__(parent)

        self._highlighter = CommitMessageHighlighter(self.document())

        sett = ApplicationBase.instance().settings()
        sett.ignoreCommentLineChanged.connect(
            self._highlighter.rehighlight)

        sett.bugPatternChanged.connect(
            self._onBugPatternChanged)
        sett.fallbackGlobalChanged.connect(
            self._onBugPatternChanged)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Tab and self._isTabToGroupEnabled():
            self._handleTabKey()
            return
        elif e.key() == Qt.Key_Backtab and self._isTabToGroupEnabled():
            self._handleTabKey(isBackward=True)
            return

        super().keyPressEvent(e)

    def _isTabToGroupEnabled(self):
        return ApplicationBase.instance().settings().tabToNextGroup()

    def _handleTabKey(self, isBackward=False):
        if self.document().isEmpty():
            return

        groupChars = [groupChar.strip() for groupChar in ApplicationBase.instance().settings(
        ).groupChars().split(" ") if len(groupChar.strip()) == 2]
        if not groupChars:
            return
        ignoreCommentLine = ApplicationBase.instance().settings().ignoreCommentLine()

        cursor = self.textCursor()
        firstRound = True

        def _updateNotFoundCursor():
            if isBackward:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
            else:
                cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)

        processedBlocks = set()
        while True:
            # we've processed all blocks
            if cursor.blockNumber() in processedBlocks:
                _updateNotFoundCursor()
                break
            processedBlocks.add(cursor.blockNumber())

            lineText = self._curLineText(cursor)
            if not lineText or (ignoreCommentLine and lineText.startswith("#")):
                if self.blockCount() == 1:
                    _updateNotFoundCursor()
                    break
                firstRound = self._nextLine(cursor, isBackward, firstRound)
                continue

            cursorPos = cursor.positionInBlock()
            text = lineText[:cursorPos] if isBackward else lineText[cursorPos:]
            if self._doFind(cursor, text, groupChars, isBackward, ignoreCommentLine):
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

    def _doFind(self, cursor: QTextCursor, text: str, groupChars: List[str], isBackward=False, ignoreCommentLine=False):
        if not text:
            return False

        findFunc = self._doFindPrev if isBackward else self._doFindNext
        for groupChar in groupChars:
            if findFunc(cursor, text, groupChar[0], groupChar[1], ignoreCommentLine):
                return True

        return False

    def _doFindNext(self, cursor: QTextCursor, text: str, openChar: str, closeChar: str, ignoreCommentLine: bool):
        begin = text.find(openChar)
        if begin != -1:
            end = text.find(closeChar, begin + 1)
            # maybe end in next line
            while end == -1 and cursor.block().blockNumber() != self.blockCount() - 1:
                self._nextLine(cursor, False)
                text = self._curLineText(cursor)
                if not ignoreCommentLine or not text.startswith("#"):
                    end = text.find(closeChar)

            if end != -1:
                cursor.setPosition(cursor.position() + end)
                self.setTextCursor(cursor)
                return True

        return False

    def _doFindPrev(self, cursor: QTextCursor, text: str, openChar: str, closeChar: str, ignoreCommentLine: bool):
        end = text.rfind(closeChar)
        if end != -1:
            begin = text.rfind(openChar, 0, end - 1)
            # maybe start in prev line
            while begin == -1 and cursor.block().blockNumber() != 0:
                self._nextLine(cursor, True)
                text = self._curLineText(cursor)
                if not ignoreCommentLine or not text.startswith("#"):
                    begin = text.rfind(openChar)

            if begin != -1:
                cursor.setPosition(cursor.position() - len(text[end:]))
                self.setTextCursor(cursor)
                return True

        return False

    def _onBugPatternChanged(self):
        self._highlighter.reloadBugPattern()
        self._highlighter.rehighlight()
