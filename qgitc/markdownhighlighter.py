# -*- coding: utf-8 -*-

from enum import Flag, IntEnum
import string
from typing import Dict, List
from PySide6.QtCore import (
    QRegularExpression,
    QTimer,
    Signal,
    Qt,
    QFlag,
    QRegularExpressionMatch
)
from PySide6.QtGui import (
    QSyntaxHighlighter,
    QTextCharFormat,
    QColor,
    QFont,
    QTextDocument,
    QBrush,
    QFontDatabase,
    QTextBlock
)

from .languagedata import *


# translated from https://github.com/pbek/qmarkdowntextedit


@QFlag
class HighlightingOptions(Flag):
    None_ = 0
    FullyHighlightedBlockQuote = 0x01
    Underline = 0x02


class HighlighterState(IntEnum):
    NoState = -1
    Link = 0
    Image = 3
    CodeBlock = 4
    CodeBlockComment = 5
    Italic = 7
    Bold = 8
    List = 9
    Comment = 11
    H1 = 12
    H2 = 13
    H3 = 14
    H4 = 15
    H5 = 16
    H6 = 17
    BlockQuote = 18
    HorizontalRuler = 21
    Table = 22
    InlineCodeBlock = 23
    MaskedSyntax = 24
    CurrentLineBackgroundColor = 25
    BrokenLink = 26
    FrontmatterBlock = 27
    TrailingSpace = 28
    CheckBoxUnChecked = 29
    CheckBoxChecked = 30

    # Code highlighting
    CodeKeyWord = 1000
    CodeString = 1001
    CodeComment = 1002
    CodeType = 1003
    CodeOther = 1004
    CodeNumLiteral = 1005
    CodeBuiltIn = 1006

    # Internal
    CodeBlockIndented = 96
    CodeBlockTildeEnd = 97
    CodeBlockTilde = 98
    CodeBlockTildeComment = 99
    CodeBlockEnd = 100
    HeadlineEnd = 101
    FrontmatterBlockEnd = 102

    # languages
    # When adding a language make sure that its value is a multiple of 2
    # This is because we use the next number as comment for that language
    # In case the language doesn't support multiline comments in the
    # traditional C++ sense, leave the next value empty. Otherwise mark the
    # next value as comment for that language. e.g CodeCpp = 200
    # CodeCppComment = 201
    CodeCpp = 200
    CodeCppComment = 201
    CodeJs = 202
    CodeJsComment = 203
    CodeC = 204
    CodeCComment = 205
    CodeBash = 206
    CodePHP = 208
    CodePHPComment = 209
    CodeQML = 210
    CodeQMLComment = 211
    CodePython = 212
    CodeRust = 214
    CodeRustComment = 215
    CodeJava = 216
    CodeJavaComment = 217
    CodeCSharp = 218
    CodeCSharpComment = 219
    CodeGo = 220
    CodeGoComment = 221
    CodeV = 222
    CodeVComment = 223
    CodeSQL = 224
    CodeJSON = 226
    CodeXML = 228
    CodeCSS = 230
    CodeCSSComment = 231
    CodeTypeScript = 232
    CodeTypeScriptComment = 233
    CodeYAML = 234
    CodeINI = 236
    CodeTaggerScript = 238
    CodeVex = 240
    CodeVexComment = 241
    CodeCMake = 242
    CodeMake = 244


class HighlightingRule:

    def __init__(self, state: HighlighterState):
        self.pattern = QRegularExpression()
        self.shouldContain = ""
        self.state = state
        self.capturingGroup = 0
        self.maskedGroup = 0


def getIndentation(text):
    """
    Gets indentation(spaces) of text
    @param text
    @return 1, if 1 space, 2 if 2 spaces, 3 if 3 spaces. Otherwise 0
    """
    spaces = 0
    # no more than 3 spaces
    while spaces < 4 and spaces < len(text) and text[spaces] == ' ':
        spaces += 1
    return spaces


def isInLinkRange(self, pos: int, ranges: List[tuple[int, int]]):
    """ helper function to check if we are in a link while highlighting inline rules """
    j = 0
    for i in range(len(ranges)):
        if pos > ranges[i][0] and pos < ranges[i][1]:
            length = ranges[i][1] - ranges[i][0]
            del ranges[j]
            return length
        j += 1
    return -1

# EM and Strong Parsing + Highlighting


class Delimiter:

    def __init__(self):
        self.pos = 0
        self.len = 0
        self.end = 0
        self.jump = 0
        self.open = False
        self.close = False
        self.marker = ""


def isMDAsciiPunct(ch: str):
    if not ch:
        return False

    n = ord(ch)
    return 33 <= n <= 47 or 58 <= n <= 64 or \
        91 <= n <= 96 or 123 <= n <= 126


def scanDelims(text: str, start: int, canSplitWord: bool):
    """ scans a chain of '*' or '_' """

    pos = start
    textLen = len(text)
    marker = text[start]
    leftFlanking = True
    rightFlanking = True

    lastChar = text[start - 1] if start > 0 else ""

    while pos < textLen and text[pos] == marker:
        pos += 1

    length = pos - start
    nextChar = text[pos] if pos + 1 < textLen else ""

    isLastPunct = isMDAsciiPunct(lastChar) or lastChar in string.punctuation
    isNextPunct = isMDAsciiPunct(nextChar) or nextChar in string.punctuation

    # treat line end and start as whitespace
    isLastWhiteSpace = True if not lastChar else lastChar.isspace()
    isNextWhiteSpace = True if not nextChar else nextChar.isspace()

    if isNextWhiteSpace:
        leftFlanking = False
    elif isNextPunct:
        if not (isLastWhiteSpace or isLastPunct):
            leftFlanking = False
    if isLastWhiteSpace:
        rightFlanking = False
    elif isLastPunct:
        if not (isNextWhiteSpace or isNextPunct):
            rightFlanking = False

    canOpen = leftFlanking if canSplitWord else leftFlanking and (
        not rightFlanking or isLastPunct)
    canClose = rightFlanking if canSplitWord else rightFlanking and (
        not leftFlanking or isNextPunct)

    return length, canOpen, canClose


def collectEmDelims(text: str, curPos: int, delims: List[Delimiter]):
    marker = text[curPos]
    result = scanDelims(text, curPos, marker == "*")
    length = result[0]
    canOpen = result[1]
    canClose = result[2]

    for i in range(length):
        d = Delimiter()
        d.pos = curPos + i
        d.len = length
        d.end = -1
        d.jump = i
        d.open = canOpen
        d.close = canClose
        d.marker = marker
        delims.append(d)

    return curPos + length


def balancePairs(delims: List[Delimiter]):
    for i in range(len(delims)):
        lastDelim = delims[i]
        if not lastDelim.close:
            continue

        j = i - lastDelim.jump - 1
        while j >= 0:
            curDelim = delims[j]
            if curDelim.open and curDelim.marker == lastDelim.marker and curDelim.end < 0:
                oddMatch = (curDelim.close or lastDelim.open) and curDelim.len != - \
                    1 and lastDelim.len != - \
                    1 and (curDelim.len + lastDelim.len) % 3 == 0

                if not oddMatch:
                    delims[i].jump = i - j
                    delims[i].open = False
                    delims[j].end = i
                    delims[j].jump = 0
                    break
            j -= curDelim.jump + 1


