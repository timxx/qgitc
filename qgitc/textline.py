# -*- coding: utf-8 -*-

import bisect
import re
from typing import List, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QPalette,
    QTextCharFormat,
    QTextLayout,
    QTextOption,
)

from qgitc.applicationbase import ApplicationBase
from qgitc.common import logger

__all__ = ["createFormatRange", "Link", "TextLine",
           "SourceTextLineBase", "LinkTextLine"]


sha1_re = re.compile("(?<![a-zA-Z0-9_])[a-f0-9]{7,40}(?![a-zA-Z0-9_])")
email_re = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
url_re = re.compile("((https?|ftp)://[a-zA-Z0-9@:%_+-.~#?&/=()]+)")

cr_char = "^M"


def createFormatRange(start, length, fmt):
    formatRange = QTextLayout.FormatRange()
    formatRange.start = start
    formatRange.length = length
    formatRange.format = fmt

    return formatRange


class Link():
    Sha1 = 0
    BugId = 1
    Email = 2
    Url = 3

    def __init__(self, start, end, linkType):
        self.start = start
        self.end = end
        self.type = linkType
        self.data = None

    def setData(self, data):
        self.data = data

    def hitTest(self, pos):
        return self.start <= pos and pos <= self.end


class TextLine():

    def __init__(self, text: str, font: QFont, option: QTextOption = None):
        self._text = text
        self._layout = None
        self._links = []
        self._lineNo = 0
        self._patterns = None
        self._rehighlight = True
        self._invalidated = True
        self._font = font

        self._defOption = option
        self._useBuiltinPatterns = True

        if not self._defOption:
            self._defOption = QTextOption()
        self._defOption.setWrapMode(QTextOption.NoWrap)

        self._utf16Len = None
        self._indices = None

    def _relayout(self):
        self._layout.beginLayout()
        self._layout.createLine()
        self._layout.endLayout()

    def _findLinks(self, patterns):
        links = TextLine.findLinks(
            self._text,
            patterns)
        if links:
            self._links.extend(links)

    @staticmethod
    def findLinks(text: str, patterns: List[Tuple[int, re.Pattern, str]]):
        links: List[Link] = []
        if not text or not patterns:
            return links

        for linkType, pattern, url, in patterns:
            matches = pattern.finditer(text)
            for m in matches:
                shouldAdd = True
                for i in reversed(range(len(links))):
                    start = links[i].start
                    end = links[i].end

                    # prefer the first one if the range is the same
                    if m.start() == start and m.end() == end:
                        shouldAdd = False
                        break

                    # the new one is longer than the old one
                    if m.start() <= start and end <= m.end():
                        del links[i]
                        continue

                    # the old one is longer than the new one or overlap
                    if (start <= m.start() and m.end() <= end) or \
                        (start < m.end() and m.start() < end) or \
                            (m.start() < end and start < m.end()):
                        shouldAdd = False
                        break

                if not shouldAdd:
                    continue

                link = Link(m.start(), m.end(), linkType)
                if url:
                    if pattern.groups == 1:
                        link.setData(url + m.group(1))
                    else:
                        link.setData(url + m.group(2))
                elif pattern.groups == 0 or m.lastindex is None:
                    link.setData(m.group(0))
                else:
                    link.setData(m.group(m.lastindex))

                links.append(link)

        return links

    @staticmethod
    def builtinPatterns():
        patterns = {Link.Email: email_re,
                    Link.Url: url_re,
                    Link.Sha1: sha1_re}
        return patterns

    def createLinksFormats(self):
        if not self._links:
            return None

        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        fmt.setForeground(
            ApplicationBase.instance().palette().color(QPalette.Link))

        formats = []
        for link in self._links:
            start = self.mapToUtf16(link.start)
            end = self.mapToUtf16(link.end)
            rg = createFormatRange(start, end - start, fmt)
            formats.append(rg)

        return formats

    def text(self):
        return self._text

    def utf16Length(self):
        """ For createFormatRange """
        if self._utf16Len is None:
            self._utf16Len = len(self._text.encode('utf-16-le')) // 2

        return self._utf16Len

    def _buildIndices(self):
        if self.utf16Length() == len(self._text) or self._indices:
            return

        self._indices = [0]
        for c in self._text:
            if ord(c) > 0xFFFF:
                self._indices.append(self._indices[-1] + 2)
            else:
                self._indices.append(self._indices[-1] + 1)

    def mapToUtf16(self, index: int):
        """ Map the python str index to utf16 index """
        if index == 0:
            return 0

        self._buildIndices()
        if not self._indices:
            return index

        if index >= len(self._indices):
            logger.warning("index out of range %s > %s", index, len(self._indices))
            return self._indices[-1]

        return self._indices[index]

    def mapFromUtf16(self, index: int):
        """ Map the utf16 index to python str index """
        if index == 0:
            return 0

        self._buildIndices()
        if not self._indices:
            return index

        i = bisect.bisect_right(self._indices, index)
        return i - 1

    def layout(self):
        self.ensureLayout()
        return self._layout

    def defOption(self):
        return self._defOption

    def setDefOption(self, option):
        showWhitespace = option.flags() & QTextOption.ShowTabsAndSpaces
        oldShowWhitespace = self._defOption.flags() & QTextOption.ShowTabsAndSpaces if \
            self._defOption else False

        self._rehighlight = showWhitespace != oldShowWhitespace
        self._defOption = option

        if self._layout:
            self._layout.setTextOption(option)
            if self._rehighlight:
                self.rehighlight()
                self._rehighlight = False

    def setFont(self, font):
        self._font = font
        if self._layout:
            self._layout.setFont(self._font)
            self._invalidated = True

    def lineNo(self):
        return self._lineNo

    def setLineNo(self, n):
        self._lineNo = n

    def ensureLayout(self):
        if not self._layout:
            self._layout = QTextLayout(self._text, self._font)
            if self._defOption:
                self._layout.setTextOption(self._defOption)

            builtinPatterns = TextLine.builtinPatterns() if \
                self._useBuiltinPatterns else {}
            patterns = self._patterns or []
            for type, pattern in builtinPatterns.items():
                patterns.append((type, pattern, None))
            self._findLinks(patterns)

        if self._rehighlight:
            self.rehighlight()
            self._rehighlight = False
            # need relayout
            self._invalidated = True

        if self._invalidated:
            self._relayout()
            self._invalidated = False

    def boundingRect(self):
        self.ensureLayout()
        return self._layout.boundingRect()

    def offsetForPos(self, pos):
        if not self._text:
            return 0
        self.ensureLayout()
        line = self._layout.lineAt(0)
        offset = line.xToCursor(pos.x())
        return self.mapFromUtf16(offset)

    def offsetToX(self, offset):
        self.ensureLayout()
        line = self._layout.lineAt(0)
        offset = self.mapToUtf16(offset)
        x, _ = line.cursorToX(offset)
        return x

    def draw(self, painter, pos, selections=[], clip=QRectF()):
        self.ensureLayout()
        self._layout.draw(painter, pos, selections, clip)

    def rehighlight(self):
        if not self._text:
            return
        formats = self.createLinksFormats()
        if formats:
            self._layout.setFormats(formats)

    def setCustomLinkPatterns(self, patterns):
        self._links.clear()
        self._patterns = list(patterns)

        if self._layout:
            if patterns:
                patterns = list(patterns)
                for type, pattern in self.builtinPatterns().items():
                    patterns.append((type, pattern, None))
                self._findLinks(patterns)
            self.rehighlight()
        else:
            self._rehighlight = True

    def hitTest(self, pos):
        for link in self._links:
            if link.hitTest(pos):
                return link
        return None

    def hasCR(self):
        return False

    @property
    def useBuiltinPatterns(self):
        return self._useBuiltinPatterns

    @useBuiltinPatterns.setter
    def useBuiltinPatterns(self, value):
        self._useBuiltinPatterns = value

    def reapplyColorTheme(self):
        # no need to rehighlight
        if not self._layout or self._invalidated:
            return

        self.rehighlight()
        self._relayout()


