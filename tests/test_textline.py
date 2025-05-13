# -*- coding: utf-8 -*-
import re
import unittest

from qgitc.textline import Link, TextLine


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
