# -*- coding: utf-8 -*-

from PySide2.QtGui import (
    QTextCharFormat,
    QTextLayout,
    QTextOption)
from PySide2.QtCore import QRectF

from .colorschema import ColorSchema

import bisect
import re


__all__ = ["createFormatRange", "Link", "TextLine"]


sha1_re = re.compile("(?<![a-zA-Z0-9_])[a-f0-9]{7,40}(?![a-zA-Z0-9_])")
email_re = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
url_re = re.compile("((https?|ftp)://[a-zA-Z0-9@:%_+-.~#?&/=()]+)")


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

    def __init__(self, start, end, linkType, lineType):
        self.start = start
        self.end = end
        self.type = linkType
        self.data = None
        self.lineType = lineType

    def setData(self, data):
        self.data = data

    def hitTest(self, pos):
        return self.start <= pos and pos <= self.end


class TextLine():

    Author = 0
    Parent = 1
    Child = 2
    Branch = 3
    Comments = 4
    File = 5
    FileInfo = 6
    Diff = 7

    def __init__(self, viewer, type, text):
        self._viewer = viewer
        self._type = type
        self._text = text
        self._layout = None
        self._links = []
        self._lineNo = 0
        self._patterns = None
        self._rehighlight = True
        self._invalidated = True
        self._font = viewer.defFont

        self._defOption = viewer.diffOption \
            if type == TextLine.Diff \
            else viewer.defOption

    def __relayout(self):
        self._layout.beginLayout()
        line = self._layout.createLine()
        self._layout.endLayout()

    def __findLinks(self, patterns):
        if self.isInfoType():
            return

        foundLinks = []
        for linkType, pattern in patterns.items():
            # only find email if item is author
            if linkType != Link.Email and \
                    self._type == TextLine.Author:
                continue

            matches = pattern.finditer(self._text)
            for m in matches:
                found = False
                i = bisect.bisect_left(foundLinks, (m.start(), m.end()))
                for x in range(i, len(foundLinks)):
                    start, end = foundLinks[x]
                    if (start <= m.start() and m.start() <= end) \
                            or (start <= m.end() and m.end() <= end):
                        found = True
                        break
                # not allow links in the same range
                if found:
                    continue

                link = Link(m.start(), m.end(), linkType, self._type)
                link.setData(m.group(0 if pattern.groups == 0 else 1))

                self._links.append(link)
                bisect.insort(foundLinks, (m.start(), m.end()))

    def createLinksFormats(self):
        if not self._links:
            return None

        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        fmt.setForeground(ColorSchema.Link)

        formats = []
        for link in self._links:
            rg = createFormatRange(link.start, link.end - link.start, fmt)
            formats.append(rg)

        return formats

    def type(self):
        return self._type

    def isInfoType(self):
        return self._type == TextLine.File or \
            self._type == TextLine.FileInfo

    def text(self):
        return self._text

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

            patterns = {Link.Sha1: sha1_re,
                        Link.Email: email_re,
                        Link.Url: url_re}
            if self._patterns:
                patterns.update(self._patterns)
            self.__findLinks(patterns)

        if self._rehighlight:
            self.rehighlight()
            self._rehighlight = False
            # need relayout
            self._invalidated = True

        if self._invalidated:
            self.__relayout()
            self._invalidated = False

    def boundingRect(self):
        self.ensureLayout()
        return self._layout.boundingRect()

    def offsetForPos(self, pos):
        self.ensureLayout()
        line = self._layout.lineAt(0)
        return line.xToCursor(pos.x())

    def offsetToX(self, offset):
        self.ensureLayout()
        line = self._layout.lineAt(0)
        x, _ = line.cursorToX(offset)
        return x

    def draw(self, painter, pos, selections=None, clip=QRectF()):
        self.ensureLayout()
        self._layout.draw(painter, pos, selections, clip)

    def rehighlight(self):
        formats = self.createLinksFormats()
        if formats:
            self._layout.setAdditionalFormats(formats)

    def setCustomLinkPatterns(self, patterns):
        self._links.clear()
        self._patterns = patterns

        if self._layout:
            if patterns:
                patterns[Link.Sha1] = sha1_re
                patterns[Link.Email] = email_re
                patterns[Link.Url] = url_re
                self.__findLinks(patterns)
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
