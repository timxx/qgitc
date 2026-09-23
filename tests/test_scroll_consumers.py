# -*- coding: utf-8 -*-
from PySide6.QtCore import QPointF

from qgitc.blameline import BlameLine
from qgitc.blamesourceviewer import BlameSourceViewer
from tests.base import TestBase


class TestPixelScrollConsumers(TestBase):
    """Consumers that historically read the scrollbar value as a line
    number must follow logical-line semantics after the pixel-scroll
    switch."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.viewer = BlameSourceViewer()
        # the revision panel takes a fixed chunk of the width; keep the
        # window wide enough that the main viewport stays usable
        self.viewer.resize(800, 200)
        self.viewer.show()
        self.processEvents()

        revs = []
        texts = []
        for i in range(30):
            rev = BlameLine()
            rev.sha1 = "abcdef0%d" % (i // 10)
            rev.author = "author"
            rev.authorTime = "2020-05-27 10:00:00"
            rev.oldLineNo = i + 1
            revs.append(rev)
            texts.append(("line %d" % i).encode())
        # appendBlameLines consumes line.text
        for rev, text in zip(revs, texts):
            rev.text = text
        self.viewer.beginReading()
        self.viewer.appendBlameLines(revs)
        self.viewer.endReading()
        self.processEvents()
        self.lineH = self.viewer.lineHeight
        self.panel = self.viewer._panel

    def scrollMidLine(self, lineNo, third=1):
        value = lineNo * self.lineH + self.lineH // 3 * third
        self.viewer.verticalScrollBar().setValue(value)
        return value

    def testFirstVisibleLineFollowsFractionalScroll(self):
        self.scrollMidLine(3)
        self.assertEqual(self.viewer.firstVisibleLine(), 3)

    def testContentOffsetReflectsFraction(self):
        value = self.scrollMidLine(3)
        offset = self.viewer.contentOffset()
        expected = 3 * self.lineH - value
        self.assertEqual(int(offset.y()), expected)
        self.assertLess(int(offset.y()), 0)

    def testPanelClickRowMatchesViewerGeometry(self):
        # a click 2px below the top of the viewport must hit the same
        # logical line the viewer paints there, not line 2
        self.scrollMidLine(3)
        expected = self.viewer.textRowForPos(QPointF(5, 2))
        self.assertEqual(expected, 3)
        self.assertEqual(self.panel.textRowForPos(QPointF(5, 2)),
                         expected)

    def testLineRectTracksFractionalScroll(self):
        value = self.scrollMidLine(3)
        rect = self.viewer._lineRect(3)
        self.assertTrue(rect.isValid())
        self.assertEqual(rect.top(), 3 * self.lineH - value)