class SourceTextLineBase(TextLine):

    def __init__(self, text, font, option):
        self._hasCR = text.endswith('\r')
        if self._hasCR:
            text = text[:-1]
        super().__init__(text, font, option)

        self._crWidth = 0
        self._updateCRWidth()

    def hasCR(self):
        return self._hasCR

    def setDefOption(self, option):
        super().setDefOption(option)
        self._updateCRWidth()

    def setFont(self, font):
        super().setFont(font)
        self._updateCRWidth()

    def boundingRect(self):
        br = super().boundingRect()
        br.setWidth(br.width() + self._crWidth)

        return br

    def draw(self, painter, pos, selections=None, clip=QRectF()):
        super().draw(painter, pos, selections, clip)

        if self._hasCR and self._showWhitespaces():
            br = super().boundingRect()
            rect = self.boundingRect()
            rect.setTopLeft(br.topRight())
            rect.moveTo(rect.topLeft() + pos)

            painter.save()
            painter.setFont(self._font)
            painter.setPen(ApplicationBase.instance().colorSchema().Whitespace)
            painter.drawText(rect, Qt.AlignCenter | Qt.AlignVCenter, cr_char)
            painter.restore()

    def _applyWhitespaces(self, text: str, formats: List[QTextLayout.FormatRange]):
        tcFormat = QTextCharFormat()
        tcFormat.setForeground(
            ApplicationBase.instance().colorSchema().Whitespace)

        offset = 0
        i = 0
        length = len(text)
        while i < length:
            c = text[i]
            if c.isspace():
                start = offset
                offset += 1
                i += 1
                while i < length and text[i].isspace():
                    offset += 1
                    i += 1
                rg = createFormatRange(start, offset - start, tcFormat)
                formats.append(rg)
            else:
                if ord(c) > 0xFFFF:
                    offset += 2
                else:
                    offset += 1
                i += 1

    def _showWhitespaces(self):
        flags = self._defOption.flags()
        return flags & QTextOption.ShowTabsAndSpaces

    def _updateCRWidth(self):
        if self._hasCR and self._showWhitespaces():
            fm = QFontMetrics(self._font)
            self._crWidth = fm.horizontalAdvance(cr_char)
        else:
            self._crWidth = 0

    def _commonHighlightFormats(self):
        formats = []

        if self._defOption:
            if self._defOption.flags() & QTextOption.ShowTabsAndSpaces:
                self._applyWhitespaces(self.text(), formats)

        linkFmt = self.createLinksFormats()
        if linkFmt:
            formats.extend(linkFmt)

        return formats


class LinkTextLine(TextLine):

    def __init__(self, text, font, linkType):
        super().__init__(text, font)
        self.useBuiltinPatterns = False
        patterns = TextLine.builtinPatterns()
        self.setCustomLinkPatterns(
            [(linkType, patterns[linkType], None)])
