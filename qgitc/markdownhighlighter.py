# -*- coding: utf-8 -*-

import string
from enum import Enum, Flag, IntEnum
from typing import Dict, List

from PySide6.QtCore import (
    QFlag,
    QRegularExpression,
    QRegularExpressionMatch,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QSyntaxHighlighter,
    QTextBlock,
    QTextCharFormat,
    QTextDocument,
    QTextFormat,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.colorschema import ColorSchema
from qgitc.diffutils import diff_begin_re
from qgitc.languagedata import *

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
    StUnderline = 31

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
    CodeSQLComment = 225
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
    CodeNix = 246,
    CodeForth = 248
    CodeForthComment = 249
    CodeSystemVerilog = 250
    CodeSystemVerilogComment = 251
    CodeGDScript = 252
    CodeTOML = 254
    CodeTOMLString = 255
    Diff = 300


class HighlightingRule:

    def __init__(self, state: HighlighterState):
        self.pattern = QRegularExpression()
        self.shouldContain = ""
        self.state = state
        self.capturingGroup = 0
        self.maskedGroup = 0


class RangeType(Enum):
    CodeSpan = 0
    Emphasis = 1
    Link = 2


class InlineRange:
    def __init__(self, begin: int, end: int, type: RangeType):
        self.begin = begin
        self.end = end
        self.type = type


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


def isParagraph(text: str):
    # blank line
    if not text:
        return False

    indent = getIndentation(text)
    # code block
    if indent >= 4:
        return False

    textView = text[indent:-1]
    if not textView:
        return False

    # unordered listtextView
    if textView.startswith("- ") or \
            textView.startswith("+ ") or \
            textView.startswith("* "):
        return False

    # block quote
    if textView.startswith("> "):
        return False

    # atx heading
    if textView.startswith("#"):
        firstSpace = textView.find(' ')
        if firstSpace > 0 and firstSpace <= 7:
            return False

    # hr
    def isThematicBreak():
        return (all(ch == '-' or ch == ' ' or ch == '\t' for ch in textView) or
                all(ch == '+' or ch == ' ' or ch == '\t' for ch in textView) or
                all(ch == '*' or ch == ' ' or ch == '\t' for ch in textView))

    if isThematicBreak():
        return False

    # ordered list
    if textView[0].isdigit():
        i = 1
        count = 1
        while i < len(textView):
            if textView[i].isdigit():
                count += 1
                i += 1
                continue
            else:
                break

        # ordered list marker can't be more than 9 numbers
        if (count <= 9 and i + 1 < len(textView) and
            (textView[i] == '.' or
             textView[i] == ')') and
                textView[i + 1] == ' '):
            return False

    return True


def isBeginningOfList(front: str):
    return front == '-' or front == '+' or front == '*' or front.isdigit()


supportedSchemes = {
    "http://",  "https://",
    "file://",  "www.",
    "ftp://",   "mailto:",
    "tel:",     "sms:",
    "smsto:",   "data:",
    "irc://",   "gopher://",
    "spotify:", "steam:",
    "bitcoin:", "magnet:",
    "ed2k://",  "news:",
    "ssh://",   "note://"
}


def isLink(text: str):
    for scheme in supportedSchemes:
        if text.startswith(scheme):
            return True

    return False


def isValidEmail(email: str):
    # Check for a single '@' character
    atIndex = email.find('@')
    if atIndex == -1:
        return False

    # Check for at least one character before and after '@'
    if atIndex == 0 or atIndex == email.length() - 1:
        return False

    # Split email into local part and domain
    localPart = email[:atIndex]
    domain = email[atIndex + 1:]

    # Check local part for validity (e.g., no consecutive dots)
    if not localPart or ".." in localPart:
        return False

    # Check domain for validity (e.g., at least one dot)
    if not domain or domain.find('.') == -1:
        return False

    return True


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
        self._ranges: Dict[int, list] = {}
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
                state >= HighlighterState.CodeCpp or
                state == HighlighterState.Diff)

    @staticmethod
    def setTextFormats(formats: Dict[HighlighterState, QTextCharFormat]):
        MarkdownHighlighter._formats = formats

    @staticmethod
    def setTextFormat(state: HighlighterState, format_: QTextCharFormat):
        MarkdownHighlighter._formats[state] = format_

    @staticmethod
    def isHeading(state: HighlighterState):
        return HighlighterState.H1 <= state <= HighlighterState.H6

    def clearDirtyBlocks(self):
        self._dirtyTextBlocks.clear()

    def setHighlightingOptions(self, options: HighlightingOptions):
        self._highlightingOptions = options

    def initHighlightingRules(self):
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

        # Trailing spaces
        rule = HighlightingRule(HighlighterState.TrailingSpace)
        rule.pattern = QRegularExpression(r"( +)$")
        # Note: Python string handling is different, this might need adjustment
        rule.shouldContain = "  "
        rule.capturingGroup = 1
        self._highlightingRules.append(rule)

        # Inline comments for Markdown
        rule = HighlightingRule(HighlighterState.Comment)
        rule.pattern = QRegularExpression(r"^\[.+?\]: # \(.+?\)$")
        rule.shouldContain = "]: # ("
        self._highlightingRules.append(rule)

        # Tables with starting |
        rule = HighlightingRule(HighlighterState.Table)
        rule.shouldContain = "|"
        # Support up to 3 leading spaces, because md4c seems to support it
        # See https://github.com/pbek/QOwnNotes/issues/3137
        rule.pattern = QRegularExpression(r"^\\s{0,3}(\\|.+?\\|)$")
        rule.capturingGroup = 1
        self._highlightingRules.append(rule)

    @staticmethod
    def initTextFormats():
        formats = {}

        schema: ColorSchema = ApplicationBase.instance().colorSchema()

        # Set character formats for headlines
        charFormat = QTextCharFormat()
        charFormat.setForeground(schema.Heading)
        charFormat.setFontWeight(QFont.Bold)
        charFormat.setProperty(QTextFormat.FontSizeAdjustment, 3)
        formats[HighlighterState.H1] = QTextCharFormat(charFormat)

        charFormat.setProperty(QTextFormat.FontSizeAdjustment, 2)
        formats[HighlighterState.H2] = QTextCharFormat(charFormat)

        charFormat.setProperty(QTextFormat.FontSizeAdjustment, 1)
        formats[HighlighterState.H3] = QTextCharFormat(charFormat)

        formats[HighlighterState.H4] = QTextCharFormat(charFormat)

        charFormat.setProperty(QTextFormat.FontSizeAdjustment, -1)
        formats[HighlighterState.H5] = QTextCharFormat(charFormat)

        charFormat.setProperty(QTextFormat.FontSizeAdjustment, -2)
        formats[HighlighterState.H6] = QTextCharFormat(charFormat)

        # Set character format for horizontal rulers
        charFormat = QTextCharFormat()
        charFormat.setForeground(schema.HorizontalRuler)
        formats[HighlighterState.HorizontalRuler] = charFormat

        # Set character format for lists
        charFormat = QTextCharFormat()
        charFormat.setForeground(schema.List)
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
        charFormat.setForeground(
            ApplicationBase.instance().palette().link().color())
        charFormat.setFontUnderline(True)
        formats[HighlighterState.Link] = charFormat

        # Set character format for images
        charFormat = QTextCharFormat()
        charFormat.setForeground(QColor(0, 191, 0))
        charFormat.setBackground(QColor(228, 255, 228))
        formats[HighlighterState.Image] = charFormat

        fixedFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        # Set character format for code blocks
        charFormat = QTextCharFormat()
        charFormat.setFont(fixedFont)
        formats[HighlighterState.CodeBlock] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setForeground(schema.InlineCode)
        formats[HighlighterState.InlineCodeBlock] = charFormat

        # Set character format for italic
        charFormat = QTextCharFormat()
        charFormat.setFontItalic(True)
        formats[HighlighterState.Italic] = charFormat

        # set character format for underline
        charFormat = QTextCharFormat()
        charFormat.setFontUnderline(True)
        formats[HighlighterState.StUnderline] = charFormat

        # Set character format for bold
        charFormat = QTextCharFormat()
        charFormat.setFontWeight(QFont.Bold)
        charFormat.setForeground(schema.Bold)
        formats[HighlighterState.Bold] = charFormat

        # Set character format for comments
        charFormat = QTextCharFormat()
        charFormat.setForeground(schema.Comment)
        formats[HighlighterState.Comment] = charFormat

        # Set character format for masked syntax
        charFormat = QTextCharFormat()
        charFormat.setForeground(QColor(204, 204, 204))
        formats[HighlighterState.MaskedSyntax] = charFormat

        # Set character format for tables
        charFormat = QTextCharFormat()
        charFormat.setFont(fixedFont)
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

        # set character format for trailing spaces
        charFormat = QTextCharFormat()
        formats[HighlighterState.TrailingSpace] = charFormat

        # Formats for syntax highlighting
        charFormat = QTextCharFormat()
        charFormat.setFont(fixedFont)
        charFormat.setForeground(schema.Keyword)
        formats[HighlighterState.CodeKeyWord] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(fixedFont)
        charFormat.setForeground(schema.String)
        formats[HighlighterState.CodeString] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(fixedFont)
        charFormat.setForeground(schema.Comment)
        formats[HighlighterState.CodeComment] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(fixedFont)
        charFormat.setForeground(schema.Type)
        formats[HighlighterState.CodeType] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(fixedFont)
        charFormat.setForeground(schema.Other)
        formats[HighlighterState.CodeOther] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(fixedFont)
        charFormat.setForeground(schema.Literal)
        formats[HighlighterState.CodeNumLiteral] = charFormat

        charFormat = QTextCharFormat()
        charFormat.setFont(fixedFont)
        charFormat.setForeground(schema.Builtin)
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
            "nix": HighlighterState.CodeNix,
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
            "svg": HighlighterState.CodeXML,
            "yml": HighlighterState.CodeYAML,
            "yaml": HighlighterState.CodeYAML,
            "forth": HighlighterState.CodeForth,
            "systemverilog": HighlighterState.CodeSystemVerilog,
            "gdscript": HighlighterState.CodeGDScript,
            "toml": HighlighterState.CodeTOML,
            "diff": HighlighterState.Diff,
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
                            text.lstrip().startswith("```") or
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

                    if self.isHeading(self.currentBlockState()):
                        pass
                    else:
                        self.setFormat(match.capturedStart(maskedGroup),
                                       match.capturedLength(maskedGroup), currentMaskedFormat)

                if self.isHeading(self.currentBlockState()):
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
        i = 0
        while i < 4 and i < len(text):
            if text[i] != ' ':
                break
            i += 1

        sText = text[i:]
        if not sText or i == 4 or text.startswith("\t"):
            return

        c = sText[0]
        if c != '-' and c != '_' and c != '*':
            return

        length = 0
        hasSameChars = True
        for sc in sText:
            if c != sc and sc != ' ':
                hasSameChars = False
                break
            if sc != " ":
                length += 1
        if length < 3:
            return

        if hasSameChars:
            self.setFormat(
                0, len(text), self._formats[HighlighterState.HorizontalRuler])

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

                # Set styling of the "#"s to "masked syntax", but with the size of
                # the heading
                maskedFormat = QTextCharFormat(self._formats[state])
                fontSize = self._formats[state].fontPointSize()
                if fontSize > 0:
                    maskedFormat.setFontPointSize(fontSize)
                self.setFormat(0, headingLevel, maskedFormat)

                # Set the styling of the rest of the heading
                self.setFormat(headingLevel + 1, len(text) - 1 - headingLevel,
                               self._formats[state])

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
        isPrevParagraph = isParagraph(prev)

        if text[spacesOffset] == '=' and prevSpaces < 4 and isPrevParagraph:
            pattern1 = prev and hasOnlyHeadChars(text, '=', spacesOffset)
            if pattern1:
                self.highlightSubHeadline(text, HighlighterState.H1)
                return
        elif text[spacesOffset] == '-' and prevSpaces < 4 and isPrevParagraph:
            pattern2 = prev and hasOnlyHeadChars(text, '-', spacesOffset)
            if pattern2:
                self.highlightSubHeadline(text, HighlighterState.H2)
                return

        nextBlockText = self.currentBlock().next().text()
        if not nextBlockText:
            return
        nextSpaces = getIndentation(nextBlockText)
        isCurrentParagraph = isParagraph(text)

        if nextSpaces >= len(nextBlockText):
            return

        if nextBlockText[nextSpaces] == '=' and nextSpaces < 4 and isCurrentParagraph:
            nextHasEqualChars = hasOnlyHeadChars(
                nextBlockText, '=', nextSpaces)
            if nextHasEqualChars:
                self.setFormat(
                    0, len(text), self._formats[HighlighterState.H1])
                self.setCurrentBlockState(HighlighterState.H1)
        elif nextBlockText[nextSpaces] == '-' and nextSpaces < 4 and isCurrentParagraph:
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

        prevTrimmed = self.currentBlock().previous().text().strip()
        # previous line must be empty according to CommonMark except if it is a
        # heading https://spec.commonmark.org/0.29/#indented-code-block
        if (prevTrimmed and self.previousBlockState() != HighlighterState.CodeBlockIndented and
                not self.isHeading(self.previousBlockState()) and self.previousBlockState() != HighlighterState.HeadlineEnd):
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

        # we check for both H1/H2 so that if the user changes his mind, and changes
        # === to ---, changes be reflected immediately
        if (self.previousBlockState() == HighlighterState.H1 or
            self.previousBlockState() == HighlighterState.H2 or
                self.previousBlockState() == HighlighterState.NoState):
            currentMaskedFormat = QTextCharFormat(maskedFormat)
            # set the font size from the current rule's font format
            currentMaskedFormat.setFontPointSize(
                self._formats[state].fontPointSize())

            self.setFormat(0, len(text), currentMaskedFormat)
            self.setCurrentBlockState(HighlighterState.HeadlineEnd)

            # we want to re-highlight the previous block
            # this must not be done directly, but with a queue, otherwise it
            # will crash
            # setting the character format of the previous text, because this
            # causes text to be formatted the same way when writing after
            # the text
            if self.previousBlockState() != state:
                self.addDirtyBlock(previousBlock)
                previousBlock.setUserState(state)

    def highlightCodeBlock(self, text: str, opener="```"):
        """ Highlight multi-line code blocks """

        trimmed = text.lstrip()
        if trimmed.startswith(opener):
            # if someone decides to put these on the same line
            # interpret it as inline code, not code block
            if text.endswith("```") and len(text) > 3:
                self.setFormat(3, len(text) - 3,
                               self._formats[HighlighterState.InlineCodeBlock])
                self.setFormat(
                    0, 3, self._formats[HighlighterState.NoState])
                self.setFormat(len(text) - 3, 3,
                               self._formats[HighlighterState.NoState])
                return

            if ((self.previousBlockState() != HighlighterState.CodeBlock and
                self.previousBlockState() != HighlighterState.CodeBlockTilde) and
                (self.previousBlockState() != HighlighterState.CodeBlockComment and
                self.previousBlockState() != HighlighterState.CodeBlockTildeComment) and
                    self.previousBlockState() < HighlighterState.CodeCpp):
                lang = trimmed[3:].lower()
                progLang = self._langStringToEnum.get(lang)

                if progLang and progLang >= HighlighterState.CodeCpp:
                    state = progLang if trimmed.startswith(
                        "```") else progLang + self.tildeOffset
                    self.setCurrentBlockState(state)
                else:
                    state = HighlighterState.CodeBlock if opener == "```" else HighlighterState.CodeBlockTilde
                    self.setCurrentBlockState(state)
            elif self.isCodeBlock(self.previousBlockState()):
                state = HighlighterState.CodeBlockEnd if opener == "```" else HighlighterState.CodeBlockTildeEnd
                self.setCurrentBlockState(state)

            # set the font size from the current rule's font format
            maskedFormat = QTextCharFormat(
                self._formats[HighlighterState.NoState])
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
        isForth = False
        isGDScript = False
        isSQL = False
        isTOML = False

        keywords = {}
        others = {}
        types = {}
        builtin = {}
        literals = {}

        # apply the default code block format first
        self.setFormat(0, textLen, self._formats[HighlighterState.CodeBlock])

        state = self.currentBlockState()
        if state in [HighlighterState.CodeCpp,
                     HighlighterState.CodeCpp + self.tildeOffset,
                     HighlighterState.CodeCppComment,
                     HighlighterState.CodeCppComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadCppData()
        elif state in [HighlighterState.CodeJs,
                       HighlighterState.CodeJs + self.tildeOffset,
                       HighlighterState.CodeJsComment,
                       HighlighterState.CodeJsComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadJSData()
        elif state in [HighlighterState.CodeC,
                       HighlighterState.CodeC + self.tildeOffset,
                       HighlighterState.CodeCComment,
                       HighlighterState.CodeBlockComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadCppData()
        elif state in [HighlighterState.CodeBash,
                       HighlighterState.CodeBash + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadShellData()
            comment = '#'
        elif state in [HighlighterState.CodePHP,
                       HighlighterState.CodePHP + self.tildeOffset,
                       HighlighterState.CodePHPComment,
                       HighlighterState.CodePHPComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadPHPData()
        elif state in [HighlighterState.CodeQML,
                       HighlighterState.CodeQML + self.tildeOffset,
                       HighlighterState.CodeQMLComment,
                       HighlighterState.CodeQMLComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadQMLData()
        elif state in [HighlighterState.CodePython,
                       HighlighterState.CodePython + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadPythonData()
            comment = '#'
        elif state in [HighlighterState.CodeRust,
                       HighlighterState.CodeRust + self.tildeOffset,
                       HighlighterState.CodeRustComment,
                       HighlighterState.CodeRustComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadRustData()
        elif state in [HighlighterState.CodeJava,
                       HighlighterState.CodeJava + self.tildeOffset,
                       HighlighterState.CodeJavaComment,
                       HighlighterState.CodeJavaComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadJavaData()
        elif state in [HighlighterState.CodeCSharp,
                       HighlighterState.CodeCSharp + self.tildeOffset,
                       HighlighterState.CodeCSharpComment,
                       HighlighterState.CodeCSharpComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadCSharpData()
        elif state in [HighlighterState.CodeGo,
                       HighlighterState.CodeGo + self.tildeOffset,
                       HighlighterState.CodeGoComment,
                       HighlighterState.CodeGoComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadGoData()
        elif state in [HighlighterState.CodeV,
                       HighlighterState.CodeV + self.tildeOffset,
                       HighlighterState.CodeVComment,
                       HighlighterState.CodeVComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadVData()
        elif state in [HighlighterState.CodeSQL,
                       HighlighterState.CodeSQL + self.tildeOffset,
                       HighlighterState.CodeSQLComment,
                       HighlighterState.CodeSQLComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadSQLData()
            isSQL = True
            comment = "-"  # prevent the default comment highlighting
        elif state in [HighlighterState.CodeJSON,
                       HighlighterState.CodeJSON + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadJSONData()
        elif state in [HighlighterState.CodeXML,
                       HighlighterState.CodeXML + self.tildeOffset]:
            self.xmlHighlighter(text)
            return
        elif state in [HighlighterState.CodeCSS,
                       HighlighterState.CodeCSS + self.tildeOffset,
                       HighlighterState.CodeCSSComment,
                       HighlighterState.CodeCSSComment + self.tildeOffset]:
            isCSS = True
            types, keywords, builtin, literals, others = loadCSSData()
        elif state in [HighlighterState.CodeTypeScript,
                       HighlighterState.CodeTypeScript + self.tildeOffset,
                       HighlighterState.CodeTypeScriptComment,
                       HighlighterState.CodeTypeScriptComment + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadTypeScriptData()
        elif state in [HighlighterState.CodeYAML,
                       HighlighterState.CodeYAML + self.tildeOffset]:
            isYAML = True
            comment = '#'
            types, keywords, builtin, literals, others = loadYAMLData()
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
            types, keywords, builtin, literals, others = loadVexData()
        elif state in [HighlighterState.CodeCMake,
                       HighlighterState.CodeCMake + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadCMakeData()
            comment = "#"
        elif state in [HighlighterState.CodeMake,
                       HighlighterState.CodeMake + self.tildeOffset]:
            isMake = True
            types, keywords, builtin, literals, others = loadMakeData()
            comment = "#"
        elif state in [HighlighterState.CodeNix,
                       HighlighterState.CodeNix + self.tildeOffset]:
            types, keywords, builtin, literals, others = loadNixData()
            comment = "#"
        elif state in [HighlighterState.CodeForth,
                       HighlighterState.CodeForth + self.tildeOffset,
                       HighlighterState.CodeForthComment,
                       HighlighterState.CodeForthComment + self.tildeOffset]:
            isForth = True
            types, keywords, builtin, literals, others = loadForthData()
        elif state in [HighlighterState.CodeSystemVerilog,
                       HighlighterState.CodeSystemVerilogComment]:
            types, keywords, builtin, literals, others = loadSystemVerilogData()
        elif state in [HighlighterState.CodeGDScript,
                       HighlighterState.CodeGDScript + self.tildeOffset]:
            isGDScript = True
            types, keywords, builtin, literals, others = loadGDScriptData()
            comment = "#"
        elif state in [HighlighterState.CodeTOML,
                       HighlighterState.CodeTOML + self.tildeOffset,
                       HighlighterState.CodeTOMLString,
                       HighlighterState.CodeTOMLString + self.tildeOffset]:
            isTOML = True
            types, keywords, builtin, literals, others = loadTOMLData()
            comment = "#"
        elif state in [HighlighterState.Diff,
                       HighlighterState.Diff + self.tildeOffset]:
            self.diffHighlighter(text)
            return
        else:
            self.setFormat(
                0, textLen, self._formats[HighlighterState.CodeBlock])
            return

        def applyCodeFormat(i, data: Dict[str, list], text: str, fmt):
            # check if we are at the beginning OR if this is the start of a word
            if i == 0 or (not text[i - 1].isalnum() and text[i - 1] != '_'):
                wordList = data.get(text[i], [])
                for word in wordList:
                    # we have a word match check
                    # 1. if we are at the end
                    # 2. if we have a complete word
                    if (text[i:i+len(word)] == word and
                        (i + len(word) == len(text) or
                         (not text[i + len(word)].isalnum() and text[i+len(word)] != '_'))):
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
                i += 1
                continue

            # Highlight Types
            i = applyCodeFormat(i, types, text, formatType)

            # next letter is usually a space, in that case
            # going forward is useless, so continue;
            if i == textLen or not text[i].isalpha():
                i += 1
                continue

            # Highlight Keywords
            i = applyCodeFormat(i, keywords, text, formatKeyword)
            if i == textLen or not text[i].isalpha():
                i += 1
                continue

            # Highlight Literals (true/false/NULL,nullptr)
            i = applyCodeFormat(i, literals, text, formatNumLit)
            if i == textLen or not text[i].isalpha():
                i += 1
                continue

            # Highlight Builtin library stuff
            i = applyCodeFormat(i, builtin, text, formatBuiltIn)
            if i == textLen or not text[i].isalpha():
                i += 1
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
                i = cnt - 1
            i += 1

        # POST PROCESSORS
        if isCSS:
            self.cssHighlighter(text)
        if isYAML:
            self.ymlHighlighter(text)
        if isMake:
            self.makeHighlighter(text)
        if isForth:
            self.forthHighlighter(text)
        if isGDScript:
            self.gdscriptHighlighter(text)
        if isSQL:
            self.sqlHighlighter(text)
        if isTOML:
            self.tomlHighlighter(text)

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
                        if not self.isOctal(text[i + 2]):
                            pass
                        elif not self.isOctal(text[i + 3]):
                            pass
                        else:
                            length = 4
                # hex numbers \xFA
                elif nextChar == 'x':
                    if i + 3 <= len(text):
                        if not self.isHex(text[i + 2]):
                            pass
                        elif not self.isHex(text[i + 3]):
                            pass
                        else:
                            length = 4
                # TODO: implement Unicode code point escaping

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

        return i - 1

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
            if isCurrentHex or text[i - 1] != 'e':
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
                    errorFormat = QTextCharFormat(
                        self._formats[HighlighterState.NoState])
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
                if text[i:i+4] == "http":
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

                    f = QTextCharFormat(
                        self._formats[HighlighterState.CodeBlock])
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
        # Skip any spaces in the beginning
        while spaces < len(text) and text[spaces].isspace():
            spaces += 1

        # return if we reached the end
        if spaces >= len(text):
            return

        # check for start of list
        front = text[spaces]
        if not isBeginningOfList(front):
            return

        curPos = spaces
        # Ordered List
        if text[spaces].isdigit():
            number = curPos
            # move forward till first non-number char
            while number < len(text) and text[number].isdigit():
                number += 1

            count = number - curPos
            # reached end?
            if number + 1 >= len(text) or count > 9:
                return
            # there should be a '.' or ')' after a number
            if ((text[number] == '.' or text[number] == ')') and
                    text[number + 1] == ' '):
                self.setCurrentBlockState(HighlighterState.List)
                self.setFormat(curPos, number - curPos + 1,
                               self._formats[HighlighterState.List])
                # highlight checkbox if any
                self.highlightCheckbox(text, number)
            return

        # if its just a '-' etc, no highlighting
        if curPos + 1 >= len(text):
            return
        # check for a space after it
        if text[curPos + 1] != ' ':
            return

        # check if we are in checkbox list
        self.highlightCheckbox(text, curPos)

        # Unordered List
        self.setCurrentBlockState(HighlighterState.List)
        self.setFormat(curPos, 1, self._formats[HighlighterState.List])

    def highlightInlineRules(self, text: str):
        """
        Highlight inline rules aka Emphasis, bolds, inline code spans,
        underlines, strikethrough, links, and images.
        """
        # clear existing span ranges for this block
        it = self._ranges.get(self.currentBlock().blockNumber(), [])
        it.clear()

        i = 0
        while i < len(text):
            currentChar = text[i]
            if currentChar == '`' or currentChar == '~':
                i = self.highlightInlineSpans(text, i, currentChar)
            elif currentChar == '<' and i + 4 < len(text) and text[i:i + 4] == "<!--":
                i = self.highlightInlineComment(text, i)
            else:
                i = self.highlightLinkOrImage(text, i)
            i += 1
        self.highlightEmAndStrong(text, 0)

    def highlightInlineSpans(self, text: str, currentPos: int, c: str):
        """ highlight inline code spans -> `code` and highlight strikethroughs """
        # clear code span ranges for this block
        i = currentPos
        # found a backtick
        length = 0
        pos = i

        if i != 0 and text[i - 1] == '\\':
            return currentPos

        # keep moving forward in backtick sequence;
        while pos < len(text) and text[pos] == c:
            length += 1
            pos += 1

        seq = text[i:i+length]
        start = i
        i += length
        next = text.find(seq, i)
        if next == -1:
            return currentPos

        if next + length < len(text) and text[next + length] == c:
            return currentPos

        # get existing format if any
        # we want to append to the existing format, not overwrite it
        fmt = self.format(start + 1)
        inlineFmt = QTextCharFormat()

        # select appropriate format for current text
        if c != '~':
            inlineFmt = QTextCharFormat(
                self._formats[HighlighterState.InlineCodeBlock])

        # make sure we don't change font size / existing formatting
        if fmt.fontPointSize() > 0:
            inlineFmt.setFontPointSize(fmt.fontPointSize())

        if c == '~':
            inlineFmt.setFontStrikeOut(True)
            # we don't want these properties for "inline code span"
            inlineFmt.setFontItalic(fmt.fontItalic())
            inlineFmt.setFontWeight(fmt.fontWeight())
            inlineFmt.setFontUnderline(fmt.fontUnderline())
            inlineFmt.setUnderlineStyle(fmt.underlineStyle())

        if c == '`':
            self._ranges.setdefault(self.currentBlock().blockNumber(), []).append(
                InlineRange(start, next, RangeType.CodeSpan))

        # format the text
        self.setFormat(start + length, next - (start + length), inlineFmt)

        # format backticks as masked
        self.setFormat(start, length, inlineFmt)
        self.setFormat(next, length, inlineFmt)

        i = next + length
        return i

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
            isIncodeSpan = self.isPosInACodeSpan(
                self.currentBlock().blockNumber(), i)
            if isIncodeSpan:
                i += 1
                continue
            i = collectEmDelims(text, i, delims)

        # 2. Balance pairs
        balancePairs(delims)

        # start,length -> helper for applying masking later
        masked: List[tuple[int, int]] = []

        # 3. final processing & highlighting
        i = len(delims) - 1
        while i >= 0:
            startDelim = delims[i]
            if startDelim.marker != "_" and startDelim.marker != "*":
                i -= 1
                continue
            if startDelim.end == -1:
                i -= 1
                continue

            endDelim = delims[startDelim.end]
            state: HighlighterState = self.currentBlockState()

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
                    fontFamilies = self._formats[HighlighterState.Bold].fontFamilies(
                    )
                    if fontFamilies:
                        fmt.setFontFamilies(fontFamilies)
                    if self._formats[state].fontPointSize() > 0:
                        fmt.setFontPointSize(
                            self._formats[state].fontPointSize())

                    # if we are in plain text, use the format's specified color
                    if fmt.foreground() == QTextCharFormat().foreground():
                        fmt.setForeground(
                            self._formats[HighlighterState.Bold].foreground())
                    if underline:
                        fmt.setForeground(
                            self._formats[HighlighterState.StUnderline].foreground())
                        fmt.setFont(
                            self._formats[HighlighterState.StUnderline].font())
                        fmt.setFontUnderline(
                            self._formats[HighlighterState.StUnderline].fontUnderline())
                    elif self._formats[HighlighterState.Bold].font().bold():
                        fmt.setFontWeight(QFont.Bold)
                    self.setFormat(k, 1, fmt)
                    k += 1

                masked.append((startDelim.pos - 1, 2))
                masked.append((endDelim.pos, 2))

                block = self.currentBlock().blockNumber()
                self._ranges.setdefault(block, []).append(InlineRange(
                    startDelim.pos, endDelim.pos + 1, RangeType.Emphasis))
                self._ranges[block].append(InlineRange(
                    startDelim.pos - 1, endDelim.pos, RangeType.Emphasis))
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
                    fontFamilies = self._formats[HighlighterState.Italic].fontFamilies(
                    )
                    if fontFamilies:
                        fmt.setFontFamilies(fontFamilies)
                    if self._formats[state].fontPointSize() > 0:
                        fmt.setFontPointSize(
                            self._formats[state].fontPointSize())
                    if fmt.foreground() == QTextCharFormat().foreground():
                        fmt.setForeground(
                            self._formats[HighlighterState.Italic].foreground())
                    if underline:
                        fmt.setFontUnderline(
                            self._formats[HighlighterState.StUnderline].fontUnderline())
                    else:
                        fmt.setFontItalic(
                            self._formats[HighlighterState.Italic].fontItalic())
                    self.setFormat(k, 1, fmt)
                    k += 1
                masked.append((startDelim.pos, 1))
                masked.append((endDelim.pos, 1))

                block = self.currentBlock().blockNumber()
                self._ranges.setdefault(block, []).append(InlineRange(
                    startDelim.pos, endDelim.pos, RangeType.Emphasis))
            i -= 1

        # 4. Apply masked syntax
        for i in range(len(masked)):
            state = HighlighterState.Bold if isStrong else HighlighterState.Italic
            maskedFmt = QTextCharFormat(self._formats[state])
            state: HighlighterState = self.currentBlockState()
            if self._formats[state].fontPointSize() > 0:
                maskedFmt.setFontPointSize(
                    self._formats[state].fontPointSize())
            self.setFormat(masked[i][0], masked[i][1], maskedFmt)

    def forthHighlighter(self, text: str):
        """ The Forth highlighter """
        if not text:
            return

        textLen = len(text)

        # Default Format
        self.setFormat(0, textLen, self._formats[HighlighterState.CodeBlock])

        for i in range(textLen):
            # 1, It highlights the "\ " comments
            if i + 1 <= textLen and text[i] == '\\' and \
                    text[i + 1] == ' ':
                # The full line is commented
                self.setFormat(i + 1, textLen - 1,
                               self._formats[HighlighterState.CodeComment])
                break

            # 2. It highlights the "( " comments
            elif i + 1 <= textLen and text[i] == '(' and \
                    text[i + 1] == ' ':
                # Find the End bracket
                lastBracket = text.rfind(')', i)
                # Can't Handle wrong Format
                if lastBracket <= 0:
                    return
                # ' )' at the end of the comment
                if lastBracket <= textLen and \
                        text[lastBracket] == ' ':
                    self.setFormat(
                        i, lastBracket, self._formats[HighlighterState.CodeComment])

    def gdscriptHighlighter(self, text: str):
        """ The GDScript highlighter """
        if not text:
            return

        # 1. Hightlight '$' NodePath constructs.
        # 2. Highlight '%' UniqueNode constructs.
        re = QRegularExpression(
            r"([$%][a-zA-Z_][a-zA-Z0-9_]*(/[a-zA-Z_][a-zA-Z0-9_]*)*|@)")
        i = re.globalMatch(text)
        while i.hasNext():
            match = i.next()
            # 3. Hightlight '@' annotation symbol
            if match.captured().startswith('@'):
                self.setFormat(match.capturedStart(), match.capturedLength(),
                               self._formats[HighlighterState.CodeOther])
            else:
                self.setFormat(match.capturedStart(), match.capturedLength(),
                               self._formats[HighlighterState.CodeNumLiteral])

    def sqlHighlighter(self, text: str):
        """ The SQL highlighter """
        if not text:
            return
        textLen = len(text)

        for i in range(textLen):
            if i + 1 > textLen:
                break

            # Check for comments: single-line, or multi-line start or end
            if text[i] == '-' and text[i + 1] == '-':
                self.setFormat(
                    i, textLen, self._formats[HighlighterState.CodeComment])
            elif text[i] == '/' and text[i + 1] == '*':
                # we're in a multi-line comment now
                if self.currentBlockState() % 2 == 0:
                    self.setCurrentBlockState(self.currentBlockState() + 1)
                    # Did the multi-line comment end in the same line?
                    endingComment = text.find("*/", i + 2)
                    highlightEnd = textLen
                    if endingComment > -1:
                        highlightEnd = endingComment + 2

                    self.setFormat(i, highlightEnd - i,
                                   self._formats[HighlighterState.CodeComment])
            elif text[i] == '*' and text[i + 1] == '/':
                # we're now no longer in a multi-line comment
                if self.currentBlockState() % 2 != 0:
                    self.setCurrentBlockState(self.currentBlockState() - 1)
                    # Did the multi-line comment start in the same line?
                    startingComment = text.find("/*", 0)
                    highlightStart = 0
                    if startingComment > -1:
                        highlightStart = startingComment

                    self.setFormat(highlightStart - i, i + 1,
                                   self._formats[HighlighterState.CodeComment])

    def tomlHighlighter(self, text: str):
        """ The TOML highlighter"""
        if not text:
            return

        textLen = len(text)

        onlyWhitespaceBeforeHeader = True
        possibleAssignmentPos = text.find('=', 0)
        singleQStringStart = -1
        doubleQStringStart = -1
        multiSingleQStringStart = -1
        multiDoubleQStringStart = -1
        singleQ = "'"
        doubleQ = '"'

        i = 0
        while i < textLen:
            if i + 1 > textLen:
                break

            # track the state of strings
            # multiline highlighting doesn't quite behave due to clashing handling
            # of " and ' chars, but this accomodates normal " and ' strings, as
            # well as ones wrapped by either """ or '''
            if text[i] == doubleQ:
                if i + 2 <= textLen and text[i + 1] == doubleQ and \
                        text[i + 2] == doubleQ:
                    if multiDoubleQStringStart > -1:
                        multiDoubleQStringStart = -1
                    else:
                        multiDoubleQStringStart = i
                        multiDoubleQStringEnd = text.find('"""', i + 1)
                        if multiDoubleQStringEnd > -1:
                            self.setFormat(i, multiDoubleQStringEnd - i,
                                           self._formats[HighlighterState.CodeString])
                            i = multiDoubleQStringEnd + 2
                            multiDoubleQStringEnd = -1
                            multiDoubleQStringStart = -1
                            i += 1
                            continue
                else:
                    if doubleQStringStart > -1:
                        doubleQStringStart = -1
                    else:
                        doubleQStringStart = i
            elif text[i] == singleQ:
                if i + 2 <= textLen and text[i + 1] == singleQ and \
                        text[i + 2] == singleQ:
                    if multiSingleQStringStart > -1:
                        multiSingleQStringStart = -1
                    else:
                        multiSingleQStringStart = i
                        multiSingleQStringEnd = text.find("'''", i + 1)
                        if multiSingleQStringEnd > -1:
                            self.setFormat(i, multiSingleQStringEnd - i,
                                           self._formats[HighlighterState.CodeString])
                            i = multiSingleQStringEnd + 2
                            multiSingleQStringEnd = -1
                            multiSingleQStringStart = -1
                            i += 1
                            continue
                else:
                    if singleQStringStart > -1:
                        singleQStringStart = -1
                    else:
                        singleQStringStart = i

            inString = doubleQStringStart > -1 or singleQStringStart > -1 or \
                multiSingleQStringStart > -1 or \
                multiDoubleQStringStart > -1

            # do comment highlighting
            if text[i] == '#' and not inString:
                self.setFormat(
                    i, textLen - i, self._formats[HighlighterState.CodeComment])
                return

            # table header (all stuff preceeding must only be whitespace)
            if text[i] == '[' and onlyWhitespaceBeforeHeader:
                headerEnd = text.find(']', i)
                if headerEnd > -1:
                    self.setFormat(i, headerEnd + 1 - i,
                                   self._formats[HighlighterState.CodeType])
                    return

            # handle numbers, inf, nan and datetime the same way
            if i > possibleAssignmentPos and not inString and \
                (text[i].isdigit() or text.find("inf", i) > 0 or
                 text.find("nan", i) > 0):
                nextWhitespace = text.find(' ', i)
                endOfNumber = textLen
                if nextWhitespace > -1:
                    if (text[nextWhitespace - 1] == ','):
                        nextWhitespace -= 1
                    endOfNumber = nextWhitespace

                highlightStart = i
                if i > 0:
                    if text[i - 1] == '-' or \
                            text[i - 1] == '+':
                        highlightStart -= 1
                self.setFormat(highlightStart, endOfNumber - highlightStart,
                               self._formats[HighlighterState.CodeNumLiteral])
                i = endOfNumber

            if not text[i].isspace():
                onlyWhitespaceBeforeHeader = False
        i += 1

    def highlightCheckbox(self, text: str, curPos: int):
        if curPos + 4 >= len(text):
            return

        hasOpeningBracket = text[curPos + 2] == '['
        hasClosingBracket = text[curPos + 4] == ']'
        midChar = text[curPos + 3]
        hasXorSpace = midChar == ' ' or \
            midChar == 'x' or \
            midChar == 'X'
        hasDash = midChar == '-'

        if hasOpeningBracket and hasClosingBracket and (hasXorSpace or hasDash):
            start = curPos + 2
            length = 3

            if hasXorSpace:
                if midChar == ' ':
                    fmt = HighlighterState.CheckBoxUnChecked
                else:
                    fmt = HighlighterState.CheckBoxChecked
            else:
                fmt = HighlighterState.MaskedSyntax
            self.setFormat(start, length, self._formats[fmt])

    def formatAndMaskRemaining(self, formatBegin, formatLength, beginningText, endText, format: QTextCharFormat):
        afterFormat = formatBegin + formatLength

        maskedSyntax = QTextCharFormat(
            self._formats[HighlighterState.MaskedSyntax])
        maskedSyntax.setFontPointSize(
            self.format(beginningText).fontPointSize())

        # highlight before the link
        self.setFormat(beginningText, formatBegin -
                       beginningText, maskedSyntax)

        # highlight the link if we are not in a heading
        if not self.isHeading(self.currentBlockState()):
            self.setFormat(formatBegin, formatLength, format)

        # highlight after the link
        maskedSyntax.setFontPointSize(
            self.format(afterFormat).fontPointSize())
        self.setFormat(afterFormat, endText - afterFormat, maskedSyntax)

        self._ranges.setdefault(self.currentBlock().blockNumber(), []).append(
            InlineRange(beginningText, formatBegin, RangeType.Link))
        self._ranges[self.currentBlock().blockNumber()].append(
            InlineRange(afterFormat, endText, RangeType.Link))

    def highlightLinkOrImage(self, text: str, startIndex: int):
        """ This function highlights images and links in Markdown text. """
        # If the first 4 characters are spaces (for 4-spaces fence code),
        # but not list markers, return
        if not text[:4].strip():
            # Check for unordered list markers
            leftChars = text.strip()[:2]

            if leftChars not in ["- ", "+ ", "* "]:
                # Check for a few ordered list markers
                leftChars = text.strip()[:3]

                markers = [
                    f"{i}{sep} " for i in range(1, 10) for sep in [")", "."]
                ]
                if leftChars not in markers:
                    # Check if text starts with a "\d+. ", "\d+) "
                    patterns = ["\\d+\\. ", "\\d+\\) "]
                    pattern_string = "^(" + "|".join(patterns) + ")"
                    pattern = QRegularExpression(pattern_string)

                    match = pattern.match(text.strip())
                    if not match.hasMatch():
                        return startIndex

        # Get the character at the starting index
        startChar = text[startIndex]

        # If it starts with '<', it indicates a link or email enclosed in angle brackets
        if startChar == '<':
            closingChar = text.find('>', startIndex)
            if closingChar == -1:
                return startIndex

            # Extract the content between '<' and '>'
            linkContent = text[startIndex + 1:closingChar]

            # Check if it's a valid link or email
            if not isLink(linkContent) and not isValidEmail(linkContent) and '.' not in linkContent:
                return startIndex

            # Apply formatting to highlight the link
            self.formatAndMaskRemaining(
                startIndex + 1, closingChar - startIndex - 1,
                startIndex, closingChar + 1, self._formats[HighlighterState.Link])

            return closingChar

        # Highlight http and www links
        elif startChar != '[':
            space = text.find(' ', startIndex)
            if space == -1:
                space = len(text)

            # Allow highlighting href in HTML tags
            if text[startIndex:startIndex+6] == 'href="':
                hrefEnd = text.find('"', startIndex + 6)
                if hrefEnd == -1:
                    return space

                blockNum = self.currentBlock().blockNumber()
                self._ranges.setdefault(blockNum, []).append(
                    InlineRange(startIndex + 6, hrefEnd, RangeType.Link))

                self.setFormat(startIndex + 6, hrefEnd - startIndex -
                               6, self._formats[HighlighterState.Link])
                return hrefEnd

            link = text[startIndex:space-1]
            if not isLink(link):
                return startIndex

            linkLength = len(link)

            blockNum = self.currentBlock().blockNumber()
            self._ranges.setdefault(blockNum, []).append(
                InlineRange(startIndex, startIndex + linkLength, RangeType.Link))

            self.setFormat(startIndex, linkLength + 1,
                           self._formats[HighlighterState.Link])
            return space

        # Find the index of the closing ']' character
        endIndex = text.find(']', startIndex)

        # If end_index is not found or at the end of the text, the link is invalid
        if endIndex == -1 or endIndex == len(text) - 1:
            return startIndex

        # If there is an '!' preceding the starting character, it's an image
        if startIndex != 0 and text[startIndex - 1] == '!':
            # Find the closing ')' character after the image link
            closingIndex = text.find(')', endIndex)
            if closingIndex == -1:
                return startIndex
            closingIndex += 1

            # Apply formatting to highlight the image
            self.formatAndMaskRemaining(
                startIndex + 1, endIndex - startIndex - 1,
                startIndex - 1, closingIndex, self._formats[HighlighterState.Image])
            return closingIndex

        # If the character after the closing ']' is '(', it's a regular link
        elif text[endIndex + 1] == '(':
            # Find the closing ')' character after the link
            closingParenIndex = text.find(')', endIndex)
            if closingParenIndex == -1:
                return startIndex
            closingParenIndex += 1

            # Check for image with link
            if text[startIndex:startIndex+3] == '[![':
                # Find the end of the image alt text
                altEndIndex = text.find(']', endIndex + 1)
                if altEndIndex == -1:
                    return startIndex

                # Find the last ')'
                hrefIndex = text.find(')', altEndIndex)
                if hrefIndex == -1:
                    return startIndex
                hrefIndex += 1

                self.formatAndMaskRemaining(
                    startIndex + 3, endIndex - startIndex - 3,
                    startIndex, hrefIndex, self._formats[HighlighterState.Link])
                return hrefIndex

            # Apply formatting to highlight the link
            self.formatAndMaskRemaining(
                startIndex + 1, endIndex - startIndex - 1,
                startIndex, closingParenIndex, self._formats[HighlighterState.Link])
            return closingParenIndex

        # Reference links
        elif text[endIndex + 1] == '[':
            # Image with reference
            origIndex = startIndex
            if text[startIndex + 1] == '!':
                startIndex = text.find('[', startIndex + 1)
                if startIndex == -1:
                    return origIndex

            closingChar = text.find(']', endIndex + 1)
            if closingChar == -1:
                return startIndex
            closingChar += 1

            self.formatAndMaskRemaining(
                startIndex + 1, endIndex - startIndex - 1,
                origIndex, closingChar, self._formats[HighlighterState.Link])
            return closingChar

        # If the character after the closing ']' is ':', it's a reference link reference
        elif text[endIndex + 1] == ':':
            self.formatAndMaskRemaining(
                0, 0, startIndex, endIndex + 1, QTextCharFormat())
            return endIndex + 1

        # If none of the conditions are met, continue processing from the same index
        return startIndex

    def isPosInACodeSpan(self, blockNumber: int, position: int):
        rangeList: List[InlineRange] = self._ranges.get(blockNumber, [])

        for rg in rangeList:
            if (position > rg.begin and
                position < rg.end and
                    rg.type == RangeType.CodeSpan):
                return True

        return False

    def diffHighlighter(self, text: str):
        if not text:
            return

        tcFormat = QTextCharFormat()
        tcFormat.setFont(self._formats[HighlighterState.CodeBlock].font())

        if text.startswith("+++ ") or text.startswith("--- "):
            tcFormat.setFontWeight(QFont.Bold)
        elif text[0] == "+":
            if len(text) >= 2 and text[1] == "+":
                tcFormat.setFontWeight(QFont.Bold)
            else:
                tcFormat.setForeground(
                    ApplicationBase.instance().colorSchema().Adding)
        elif text[0] == "-":
            tcFormat.setForeground(
                ApplicationBase.instance().colorSchema().Deletion)
        elif text[0] == " " and len(text) >= 2:
            if text.startswith("  > "):
                tcFormat.setForeground(
                    ApplicationBase.instance().colorSchema().Submodule)
            elif text.startswith("  < "):
                tcFormat.setForeground(
                    ApplicationBase.instance().colorSchema().Submodule2)
        elif diff_begin_re.search(text) or text.startswith(r"\ No newline "):
            tcFormat.setForeground(
                ApplicationBase.instance().colorSchema().Newline)

        self.setFormat(0, len(text), tcFormat)