class MarkdownHighlighter(QSyntaxHighlighter):
    """
    Markdown syntax highlighting
    """

    # Class variables
    _formats: Dict[HighlighterState, QTextCharFormat] = {}
    _langStringToEnum: Dict[str, HighlighterState] = {}
    tildeOffset = 300

    highlightingFinished = Signal()

    def __init__(self, parent: QTextDocument = None, highlightingOptions: HighlightingOptions = HighlightingOptions.None_):
        super().__init__(parent)
        self._highlightingOptions = highlightingOptions
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.timerTick)
        self._timer.start(1000)

        self._highlightingRules: List[HighlightingRule] = []
        self._linkRanges: List[tuple[int, int]] = []
        self._dirtyTextBlocks: List[QTextBlock] = []
        self._highlightingFinished = True

        # Initialize highlighting rules
        self.initHighlightingRules()

        # Initialize text formats if not already done
        if not self._formats:
            self.initTextFormats()

        # Initialize code languages if not already done
        if not MarkdownHighlighter._langStringToEnum:
            self.initCodeLangs()

    @staticmethod
    def codeBlockBackgroundColor():
        brush = MarkdownHighlighter._formats[HighlighterState.CodeBlock].background(
        )

        if not brush.isOpaque():
            return QColor(Qt.transparent)

        return brush.color()

    @staticmethod
    def isOctal(c):
        return '0' <= c <= '7'

    @staticmethod
    def isHex(c):
        return ('0' <= c <= '9') or ('a' <= c <= 'f') or ('A' <= c <= 'F')

    @staticmethod
    def isCodeBlock(state):
        return (state == HighlighterState.CodeBlock or
                state == HighlighterState.CodeBlockTilde or
                state == HighlighterState.CodeBlockComment or
                state == HighlighterState.CodeBlockTildeComment or
                state >= HighlighterState.CodeCpp)

    @staticmethod
    def isCodeBlockEnd(state):
        return (state == HighlighterState.CodeBlockEnd or
                state == HighlighterState.CodeBlockTildeEnd)

    @staticmethod
    def setTextFormats(formats: Dict[HighlighterState, QTextCharFormat]):
        MarkdownHighlighter._formats = formats

    @staticmethod
    def setTextFormat(state: HighlighterState, format_: QTextCharFormat):
        MarkdownHighlighter._formats[state] = format_

    def clearDirtyBlocks(self):
        self._dirtyTextBlocks.clear()

    def setHighlightingOptions(self, options: HighlightingOptions):
        self._highlightingOptions = options

    def initHighlightingRules(self):
        # Highlight the reference of reference links
        rule = HighlightingRule(HighlighterState.MaskedSyntax)
        rule.pattern = QRegularExpression(r"^\[.+?\]: \w+://.+$")
        rule.shouldContain = "://"
        self._highlightingRules.append(rule)

        # Highlight block quotes
        rule = HighlightingRule(HighlighterState.BlockQuote)
        if self._highlightingOptions & HighlightingOptions.FullyHighlightedBlockQuote:
            rule.pattern = QRegularExpression(r"^\\s*(>\\s*.+)")
        else:
            rule.pattern = QRegularExpression(r"^\\s*(>\\s*)+")
        rule.shouldContain = "> "
        self._highlightingRules.append(rule)

        # highlight tables without starting |
        # we drop that for now, it's far too messy to deal with
        #    rule = HighlightingRule();
        #    rule.pattern = QRegularExpression("^.+? \\| .+? \\| .+$");
        #    rule.state = HighlighterState::Table;
        #    _highlightingRulesPre.append(rule);

        # Highlight URLs
        rule = HighlightingRule(HighlighterState.Link)

        # URLs without any other markup
        rule.pattern = QRegularExpression(r"\b\w+?:\/\/[^\s>]+")
        rule.capturingGroup = 0
        rule.shouldContain = "://"
        self._highlightingRules.append(rule)

        # URLs with <> but without any . in it
        rule = HighlightingRule(HighlighterState.Link)
        rule.pattern = QRegularExpression(r"<(\w+?:\/\/[^\s]+)>")
        rule.capturingGroup = 1
        rule.shouldContain = "://"
        self._highlightingRules.append(rule)

        # Links with <> that have a . in them
        rule = HighlightingRule(HighlighterState.Link)
        rule.pattern = QRegularExpression(r"<([^\s`][^`]*?\.[^`]*?[^\s`])>")
        rule.capturingGroup = 1
        rule.shouldContain = "<"
        self._highlightingRules.append(rule)

        # URLs with title
        rule = HighlightingRule(HighlighterState.Link)
        rule.pattern = QRegularExpression(r"\[([^\[\]]+)\]\((\S+|.+?)\)\B")
        rule.shouldContain = "]("
        self._highlightingRules.append(rule)

        # URLs with empty title
        rule = HighlightingRule(HighlighterState.Link)
        rule.pattern = QRegularExpression(r"\[\]\((.+?)\)")
        rule.shouldContain = "[]("
        self._highlightingRules.append(rule)

        # Email links
        rule = HighlightingRule(HighlighterState.Link)
        rule.pattern = QRegularExpression(r"<(.+?@.+?)>")
        rule.shouldContain = "@"
        self._highlightingRules.append(rule)

        # Reference links
        rule = HighlightingRule(HighlighterState.Link)
        rule.pattern = QRegularExpression(r"\[(.+?)\]\[.+?\]")
        rule.shouldContain = "["
        self._highlightingRules.append(rule)

        # Images with text
        rule = HighlightingRule(HighlighterState.Image)
        rule.pattern = QRegularExpression(r"!\[(.+?)\]\(.+?\)")
        rule.shouldContain = "!["
        rule.capturingGroup = 1
        self._highlightingRules.append(rule)

        # Images without text
        rule = HighlightingRule(HighlighterState.Image)
        rule.pattern = QRegularExpression(r"!\[\]\((.+?)\)")
        rule.shouldContain = "![]"
        self._highlightingRules.append(rule)

        # Image links
        rule = HighlightingRule(HighlighterState.Link)
        rule.pattern = QRegularExpression(r"\[!\[(.+?)\]\(.+?\)\]\(.+?\)")
        rule.shouldContain = "!["
        rule.capturingGroup = 1
        self._highlightingRules.append(rule)

        # Image links without text
        rule = HighlightingRule(HighlighterState.Link)
        rule.pattern = QRegularExpression(r"\[!\[\]\(.+?\)\]\((.+?)\)")
        rule.shouldContain = "![]("
        self._highlightingRules.append(rule)

        # Trailing spaces
        rule = HighlightingRule(HighlighterState.TrailingSpace)
        rule.pattern = QRegularExpression(r"( +)$")
        # Note: Python string handling is different, this might need adjustment
        rule.shouldContain = " \0"
        rule.capturingGroup = 1
        self._highlightingRules.append(rule)

        # Inline comments for Rmarkdown
        rule = HighlightingRule(HighlighterState.Comment)
        rule.pattern = QRegularExpression(r"^\[.+?\]: # \(.+?\)$")
        rule.shouldContain = "]: # ("
        self._highlightingRules.append(rule)

        # Tables with starting |
        rule = HighlightingRule(HighlighterState.Table)
        rule.pattern = QRegularExpression(r"^\|.+?\|$")
        rule.shouldContain = "|"
        self._highlightingRules.append(rule)

    @staticmethod
    def initTextFormats(defaultFontSize=12):
        formats = {}

        # Set character formats for headlines
        charFormat = QTextCharFormat()
        charFormat.setForeground(QColor(2, 69, 150))
        charFormat.setFontWeight(QFont.Bold)
        charFormat.setFontPointSize(defaultFontSize * 1.6)
        formats[HighlighterState.H1] = QTextCharFormat(charFormat)

        charFormat.setFontPointSize(defaultFontSize * 1.5)
        formats[HighlighterState.H2] = QTextCharFormat(charFormat)

        charFormat.setFontPointSize(defaultFontSize * 1.4)
        formats[HighlighterState.H3] = QTextCharFormat(charFormat)

        charFormat.setFontPointSize(defaultFontSize * 1.3)
        formats[HighlighterState.H4] = QTextCharFormat(charFormat)

        charFormat.setFontPointSize(defaultFontSize * 1.2)
        formats[HighlighterState.H5] = QTextCharFormat(charFormat)

        charFormat.setFontPointSize(defaultFontSize * 1.1)
        formats[HighlighterState.H6] = QTextCharFormat(charFormat)

        # Set character format for horizontal rulers
        charFormat = QTextCharFormat()
        charFormat.setForeground(Qt.darkGray)
        charFormat.setBackground(Qt.lightGray)
        formats[HighlighterState.HorizontalRuler] = charFormat

        # Set character format for lists
        charFormat = QTextCharFormat()
        charFormat.setForeground(QColor(163, 0, 123))
        formats[HighlighterState.List] = charFormat

        # Set character format for unchecked checkbox
        charFormat = QTextCharFormat()
        charFormat.setForeground(QColor(123, 100, 223))
        formats[HighlighterState.CheckBoxUnChecked] = charFormat

        # Set character format for checked checkbox
        charFormat = QTextCharFormat()
        charFormat.setForeground(QColor(223, 50, 123))
        formats[HighlighterState.CheckBoxChecked] = charFormat

        # Set character format for links
        charFormat = QTextCharFormat()
        charFormat.setForeground(QColor(0, 128, 255))
        charFormat.setFontUnderline(True)
        formats[HighlighterState.Link] = charFormat

        # Set character format for images
        charFormat = QTextCharFormat()
        charFormat.setForeground(QColor(0, 191, 0))
        charFormat.setBackground(QColor(228, 255, 228))
        formats[HighlighterState.Image] = charFormat

        # Set character format for code blocks
        charFormat = QTextCharFormat()
        charFormat.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        formats[HighlighterState.CodeBlock] = charFormat
        formats[HighlighterState.InlineCodeBlock] = charFormat

        # Set character format for italic
        charFormat = QTextCharFormat()
        charFormat.setFontItalic(True)
        formats[HighlighterState.Italic] = charFormat

        # Set character format for bold
        charFormat = QTextCharFormat()
        charFormat.setFontWeight(QFont.Bold)
        formats[HighlighterState.Bold] = charFormat

        # Set character format for comments
        charFormat = QTextCharFormat()
        charFormat.setForeground(QBrush(Qt.gray))
        formats[HighlighterState.Comment] = charFormat

        # Set character format for masked syntax
        charFormat = QTextCharFormat()
        charFormat.setForeground(QColor(204, 204, 204))
        formats[HighlighterState.MaskedSyntax] = charFormat

        # Set character format for tables
        charFormat = QTextCharFormat()
        charFormat.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        charFormat.setForeground(QColor(100, 148, 73))
        formats[HighlighterState.Table] = charFormat

        # Set character format for block quotes
        charFormat = QTextCharFormat()
        charFormat.setForeground(Qt.darkRed)
        formats[HighlighterState.BlockQuote] = charFormat

        charFormat = QTextCharFormat()
        formats[HighlighterState.HeadlineEnd] = charFormat

        charFormat = QTextCharFormat()
        formats[HighlighterState.NoState] = charFormat

        # Formats for syntax highlighting
        charFormat = QTextCharFormat()
        charFormat.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        charFormat.setForeground(QColor(249, 38, 114))
        formats[HighlighterState.CodeKeyWord] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        charFormat.setForeground(QColor(163, 155, 78))
        formats[HighlighterState.CodeString] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        charFormat.setForeground(QColor(117, 113, 94))
        formats[HighlighterState.CodeComment] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        charFormat.setForeground(QColor(84, 174, 191))
        formats[HighlighterState.CodeType] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        charFormat.setForeground(QColor(219, 135, 68))
        formats[HighlighterState.CodeOther] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        charFormat.setForeground(QColor(174, 129, 255))
        formats[HighlighterState.CodeNumLiteral] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        charFormat.setForeground(QColor(1, 138, 15))
        formats[HighlighterState.CodeBuiltIn] = charFormat

        MarkdownHighlighter._formats = formats

    @staticmethod
    def initCodeLangs():
        MarkdownHighlighter._langStringToEnum = {
            "bash": HighlighterState.CodeBash,
            "c": HighlighterState.CodeC,
            "cpp": HighlighterState.CodeCpp,
            "cxx": HighlighterState.CodeCpp,
            "c++": HighlighterState.CodeCpp,
            "c#": HighlighterState.CodeCSharp,
            "cmake": HighlighterState.CodeCMake,
            "csharp": HighlighterState.CodeCSharp,
            "css": HighlighterState.CodeCSS,
            "go": HighlighterState.CodeGo,
            "html": HighlighterState.CodeXML,
            "ini": HighlighterState.CodeINI,
            "java": HighlighterState.CodeJava,
            "javascript": HighlighterState.CodeJava,
            "js": HighlighterState.CodeJs,
            "json": HighlighterState.CodeJSON,
            "make": HighlighterState.CodeMake,
            "php": HighlighterState.CodePHP,
            "py": HighlighterState.CodePython,
            "python": HighlighterState.CodePython,
            "qml": HighlighterState.CodeQML,
            "rust": HighlighterState.CodeRust,
            "sh": HighlighterState.CodeBash,
            "sql": HighlighterState.CodeSQL,
            "taggerscript": HighlighterState.CodeTaggerScript,
            "ts": HighlighterState.CodeTypeScript,
            "typescript": HighlighterState.CodeTypeScript,
            "v": HighlighterState.CodeV,
            "vex": HighlighterState.CodeVex,
            "xml": HighlighterState.CodeXML,
            "yml": HighlighterState.CodeYAML,
            "yaml": HighlighterState.CodeYAML
        }

    def timerTick(self):
        # Re-highlight all dirty blocks
        self.reHighlightDirtyBlocks()

        # Emit a signal every second if there was some highlighting done
        if self._highlightingFinished:
            self._highlightingFinished = False
            self.highlightingFinished.emit()

    def reHighlightDirtyBlocks(self):
        while self._dirtyTextBlocks:
            block = self._dirtyTextBlocks[0]
            self.rehighlightBlock(block)
            self._dirtyTextBlocks.pop(0)

    def addDirtyBlock(self, block):
        if block not in self._dirtyTextBlocks:
            self._dirtyTextBlocks.append(block)

    def highlightBlock(self, text):
        if self.currentBlockState() == HighlighterState.HeadlineEnd:
            prevBlock = self.currentBlock().previous()
            prevBlock.setUserState(HighlighterState.NoState)
            self.addDirtyBlock(prevBlock)

        self.setCurrentBlockState(HighlighterState.NoState)
        self.currentBlock().setUserState(HighlighterState.NoState)

        self.highlightMarkdown(text)
        self._highlightingFinished = True

    def highlightMarkdown(self, text: str):
        # Check if this is a code block
        isBlockCodeBlock = (self.isCodeBlock(self.previousBlockState()) or
                            text.startswith("```") or
                            text.startswith("~~~"))

        if text and not isBlockCodeBlock:
            self.highlightAdditionalRules(self._highlightingRules, text)

            self.highlightThematicBreak(text)

            # needs to be called after the horizontal ruler highlighting
            self.highlightHeadline(text)
            self.highlightIndentedCodeBlock(text)
            self.highlightLists(text)
            self.highlightInlineRules(text)

        self.highlightCommentBlock(text)
        if isBlockCodeBlock:
            self.highlightCodeFence(text)
        self.highlightFrontmatterBlock(text)

    def highlightAdditionalRules(self, rules: List[HighlightingRule], text: str):
        maskedFormat = self._formats[HighlighterState.MaskedSyntax]
        self._linkRanges.clear()

        for rule in rules:
            # continue if another current block state was already set if
            # disableIfCurrentStateIsSet is set
            if self.currentBlockState() != HighlighterState.NoState:
                continue

            contains = rule.shouldContain in text
            if not contains:
                continue

            iterator = rule.pattern.globalMatch(text)
            capturingGroup = rule.capturingGroup
            maskedGroup = rule.maskedGroup
            charFormat = self._formats[rule.state]

            # find and format all occurrences
            while iterator.hasNext():
                match = iterator.next()

                # if there is a capturingGroup set then first highlight
                # everything as MaskedSyntax and highlight capturingGroup
                # with the real format
                if capturingGroup > 0:
                    currentMaskedFormat = QTextCharFormat(maskedFormat)
                    if charFormat.fontPointSize() > 0:
                        currentMaskedFormat.setFontPointSize(
                            charFormat.fontPointSize())

                    if self.currentBlockState() >= HighlighterState.H1 and self.currentBlockState() <= HighlighterState.H6:
                        pass
                    else:
                        # store masked part of the link as a range
                        if rule.state == HighlighterState.Link:
                            start = match.capturedStart(capturingGroup)
                            end = match.capturedEnd(
                                capturingGroup) + match.capturedLength(maskedGroup)
                            if (start, end) not in self._linkRanges:
                                self._linkRanges.append((start, end))

                        self.setFormat(match.capturedStart(maskedGroup),
                                       match.capturedLength(maskedGroup), currentMaskedFormat)

                if self.currentBlockState() >= HighlighterState.H1 and self.currentBlockState() <= HighlighterState.H6:
                    self.setHeadingStyles(rule.state, match, capturingGroup)
                else:
                    self.setFormat(match.capturedStart(capturingGroup),
                                   match.capturedLength(capturingGroup), charFormat)

    def setHeadingStyles(self, rule: HighlightingRule, match: QRegularExpressionMatch, capturedGroup: int):
        state: HighlighterState = self.currentBlockState()
        f = self._formats[state]

        if rule == HighlighterState.Link:
            linkFmt = self._formats[HighlighterState.Link]
            linkFmt.setFontPointSize(f.fontPointSize())
            if capturedGroup == 1:
                self.setFormat(match.capturedStart(capturedGroup),
                               match.capturedLength(capturedGroup), linkFmt)
            return

    def highlightThematicBreak(self, text: str):
        if not text or text.startswith("    ") or text.startswith("\t"):
            return

        sText = text.strip()
        if not sText:
            return

        if not sText.startswith("-") and \
            not sText.startswith("_") and \
                not sText.startswith("*"):
            return

        c = sText[0]
        hasSameChars = True
        len = 0
        for sc in sText:
            if c != sc and sc != ' ':
                hasSameChars = False
                break
            if sc != " ":
                len += 1
        if len < 3:
            return

        f = self._formats[HighlighterState.HorizontalRuler]
        if c == "-":
            f.setFontLetterSpacing(80)
        elif c == "_":
            f.setFontUnderline(True)

        if hasSameChars:
            self.setFormat(0, len(text), f)

    def highlightHeadline(self, text: str):
        """ Highlight headlines """
        # three spaces indentation is allowed in headings
        spacesOffset = getIndentation(text)

        if spacesOffset >= len(text) or spacesOffset == 4:
            return

        headingFound = text[spacesOffset] == '#'

        if headingFound:
            headingLevel = 0
            i = spacesOffset
            if i >= len(text):
                return
            while i < len(text) and text[i] == '#' and i < (spacesOffset + 6):
                i += 1

            if i < len(text) and text[i] == ' ':
                headingLevel = i - spacesOffset

            if headingLevel > 0:
                state = HighlighterState(
                    HighlighterState.H1 + headingLevel - 1)

                self.setFormat(0, len(text), self._formats[state])

                self.setCurrentBlockState(state)
                return

        def hasOnlyHeadChars(txt, c, spaces):
            if not txt:
                return False
            for i in range(spaces, len(txt)):
                if txt[i] != c:
                    return False
            return True

        # take care of ==== and ---- headlines
        prev = self.currentBlock().previous().text()
        prevSpaces = getIndentation(prev)

        if text[spacesOffset] == '=' and prevSpaces < 4:
            pattern1 = hasOnlyHeadChars(text, '=', spacesOffset)
            if pattern1:
                self.highlightSubHeadline(text, HighlighterState.H1)
                return
        elif text[spacesOffset] == '-' and prevSpaces < 4:
            pattern2 = hasOnlyHeadChars(text, '-', spacesOffset)
            if pattern2:
                self.highlightSubHeadline(text, HighlighterState.H2)
                return

        nextBlockText = self.currentBlock().next().text()
        if not nextBlockText:
            return
        nextSpaces = getIndentation(nextBlockText)

        if nextSpaces >= len(nextBlockText):
            return

        if nextBlockText[nextSpaces] == '=' and nextSpaces < 4:
            nextHasEqualChars = hasOnlyHeadChars(
                nextBlockText, '=', nextSpaces)
            if nextHasEqualChars:
                self.setFormat(
                    0, len(text), self._formats[HighlighterState.H1])
                self.setCurrentBlockState(HighlighterState.H1)
        elif nextBlockText[nextSpaces] == '-' and nextSpaces < 4:
            nextHasMinusChars = hasOnlyHeadChars(
                nextBlockText, '-', nextSpaces)
            if nextHasMinusChars:
                self.setFormat(
                    0, len(text), self._formats[HighlighterState.H2])
                self.setCurrentBlockState(HighlighterState.H2)

    def highlightIndentedCodeBlock(self, text: str):
        """
        Highlight code blocks with four spaces or tabs in front of them
        and no list character after that
        @param text
        """
        if not text or (not text.startswith("    ") and
                        not text.startswith('\t')):
            return
        # previous line must be empty according to CommonMark except if it is a
        # heading https://spec.commonmark.org/0.29/#indented-code-block
        if (self.currentBlock().previous().text().strip() and
            self.previousBlockState() != HighlighterState.CodeBlockIndented and
            (self.previousBlockState() < HighlighterState.H1 or self.previousBlockState() > HighlighterState.H6) and
                self.previousBlockState() != HighlighterState.HeadlineEnd):
            return

        trimmed = text.strip()

        # should not be in a list
        if (trimmed.startswith("- ") or
            trimmed.startswith("+ ") or
            trimmed.startswith("* ") or
                (len(trimmed) >= 1 and trimmed[0].isdigit())):
            return

        self.setCurrentBlockState(HighlighterState.CodeBlockIndented)
        self.setFormat(0, len(text), self._formats[HighlighterState.CodeBlock])

    def highlightCodeFence(self, text: str):
        # already in tilde block
        if (self.previousBlockState() == HighlighterState.CodeBlockTilde or
            self.previousBlockState() == HighlighterState.CodeBlockTildeComment or
                self.previousBlockState() >= HighlighterState.CodeCpp + self.tildeOffset):
            self.highlightCodeBlock(text, "~~~")
        # start of a tilde block
        elif ((self.previousBlockState() != HighlighterState.CodeBlock and
               self.previousBlockState() < HighlighterState.CodeCpp) and
              text.startswith("~~~")):
            self.highlightCodeBlock(text, "~~~")
        else:
            # back tick block
            self.highlightCodeBlock(text)

    def highlightSubHeadline(self, text: str, state: HighlighterState):
        maskedFormat = self._formats[HighlighterState.MaskedSyntax]
        previousBlock = self.currentBlock().previous()
        prevEmpty = not previousBlock.text().strip()

        if prevEmpty:
            return

        # we check for both H1/H2 so that if the user changes his mind, and changes
        # === to ---, changes be reflected immediately
        if (self.previousBlockState() == HighlighterState.H1 or
            self.previousBlockState() == HighlighterState.H2 or
                self.previousBlockState() == HighlighterState.NoState):
            currentMaskedFormat = maskedFormat
            # set the font size from the current rule's font format
            currentMaskedFormat.setFontPointSize(
                self._formats[state].fontPointSize())

            self.setFormat(0, len(text), currentMaskedFormat)
            self.setCurrentBlockState(HighlighterState.HeadlineEnd)

            # we want to re-highlight the previous block
            # this must not done directly, but with a queue, otherwise it
            # will crash
            # setting the character format of the previous text, because this
            # causes text to be formatted the same way when writing after
            # the text
            if self.previousBlockState() != state:
                self.addDirtyBlock(previousBlock)
                previousBlock.setUserState(state)

    def highlightCodeBlock(self, text: str, opener="```"):
        """ Highlight multi-line code blocks """

        if text.startswith(opener):
            # if someone decides to put these on the same line
            # interpret it as inline code, not code block
            if text.endswith("```") and len(text) > 3:
                self.setFormat(3, len(text) - 3,
                               self._formats[HighlighterState.InlineCodeBlock])
                self.setFormat(
                    0, 3, self._formats[HighlighterState.MaskedSyntax])
                self.setFormat(len(text) - 3, 3,
                               self._formats[HighlighterState.MaskedSyntax])
                return

            if ((self.previousBlockState() != HighlighterState.CodeBlock and
                self.previousBlockState() != HighlighterState.CodeBlockTilde) and
                (self.previousBlockState() != HighlighterState.CodeBlockComment and
                self.previousBlockState() != HighlighterState.CodeBlockTildeComment) and
                    self.previousBlockState() < HighlighterState.CodeCpp):
                lang = text[3:].lower()
                progLang = self._langStringToEnum.get(lang)

                if progLang and progLang >= HighlighterState.CodeCpp:
                    state = progLang if text.startswith(
                        "```") else progLang + self.tildeOffset
                    self.setCurrentBlockState(state)
                else:
                    state = HighlighterState.CodeBlock if opener == "```" else HighlighterState.CodeBlockTilde
                    self.setCurrentBlockState(state)
            elif self.isCodeBlock(self.previousBlockState()):
                state = HighlighterState.CodeBlockEnd if opener == "```" else HighlighterState.CodeBlockTildeEnd
                self.setCurrentBlockState(state)

            # set the font size from the current rule's font format
            maskedFormat = self._formats[HighlighterState.MaskedSyntax]
            maskedFormat.setFontPointSize(
                self._formats[HighlighterState.CodeBlock].fontPointSize())

            self.setFormat(0, len(text), maskedFormat)
        elif self.isCodeBlock(self.previousBlockState()):
            self.setCurrentBlockState(self.previousBlockState())
            self.highlightSyntax(text)

    def highlightSyntax(self, text: str):
        """ Does the code syntax highlighting """
        if not text:
            return

        textLen = len(text)

        comment = None
        isCSS = False
        isYAML = False
        isMake = False

        keywords = {}
        others = {}
        types = {}
        builtin = {}
        literals = {}

        state = self.currentBlockState()
        if state in [HighlighterState.CodeCpp,
                     HighlighterState.CodeCpp + self.tildeOffset,
                     HighlighterState.CodeCppComment,
                     HighlighterState.CodeCppComment + self.tildeOffset]:
            loadCppData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeJs,
                       HighlighterState.CodeJs + self.tildeOffset,
                       HighlighterState.CodeJsComment,
                       HighlighterState.CodeJsComment + self.tildeOffset]:
            loadJSData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeC,
                       HighlighterState.CodeC + self.tildeOffset,
                       HighlighterState.CodeCComment,
                       HighlighterState.CodeBlockComment + self.tildeOffset]:
            loadCppData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeBash,
                       HighlighterState.CodeBash + self.tildeOffset]:
            loadShellData(types, keywords, builtin, literals, others)
            comment = '#'
        elif state in [HighlighterState.CodePHP,
                       HighlighterState.CodePHP + self.tildeOffset,
                       HighlighterState.CodePHPComment,
                       HighlighterState.CodePHPComment + self.tildeOffset]:
            loadPHPData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeQML,
                       HighlighterState.CodeQML + self.tildeOffset,
                       HighlighterState.CodeQMLComment,
                       HighlighterState.CodeQMLComment + self.tildeOffset]:
            loadQMLData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodePython,
                       HighlighterState.CodePython + self.tildeOffset]:
            loadPythonData(types, keywords, builtin, literals, others)
            comment = '#'
        elif state in [HighlighterState.CodeRust,
                       HighlighterState.CodeRust + self.tildeOffset,
                       HighlighterState.CodeRustComment,
                       HighlighterState.CodeRustComment + self.tildeOffset]:
            loadRustData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeJava,
                       HighlighterState.CodeJava + self.tildeOffset,
                       HighlighterState.CodeJavaComment,
                       HighlighterState.CodeJavaComment + self.tildeOffset]:
            loadJavaData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeCSharp,
                       HighlighterState.CodeCSharp + self.tildeOffset,
                       HighlighterState.CodeCSharpComment,
                       HighlighterState.CodeCSharpComment + self.tildeOffset]:
            loadCSharpData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeGo,
                       HighlighterState.CodeGo + self.tildeOffset,
                       HighlighterState.CodeGoComment,
                       HighlighterState.CodeGoComment + self.tildeOffset]:
            loadGoData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeV,
                       HighlighterState.CodeV + self.tildeOffset,
                       HighlighterState.CodeVComment,
                       HighlighterState.CodeVComment + self.tildeOffset]:
            loadVData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeSQL,
                       HighlighterState.CodeSQL + self.tildeOffset]:
            loadSQLData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeJSON,
                       HighlighterState.CodeJSON + self.tildeOffset]:
            loadJSONData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeXML,
                       HighlighterState.CodeXML + self.tildeOffset]:
            self.xmlHighlighter(text)
            return
        elif state in [HighlighterState.CodeCSS,
                       HighlighterState.CodeCSS + self.tildeOffset,
                       HighlighterState.CodeCSSComment,
                       HighlighterState.CodeCSSComment + self.tildeOffset]:
            isCSS = True
            loadCSSData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeTypeScript,
                       HighlighterState.CodeTypeScript + self.tildeOffset,
                       HighlighterState.CodeTypeScriptComment,
                       HighlighterState.CodeTypeScriptComment + self.tildeOffset]:
            loadTypeScriptData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeYAML,
                       HighlighterState.CodeYAML + self.tildeOffset]:
            isYAML = True
            comment = '#'
            loadYAMLData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeINI,
                       HighlighterState.CodeINI + self.tildeOffset]:
            self.iniHighlighter(types, keywords, builtin, literals, others)
            return
        elif state in [HighlighterState.CodeTaggerScript,
                       HighlighterState.CodeTaggerScript + self.tildeOffset]:
            self.taggerScriptHighlighter(text)
            return
        elif state in [HighlighterState.CodeVex,
                       HighlighterState.CodeVex + self.tildeOffset,
                       HighlighterState.CodeVexComment,
                       HighlighterState.CodeVexComment + self.tildeOffset]:
            loadVexData(types, keywords, builtin, literals, others)
        elif state in [HighlighterState.CodeMake,
                       HighlighterState.CodeCMake + self.tildeOffset]:
            loadCMakeData(types, keywords, builtin, literals, others)
            comment = "#"
        elif state in [HighlighterState.CodeMake,
                       HighlighterState.CodeMake + self.tildeOffset]:
            isMake = True
            loadMakeData(types, keywords, builtin, literals, others)
            comment = "#"
        else:
            comment = ""

        # apply the default code block format first
        self.setFormat(0, textLen, self._formats[HighlighterState.CodeBlock])

        def applyCodeFormat(i, data: Dict[str, str], text: str, fmt):
            # check if we are at the beginning OR if this is the start of a word
            if i == 0 or not text[i - 1].isalpha():
                wordList = data.get(text[i].lower(), [])
                for word in wordList:
                    # we have a word match check
                    # 1. if we are at the end
                    # 2. if we have a complete word
                    if (text[i:i+len(word)] == word and
                        (i + len(word) == len(text) or
                         not text[i + len(word)].isalpha())):
                        self.setFormat(i, len(word), fmt)
                        i += len(word)
            return i

        formatType = self._formats[HighlighterState.CodeType]
        formatKeyword = self._formats[HighlighterState.CodeKeyWord]
        formatComment = self._formats[HighlighterState.CodeComment]
        formatNumLit = self._formats[HighlighterState.CodeNumLiteral]
        formatBuiltIn = self._formats[HighlighterState.CodeBuiltIn]
        formatOther = self._formats[HighlighterState.CodeOther]

        i = 0

        def _handleComment():
            next = text.find("*/", i)
            if next == -1:
                # we didn't find a comment end.
                # Check if we are already in a comment block
                if self.currentBlockState() % 2 == 0:
                    self.setCurrentBlockState(
                        self.currentBlockState() + 1)
                self.setFormat(i, textLen - i, formatComment)
                return True
            else:
                # we found a comment end
                # mark this block as code if it was previously
                # comment. First check if the comment ended on the
                # same line. if modulo 2 is not equal to zero, it
                # means we are in a comment, -1 will set this
                # block's state as language
                if self.currentBlockState() % 2 != 0:
                    self.setCurrentBlockState(
                        self.currentBlockState() - 1)
                next += 2
                self.setFormat(i, next - i, formatComment)
                i = next
                if i >= textLen:
                    return True
            return False

        while i < textLen:
            if self.currentBlockState() != -1 and self.currentBlockState() % 2 != 0:
                if _handleComment():
                    return

            while i < textLen and not text[i].isalpha():
                if text[i].isspace():
                    i += 1
                    # make sure we don't cross the bound
                    if i == textLen:
                        break
                    if text[i].isalpha():
                        break
                    continue
                # inline comment
                if comment is None and text[i] == '/':
                    if i + 1 < textLen:
                        if text[i + 1] == '/':
                            self.setFormat(i, textLen - i, formatComment)
                            return
                        elif text[i + 1] == '*':
                            if _handleComment():
                                return
                elif text[i] == comment:
                    self.setFormat(i, textLen - i, formatComment)
                    i = textLen
                    break
                # integer literal
                elif text[i].isdigit():
                    i = self.highlightNumericLiterals(text, i)
                # string literals
                elif text[i] == '"' or text[i] == "'":
                    i = self.highlightStringLiterals(text[i], text, i)

                if i >= textLen:
                    break
                i += 1

            pos = i
            if i == textLen or not text[i].isalpha():
                continue

            # Highlight Types
            i = applyCodeFormat(i, types, text, formatType)

            # next letter is usually a space, in that case
            # going forward is useless, so continue;
            if i == textLen or not text[i].isalpha():
                continue

            # Highlight Keywords
            i = applyCodeFormat(i, keywords, text, formatKeyword)
            if i == textLen or not text[i].isalpha():
                continue

            # Highlight Literals (true/false/NULL,nullptr)
            i = applyCodeFormat(i, literals, text, formatNumLit)
            if i == textLen or not text[i].isalpha():
                continue

            # Highlight Builtin library stuff
            i = applyCodeFormat(i, builtin, text, formatBuiltIn)
            if i == textLen or not text[i].isalpha():
                continue

            # Highlight other stuff (preprocessor etc.)
            if i == 0 or not text[i - 1].isalpha():
                wordList = others.get(text[i].lower(), [])
                for word in wordList:
                    if (text[i:i+len(word)] == word and
                        (i + len(word) == len(text) or
                         not text[i + len(word)].isalpha())):
                        if self.currentBlockState() == HighlighterState.CodeCpp or self.currentBlockState() == HighlighterState.CodeC:
                            self.setFormat(i - 1, len(word) + 1, formatOther)
                        else:
                            self.setFormat(i, len(word), formatOther)
                        i += len(word)

            # we were unable to find any match, lets skip this word
            if pos == i:
                cnt = i
                while cnt < textLen:
                    if not text[cnt].isalpha():
                        break
                    cnt += 1
                i = cnt

        # POST PROCESSORS
        if isCSS:
            self.cssHighlighter(text)
        if isYAML:
            self.ymlHighlighter(text)
        if isMake:
            self.makeHighlighter(text)

    def highlightStringLiterals(self, strType: str, text: str, i: int):
        """ Highlight string literals in code """
        self.setFormat(i, 1, self._formats[HighlighterState.CodeString])
        i += 1

        while i < len(text):
            # look for string end
            # make sure it's not an escape seq
            if text[i] == strType and text[i - 1] != '\\':
                self.setFormat(
                    i, 1, self._formats[HighlighterState.CodeString])
                i += 1
                break
            # look for escape sequence
            if text[i] == '\\' and (i + 1) < len(text):
                length = 0
                nextChar = text[i + 1]

                if nextChar in ['a', 'b', 'e', 'f', 'n', 'r', 't', 'v', "'", '"', '\\', '?']:
                    # 2 because we have to highlight \ as well as the following char
                    length = 2
                # octal esc sequence \123
                elif nextChar in ['0', '1', '2', '3', '4', '5', '6', '7']:
                    if i + 4 <= len(text):
                        isCurrentOctal = True
                        if not self.isOctal(text[i + 2]):
                            isCurrentOctal = False
                        if not self.isOctal(text[i + 3]):
                            isCurrentOctal = False
                        length = 4 if isCurrentOctal else 0
                # hex numbers \xFA
                elif nextChar == 'x':
                    if i + 3 <= len(text):
                        isCurrentHex = True
                        if not self.isHex(text[i + 2]):
                            isCurrentHex = False
                        if not self.isHex(text[i + 3]):
                            isCurrentHex = False
                        length = 4 if isCurrentHex else 0
                # TODO: implement unicode code point escaping

                # if len is zero, that means this wasn't an esc seq
                # increment i so that we skip this backslash
                if length == 0:
                    self.setFormat(
                        i, 1, self._formats[HighlighterState.CodeString])
                    i += 1
                    continue

                self.setFormat(
                    i, length, self._formats[HighlighterState.CodeNumLiteral])
                i += length
                continue

            self.setFormat(i, 1, self._formats[HighlighterState.CodeString])
            i += 1

        return i

    def highlightNumericLiterals(self, text: str, i: int):
        """
        @brief Highlight numeric literals in code
        @param text the text being scanned
        @param i pos of i in loop
        @return pos of i after the number
        
        @details it doesn't highlight the following yet:
         - 1000'0000
        """
        isPrefixAllowed = False
        if i == 0:
            isPrefixAllowed = True
        else:
            # these values are allowed before a number
            prevChar = text[i - 1]
            if prevChar == ':' and self.currentBlockState() == HighlighterState.CodeCSS:
                isPrefixAllowed = True
            elif prevChar in ['[', '(', '{', ' ', ',', '=', '+', '-', '*', '/', '%', '<', '>']:
                isPrefixAllowed = True

        if not isPrefixAllowed:
            return i

        start = i

        if (i + 1) >= len(text):
            self.setFormat(
                i, 1, self._formats[HighlighterState.CodeNumLiteral])
            return i + 1

        i += 1
        # hex numbers highlighting (only if there's a preceding zero)
        isCurrentHex = False
        if i < len(text) and text[i] == 'x' and text[i - 1] == '0':
            isCurrentHex = True
            i += 1

        while i < len(text):
            if (not text[i].isdigit() and text[i] != '.' and
                text[i] != 'e' and
                    not (isCurrentHex and self.isHex(text[i]))):
                break
            i += 1

        isPostfixAllowed = False
        if i == len(text):
            # cant have e at the end
            if isCurrentHex or (not isCurrentHex and text[i - 1] != 'e'):
                isPostfixAllowed = True
        else:
            # these values are allowed after a number
            nextChar = text[i]
            if nextChar in [']', ')', '}', ' ', ',', '=', '+', '-', '*', '/', '%', '>', '<', ';']:
                isPostfixAllowed = True
            # for 100u, 1.0F
            elif nextChar == 'p' and self.currentBlockState() == HighlighterState.CodeCSS:
                if i + 1 < len(text) and text[i + 1] == 'x':
                    if i + 2 == len(text) or not (text[i + 2].isalpha() or text[i + 2].isdigit()):
                        isPostfixAllowed = True
            elif nextChar == 'e' and self.currentBlockState() == HighlighterState.CodeCSS:
                if i + 1 < len(text) and text[i + 1] == 'm':
                    if i + 2 == len(text) or not (text[i + 2].isalpha() or text[i + 2].isdigit()):
                        isPostfixAllowed = True
            elif nextChar in ['u', 'l', 'f', 'U', 'L', 'F']:
                if i + 1 == len(text) or not (text[i + 1].isalpha() or text[i + 1].isdigit()):
                    isPostfixAllowed = True
                    i += 1

        if isPostfixAllowed:
            end = i
            i -= 1
            self.setFormat(start, end - start,
                           self._formats[HighlighterState.CodeNumLiteral])

        # decrement so that the index is at the last number, not after it
        return i

    def taggerScriptHighlighter(self, text: str):
        """
        The Tagger Script highlighter
        
        This function is responsible for taggerscript highlighting.
        It highlights anything between a (inclusive) '$' and a (exclusive) '(' as a
        function. An exception is the '$noop()'function, which get highlighted as a
        comment.
        
        It has basic error detection when there is an unlcosed %Metadata Variable%
        """
        if not text:
            return

        textLen = len(text)

        i = 0
        while i < textLen:
            # highlight functions, unless it's a comment function
            if text[i] == '$' and (i + 4 >= textLen or text[i:i+5] != "$noop"):
                nextPos = text.find('(', i)
                if nextPos == -1:
                    break
                self.setFormat(
                    i, nextPos - i, self._formats[HighlighterState.CodeKeyWord])
                i = nextPos

            # highlight variables
            if i < textLen and text[i] == '%':
                nextPos = text.find('%', i + 1)
                start = i
                i += 1
                if nextPos != -1:
                    self.setFormat(start, nextPos - start + 1,
                                   self._formats[HighlighterState.CodeType])
                else:
                    # error highlighting
                    errorFormat = self._formats[HighlighterState.NoState]
                    errorFormat.setUnderlineColor(Qt.red)
                    errorFormat.setUnderlineStyle(
                        QTextCharFormat.WaveUnderline)
                    self.setFormat(start, 1, errorFormat)

            # highlight comments
            if i < textLen and i + 4 < textLen and text[i:i+5] == "$noop":
                nextPos = text.find(')', i)
                if nextPos == -1:
                    break
                self.setFormat(i, nextPos - i + 1,
                               self._formats[HighlighterState.CodeComment])
                i = nextPos

            # highlight escape chars
            if i < textLen and text[i] == '\\':
                self.setFormat(i, 2, self._formats[HighlighterState.CodeOther])
                i += 1

            i += 1

    def ymlHighlighter(self, text: str):
        """
        @brief The YAML highlighter
        @param text
        @details This function post processes a line after the main syntax
        highlighter has run for additional highlighting. It does these things
        
        If the current line is a comment, skip it
        
        Highlight all the words that have a colon after them as 'keyword' except:
        If the word is a string, skip it.
        If the colon is in between a path, skip it (C:\\)
        
        Once the colon is found, the function will skip every character except 'h'
        
        If an h letter is found, check the next 4/5 letters for http/https and
        highlight them as a link (underlined)
        """
        if not text:
            return
        textLen = len(text)
        colonNotFound = False

        # if this is a comment don't do anything and just return
        if text.strip() and text.strip()[0] == '#':
            return

        i = 0
        while i < textLen:
            if not text[i].isalpha():
                i += 1
                continue

            if colonNotFound and text[i] != 'h':
                i += 1
                continue

            # we found a string literal, skip it
            if i != 0 and text[i-1] == '"':
                nextPos = text.find('"', i)
                if nextPos == -1:
                    break
                i = nextPos + 1
                continue

            if i != 0 and text[i-1] == "'":
                nextPos = text.find("'", i)
                if nextPos == -1:
                    break
                i = nextPos + 1
                continue

            colon = text.find(':', i)

            # if colon isn't found, we set this true
            if colon == -1:
                colonNotFound = True

            if not colonNotFound:
                # if the line ends here, format and return
                if colon + 1 == textLen:
                    self.setFormat(
                        i, colon - i, self._formats[HighlighterState.CodeKeyWord])
                    return
                # colon is found, check if it isn't some path or something else
                if not (text[colon + 1] == '\\' and text[colon + 1] == '/'):
                    self.setFormat(
                        i, colon - i, self._formats[HighlighterState.CodeKeyWord])

            # underlined links
            if text[i] == 'h':
                if text[i:i+5] == "https" or text[i:i+4] == "http":
                    space = text.find(' ', i)
                    if space == -1:
                        space = textLen
                    f = QTextCharFormat(
                        self._formats[HighlighterState.CodeString])
                    f.setUnderlineStyle(
                        QTextCharFormat.UnderlineStyle.SingleUnderline)
                    self.setFormat(i, space - i, f)
                    i = space

            i += 1

    def iniHighlighter(self, text: str):
        """
        @brief The INI highlighter
        @param text The text being highlighted
        @details This function is responsible for ini highlighting.
        It has basic error detection when
        (1) You opened a section but didn't close with bracket e.g [Section
        (2) You wrote an option but it didn't have an '='
        Such errors will be marked with a dotted red underline
        
        It has comment highlighting support. Everything after a ';' will
        be highlighted till the end of the line.
        
        An option value pair will be highlighted regardless of space. Example:
        Option 1 = value
        In this, 'Option 1' will be highlighted completely and not just '1'.
        I am not sure about its correctness but for now its like this.
        
        The loop is unrolled frequently upon a match. Before adding anything
        new be sure to test in debug mode and apply bound checking as required.
        """
        if not text:
            return
        textLen = len(text)

        i = 0
        while i < textLen:
            # start of a [section]
            if text[i] == '[':
                sectionFormat = QTextCharFormat(
                    self._formats[HighlighterState.CodeType])
                sectionEnd = text.find(']', i)
                # if an end bracket isn't found, we apply red underline to show error
                if sectionEnd == -1:
                    sectionFormat.setUnderlineStyle(
                        QTextCharFormat.UnderlineStyle.DotLine)
                    sectionFormat.setUnderlineColor(Qt.red)
                    sectionEnd = textLen
                else:
                    sectionEnd += 1

                self.setFormat(i, sectionEnd - i, sectionFormat)
                i = sectionEnd
                if i >= textLen:
                    break

            # comment ';'
            elif text[i] == ';':
                self.setFormat(
                    i, textLen - i, self._formats[HighlighterState.CodeComment])
                i = textLen
                break

            # key-val
            elif text[i].isalpha():
                format = QTextCharFormat(
                    self._formats[HighlighterState.CodeKeyWord])
                equalsPos = text.find('=', i)
                if equalsPos == -1:
                    format.setUnderlineColor(Qt.red)
                    format.setUnderlineStyle(
                        QTextCharFormat.UnderlineStyle.DotLine)
                    equalsPos = textLen

                self.setFormat(i, equalsPos - i, format)
                i = equalsPos - 1
                if i >= textLen:
                    break

            # skip everything after '=' (except comment)
            elif text[i] == '=':
                findComment = text.find(';', i)
                if findComment == -1:
                    break
                i = findComment - 1

            i += 1

    def cssHighlighter(self, text: str):
        if not text:
            return
        textLen = len(text)
        i = 0
        while i < textLen:
            if text[i] == '.' or text[i] == '#':
                if i + 1 >= textLen:
                    return
                if text[i + 1].isspace() or text[i + 1].isdigit():
                    i += 1
                    continue
                space = text.find(' ', i)
                if space < 0:
                    space = text.find('{', i)
                    if space < 0:
                        space = textLen
                self.setFormat(
                    i, space - i, self._formats[HighlighterState.CodeKeyWord])
                i = space
            elif text[i] == 'c':
                if text[i:i+5] == "color":
                    i += 5
                    colon = text.find(':', i)
                    if colon < 0:
                        i += 1
                        continue
                    i = colon
                    i += 1
                    while i < textLen:
                        if not text[i].isspace():
                            break
                        i += 1
                    semicolon = text.find(';', i)
                    if semicolon < 0:
                        semicolon = textLen
                    color = text[i:semicolon]
                    f = self._formats[HighlighterState.CodeBlock]
                    c = QColor(color)
                    if color.startswith("rgb"):
                        t = text.find('(', i)
                        rPos = text.find(',', t)
                        gPos = text.find(',', rPos + 1)
                        bPos = text.find(')', gPos)
                        if rPos > -1 and gPos > -1 and bPos > -1:
                            r = text[t+1:rPos]
                            g = text[rPos+1:gPos]
                            b = text[gPos+1:bPos]
                            c.setRgb(int(r), int(g), int(b))
                        else:
                            c = self._formats[HighlighterState.NoState].background(
                            ).color()

                    if not c.isValid():
                        i += 1
                        continue

                    lightness = 0
                    foreground = QColor()
                    # really dark
                    if c.lightness() <= 20:
                        foreground = Qt.white
                    elif c.lightness() > 20 and c.lightness() <= 51:
                        foreground = QColor(204, 204, 204)
                    elif c.lightness() > 51 and c.lightness() <= 110:
                        foreground = QColor(187, 187, 187)
                    elif c.lightness() > 127:
                        lightness = c.lightness() + 100
                        foreground = c.darker(lightness)
                    else:
                        lightness = c.lightness() + 100
                        foreground = c.lighter(lightness)

                    f.setBackground(c)
                    f.setForeground(foreground)
                    # clear prev format
                    self.setFormat(i, semicolon - i, QTextCharFormat())
                    self.setFormat(i, semicolon - i, f)
                    i = semicolon
                else:
                    i += 1
            else:
                i += 1

    def xmlHighlighter(self, text: str):
        if not text:
            return

        textLen = len(text)
        self.setFormat(0, textLen, self._formats[HighlighterState.CodeBlock])

        i = 0
        while i < textLen:
            if i + 1 < textLen and text[i] == '<' and text[i + 1] != '!':
                found = text.find('>', i)
                if found > 0:
                    i += 1
                    if text[i] == '/':
                        i += 1
                    self.setFormat(
                        i, found - i, self._formats[HighlighterState.CodeKeyWord])

            if text[i] == '=':
                lastSpace = text.rfind(' ', 0, i)
                if lastSpace == i - 1:
                    lastSpace = text.rfind(' ', 0, i - 2)
                if lastSpace > 0:
                    self.setFormat(lastSpace, i - lastSpace,
                                   self._formats[HighlighterState.CodeBuiltIn])

            if text[i] == '"':
                pos = i
                cnt = 1
                i += 1
                # bound check
                if (i + 1) >= textLen:
                    return
                while i < textLen:
                    if text[i] == '"':
                        cnt += 1
                        i += 1
                        break
                    i += 1
                    cnt += 1
                    # bound check
                    if (i + 1) >= textLen:
                        cnt += 1
                        break
                self.setFormat(
                    pos, cnt, self._formats[HighlighterState.CodeString])
            i += 1

    def makeHighlighter(self, text: str):
        colonPos = text.find(':')
        if colonPos == -1:
            return
        self.setFormat(
            0, colonPos, self._formats[HighlighterState.CodeBuiltIn])

    def highlightFrontmatterBlock(self, text):
        """ Highlight multi-line frontmatter blocks """

        # return if there is no frontmatter in this document
        if self.document().firstBlock().text() != "---":
            return

        if text == "---":
            foundEnd = self.previousBlockState() == HighlighterState.FrontmatterBlock

            # return if the frontmatter block was already highlighted in previous
            # blocks, there just can be one frontmatter block
            if not foundEnd and self.document().firstBlock() != self.currentBlock():
                return

            self.setCurrentBlockState(HighlighterState.FrontmatterBlockEnd if foundEnd
                                      else HighlighterState.FrontmatterBlock)

            maskedFormat = self._formats[HighlighterState.MaskedSyntax]
            self.setFormat(0, len(text), maskedFormat)
        elif self.previousBlockState() == HighlighterState.FrontmatterBlock:
            self.setCurrentBlockState(HighlighterState.FrontmatterBlock)
            self.setFormat(
                0, len(text), self._formats[HighlighterState.MaskedSyntax])

    def highlightCommentBlock(self, text: str):
        """ Highlight multi-line comments """
        if text.startswith("    ") or text.startswith('\t'):
            return

        trimmedText = text.strip()
        startText = "<!--"
        endText = "-->"

        # we will skip this case because that is an inline comment and causes
        # troubles here
        if trimmedText.startswith(startText) and endText in trimmedText:
            return

        if not trimmedText.startswith(startText) and startText in trimmedText:
            return

        isComment = (trimmedText.startswith(startText) or
                     (not trimmedText.endswith(endText) and self.previousBlockState() == HighlighterState.Comment))
        isCommentEnd = trimmedText.endswith(
            endText) and self.previousBlockState() == HighlighterState.Comment
        highlight = isComment or isCommentEnd

        if isComment:
            self.setCurrentBlockState(HighlighterState.Comment)
        if highlight:
            self.setFormat(
                0, len(text), self._formats[HighlighterState.Comment])

    def highlightLists(self, text: str):
        """ Highlight lists in markdown """
        spaces = 0
        while spaces < len(text) and text[spaces].isspace():
            spaces += 1

        if spaces >= len(text):
            return

        # check for start of list
        if (text[spaces] != '-' and
            text[spaces] != '+' and
            text[spaces] != '*' and
                not text[spaces].isdigit()):  # ordered
            return

        # Ordered List
        if text[spaces].isdigit():
            number = spaces
            while number < len(text) and text[number].isdigit():
                number += 1

            if number + 1 >= len(text):
                return
            # there should be a '.' or ')' after a number
            if ((text[number] == '.' or text[number] == ')') and
                    text[number + 1] == ' '):
                self.setCurrentBlockState(HighlighterState.List)
                self.setFormat(spaces, number - spaces + 1,
                               self._formats[HighlighterState.List])
            return

        if spaces + 1 >= len(text):
            return
        # check for a space after it
        if text[spaces + 1] != ' ':
            return

        # check if we are in checkbox list
        if spaces + 2 < len(text) and text[spaces + 2] == '[':
            if spaces + 4 >= len(text):
                return
            start = spaces + 2
            length = 3
            # checked checkbox
            if text[spaces + 3] == 'x' and text[spaces + 4] == ']':
                self.setFormat(
                    start, length, self._formats[HighlighterState.CheckBoxChecked])
            # unchecked checkbox
            elif text[spaces + 3] == ' ' and text[spaces + 4] == ']':
                self.setFormat(
                    start, length, self._formats[HighlighterState.CheckBoxUnChecked])
            # unchecked checkbox with no space bw brackets
            elif text[spaces + 3] == ']':
                self.setFormat(
                    start, 2, self._formats[HighlighterState.CheckBoxUnChecked])

        # Unordered List
        self.setCurrentBlockState(HighlighterState.List)
        self.setFormat(spaces, 1, self._formats[HighlighterState.List])

    def highlightInlineRules(self, text: str):
        """
        Highlight inline rules aka Emphasis, bolds, inline code spans,
        underlines, strikethrough.
        """
        if not text:
            return

        isEmStrongDone = False

        # TODO: Add Links and Images parsing
        i = 0
        while i < len(text):
            # make sure we are not in a link range
            if self._linkRanges:
                res = isInLinkRange(i, self._linkRanges)
                if res > -1:
                    i += res
                    continue

            if text[i] == '`' or text[i] == '~':
                i = self.highlightInlineSpans(text, i, text[i])
            elif (text[i] == '<' and i + 3 < len(text) and
                  text[i + 1] == '!' and text[i + 2] == '-' and text[i + 3] == '-'):
                i = self.highlightInlineComment(text, i)
            elif not isEmStrongDone and (text[i] == '*' or text[i] == '_'):
                self.highlightEmAndStrong(text, i)
                isEmStrongDone = True

            i += 1

    def highlightInlineSpans(self, text: str, currentPos: int, c: str):
        """ highlight inline code spans -> `code` and highlight strikethroughs """

        if currentPos + 1 >= len(text):
            return currentPos

        for i in range(currentPos, len(text)):
            if text[i] != c:
                continue

            # found a backtick
            length = 0
            pos = i

            if i != 0 and text[i - 1] == '\\':
                continue

            # keep moving forward in backtick sequence
            while pos < len(text) and text[pos] == c:
                length += 1
                pos += 1

            seq = text[i:i+length]
            start = i
            i += length
            next = text.find(seq, i)
            if next == -1:
                return currentPos + length

            if next + length < len(text) and text[next + length] == c:
                continue

            fmt = self.format(start + i)
            inlineFmt = self._formats[HighlighterState.NoState]
            if c != "~":
                inlineFmt = self._formats[HighlighterState.InlineCodeBlock]

            inlineFmt.setFontUnderline(fmt.fontUnderline())
            inlineFmt.setUnderlineStyle(fmt.underlineStyle())
            if fmt.fontPointSize() > 0:
                inlineFmt.setFontPointSize(fmt.fontPointSize())
            inlineFmt.setFontItalic(fmt.fontItalic())

            if c == "~":
                inlineFmt.setFontStrikeOut(True)

            self.setFormat(start + 1, next - start, inlineFmt)

            # highlight backticks as masked
            self.setFormat(
                start, length, self._formats[HighlighterState.MaskedSyntax])
            self.setFormat(
                next, length, self._formats[HighlighterState.MaskedSyntax])

            i = next + length

        return currentPos

    def highlightInlineComment(self, text: str, pos: int):
        """ highlight inline comments in markdown <!-- comment --> """

        start = pos
        pos += 4

        if pos >= len(text):
            return pos

        commentEnd = text.find('-->', pos)
        if commentEnd == -1:
            return pos

        commentEnd += 3
        self.setFormat(start, commentEnd - start,
                       self._formats[HighlighterState.Comment])

        return commentEnd - 1

    def highlightEmAndStrong(self, text: str, pos: int):
        """ highlights Em/Strong in text editor """

        # 1. collect all em/strong delimiters
        delims: List[Delimiter] = []
        i = 0
        while i < len(text):
            if text[i] != "_" and text[i] != "*":
                i += 1
                continue
            i = collectEmDelims(text, i, delims)

        # 2. Balance pairs
        balancePairs(delims)

        # start,length -> helper for applying masking later
        masked: List[tuple[int, int]] = []

        # 3. final processing & highlighting
        for i in range(len(delims) - 1, 0, -1):
            startDelim = delims[i]
            if startDelim.marker != "_" and startDelim.marker != "*":
                continue
            if startDelim.end == -1:
                continue

            endDelim = delims[startDelim.end]

            isStrong = i > 0 and delims[i - 1].end == startDelim.end + 1 and \
                delims[i - 1].pos == startDelim.pos - 1 and \
                delims[startDelim.end + 1].pos == endDelim.pos + 1 and \
                delims[i - 1].marker == startDelim.marker
            if isStrong:
                k = startDelim.pos
                while text[k] == startDelim.marker:
                    k += 1  # look for first letter after the delim chain

                # per character highlighting
                boldLen = endDelim.pos - startDelim.pos
                underline = (self._highlightingOptions & HighlightingOptions.Underline) and \
                    startDelim.marker == "_"
                while k != (startDelim.pos + boldLen):
                    fmt = self.format(k)
                    # if we are in plains text, use the format's specified color
                    if fmt.foreground() == QTextCharFormat().foreground():
                        fmt.setForeground(
                            self._formats[HighlighterState.Bold].foreground())
                    if underline:
                        fmt.setFontUnderline(True)
                    else:
                        fmt.setFontWeight(QFont.Bold)
                    self.setFormat(k, 1, fmt)
                    k += 1

                masked.append((startDelim.pos - 1, 2))
                masked.append((endDelim.pos, 2))
                i -= 1
            else:
                k = startDelim.pos
                while text[k] == startDelim.marker:
                    k += 1

                underline = self._highlightingOptions & HighlightingOptions.Underline and \
                    startDelim.marker == "_"
                itLen = endDelim.pos - startDelim.pos
                while k != startDelim.pos + itLen:
                    fmt = self.format(k)
                    if fmt.foreground() == QTextCharFormat().foreground():
                        fmt.setForeground(
                            self._formats[HighlighterState.Italic].foreground())
                    if underline:
                        fmt.setFontUnderline(True)
                    else:
                        fmt.setFontItalic(True)
                    self.setFormat(k, 1, fmt)
                    k += 1
                masked.append((startDelim.pos, 1))
                masked.append((endDelim.pos, 1))

        # 4. Apply masked syntax
        for i in range(len(masked)):
            maskedFmt = self._formats[HighlighterState.MaskedSyntax]
            state: HighlighterState = self.currentBlockState()
            if self._formats[state].fontPointSize() > 0:
                maskedFmt.setFontPointSize(
                    self._formats[state].fontPointSize())
            self.setFormat(masked[i][0], masked[i][1], maskedFmt)
