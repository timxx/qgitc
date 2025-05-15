# -*- coding: utf-8 -*-
import re
import unittest
from typing import List

from PySide6.QtGui import QTextLayout

from qgitc.textline import Link, SourceTextLineBase, TextLine
from tests.base import TestBase


class TestTextLine(unittest.TestCase):

    def testFindLinks(self):
        text = "foo:12345;67890 BUG#666666 revert 565815a67"
        patterns = [
            (Link.BugId, re.compile(
                r"(foo[:：]([0-9]{5,}))"), "https://foo.com/bug/"),
            (Link.BugId, re.compile(r"([0-9]{5,})"), "https://bug.com/id="),
        ]
        for type, pattern in TextLine.builtinPatterns().items():
            patterns.append((type, pattern, None))

        links = TextLine.findLinks(text, patterns)
        self.assertEqual(4, len(links))

        self.assertEqual(links[0].type, Link.BugId)
        self.assertEqual(links[0].start, 0)
        self.assertEqual(links[0].end, 9)
        self.assertEqual(links[0].data, "https://foo.com/bug/12345")

        self.assertEqual(links[1].type, Link.BugId)
        self.assertEqual(links[1].start, 10)
        self.assertEqual(links[1].end, 15)
        self.assertEqual(links[1].data, "https://bug.com/id=67890")

        self.assertEqual(links[2].type, Link.BugId)
        self.assertEqual(links[2].start, 20)
        self.assertEqual(links[2].end, 26)
        self.assertEqual(links[2].data, "https://bug.com/id=666666")

        self.assertEqual(links[3].type, Link.Sha1)
        self.assertEqual(links[3].start, 34)
        self.assertEqual(links[3].end, 43)
        self.assertEqual(links[3].data, "565815a67")

    def testLinkOverlap(self):
        patterns = [
            (Link.BugId, re.compile(
                r"(foo[:：]([0-9]{5,}))"), "https://foo.com/bug/"),
            (Link.BugId, re.compile(r"([0-9]{5,} [0-9]{5,})"), None),
        ]

        links = TextLine.findLinks("foo:12345 67890", patterns)
        self.assertEqual(1, len(links))

        self.assertEqual(links[0].type, Link.BugId)
        self.assertEqual(links[0].start, 0)
        self.assertEqual(links[0].end, 9)
        self.assertEqual(links[0].data, "https://foo.com/bug/12345")

        patterns = [
            (Link.BugId, re.compile(r"([0-9]{5,})"), None),
            (Link.Sha1, TextLine.builtinPatterns()[Link.Sha1], None)
        ]
        links = TextLine.findLinks("1234567", patterns)
        self.assertEqual(1, len(links))
        self.assertEqual(links[0].type, Link.BugId)

    def testTextLength(self):
        textLine = TextLine("hello", None)
        self.assertEqual(textLine.utf16Length(), 5)
        self.assertEqual(len(textLine.text()), 5)

        textLine = TextLine("hello 你好", None)
        self.assertEqual(textLine.utf16Length(), 8)
        self.assertEqual(len(textLine.text()), 8)

        textLine = TextLine("hello 😀", None)
        self.assertEqual(textLine.utf16Length(), 8)
        self.assertEqual(len(textLine.text()), 7)

        textLine = TextLine("你好😀", None)
        self.assertEqual(textLine.utf16Length(), 4)
        self.assertEqual(len(textLine.text()), 3)

        textLine = TextLine("😀 你好", None)
        self.assertEqual(textLine.utf16Length(), 5)
        self.assertEqual(len(textLine.text()), 4)

        textLine = TextLine("🤗😏🥵", None)
        self.assertEqual(textLine.utf16Length(), 6)
        self.assertEqual(len(textLine.text()), 3)

    def testIndex(self):
        textLine = TextLine("hello你好", None)
        for i in range(5):
            self.assertEqual(textLine.mapToUtf16(i), i)
            self.assertEqual(textLine.mapFromUtf16(i), i)

        textLine = TextLine("🤗", None)
        self.assertEqual(textLine.mapToUtf16(0), 0)
        self.assertEqual(textLine.mapToUtf16(1), 2)
        self.assertEqual(textLine.mapFromUtf16(0), 0)
        self.assertEqual(textLine.mapFromUtf16(2), 1)

        textLine = TextLine("😏he🤗llo🥵", None)
        self.assertEqual(textLine.mapToUtf16(0), 0)
        self.assertEqual(textLine.mapToUtf16(1), 2)
        self.assertEqual(textLine.mapToUtf16(2), 3)
        self.assertEqual(textLine.mapToUtf16(3), 4)
        self.assertEqual(textLine.mapToUtf16(4), 6)
        self.assertEqual(textLine.mapToUtf16(5), 7)
        self.assertEqual(textLine.mapToUtf16(6), 8)
        self.assertEqual(textLine.mapToUtf16(7), 9)
        self.assertEqual(textLine.mapToUtf16(8), 11)

        self.assertEqual(textLine.mapFromUtf16(0), 0)
        self.assertEqual(textLine.mapFromUtf16(2), 1)
        self.assertEqual(textLine.mapFromUtf16(3), 2)
        self.assertEqual(textLine.mapFromUtf16(4), 3)
        self.assertEqual(textLine.mapFromUtf16(6), 4)
        self.assertEqual(textLine.mapFromUtf16(7), 5)
        self.assertEqual(textLine.mapFromUtf16(8), 6)
        self.assertEqual(textLine.mapFromUtf16(9), 7)
        self.assertEqual(textLine.mapFromUtf16(11), 8)


class TestFormatRange(TestBase):

    def doCreateRepo(self):
        pass

    def testApplyWhitespace(self):
        textLine = SourceTextLineBase("hello", None, None)
        formats: List[QTextLayout.FormatRange] = []
        textLine._applyWhitespaces(textLine.text(), formats)
        self.assertEqual(len(formats), 0)

        textLine = SourceTextLineBase("hello 你  好", None, None)
        formats.clear()
        textLine._applyWhitespaces(textLine.text(), formats)
        self.assertEqual(len(formats), 2)
        self.assertEqual(formats[0].start, 5)
        self.assertEqual(formats[0].length, 1)

        self.assertEqual(formats[1].start, 7)
        self.assertEqual(formats[1].length, 2)

        textLine = SourceTextLineBase(
            'textLine = TextLine("🤗😏🥵", None)', None, None)
        formats.clear()
        textLine._applyWhitespaces(textLine.text(), formats)
        self.assertEqual(len(formats), 3)

        self.assertEqual(formats[0].start, 8)
        self.assertEqual(formats[0].length, 1)

        self.assertEqual(formats[1].start, 10)
        self.assertEqual(formats[1].length, 1)

        self.assertEqual(formats[2].start, 29)
        self.assertEqual(formats[2].length, 1)

    def testLinkRange(self):
        patterns = [
            (Link.BugId, re.compile(r"([0-9]{5,})"), None),
        ]

        textLine = TextLine("😛 123456 hello", self.app.font())
        textLine.setCustomLinkPatterns(patterns)
        textLine.ensureLayout()
        links: List[QTextLayout.FormatRange] = textLine.createLinksFormats()

        self.assertEqual(1, len(links))
        self.assertEqual(links[0].start, 3)
        self.assertEqual(links[0].length, 6)
