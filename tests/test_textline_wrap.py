# -*- coding: utf-8 -*-
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QTextOption

from qgitc.textline import TextLine
from tests.base import TestBase


class TestTextLineWrap(TestBase):
    """Word-wrap support on TextLine: multi visual rows per logical line."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.font = QFont()
        self.option = QTextOption()
        self.option.setWrapMode(QTextOption.NoWrap)

    def makeLine(self, text):
        return TextLine(text, self.font, self.option)

    def longText(self, words=40):
        return " ".join("word%02d" % i for i in range(words))

    def testDefaultIsSingleRow(self):
        line = self.makeLine(self.longText())
        self.assertFalse(line.wrap())
        line.ensureLayout()
        self.assertEqual(line.visualLineCount(), 1)
        singleHeight = line.boundingRect().height()

        line.setWrap(True)
        line.setWrapWidth(60)
        line.ensureLayout()
        self.assertGreater(line.visualLineCount(), 1)
        self.assertGreater(line.boundingRect().height(), singleHeight)

    def testSharedOptionNotMutated(self):
        # the QTextOption instance is shared between lines: enabling wrap
        # on one line must not change the shared option
        self.makeLine("some text").setWrap(True)
        self.assertEqual(self.option.wrapMode(), QTextOption.NoWrap)

    def testWrapWidthControlsRowCount(self):
        text = self.longText(60)
        narrow = self.makeLine(text)
        narrow.setWrap(True)
        narrow.setWrapWidth(50)
        narrow.ensureLayout()

        wide = self.makeLine(text)
        wide.setWrap(True)
        wide.setWrapWidth(500)
        wide.ensureLayout()

        self.assertGreater(narrow.visualLineCount(),
                           wide.visualLineCount())

    def testWrapWidthChangeRelayouts(self):
        line = self.makeLine(self.longText(60))
        line.setWrap(True)
        line.setWrapWidth(300)
        line.ensureLayout()
        before = line.visualLineCount()

        line.setWrapWidth(60)
        line.ensureLayout()
        self.assertGreater(line.visualLineCount(), before)

    def testUnwrapRestoresSingleRow(self):
        line = self.makeLine(self.longText())
        line.setWrap(True)
        line.setWrapWidth(60)
        line.ensureLayout()
        self.assertGreater(line.visualLineCount(), 1)

        line.setWrap(False)
        line.ensureLayout()
        self.assertEqual(line.visualLineCount(), 1)

    def testRowAtOffsetCoversWholeLine(self):
        text = self.longText(60)
        line = self.makeLine(text)
        line.setWrap(True)
        line.setWrapWidth(60)
        line.ensureLayout()
        rowCount = line.visualLineCount()
        self.assertGreater(rowCount, 1)

        self.assertEqual(line.rowAtOffset(0), 0)
        # end of text belongs to the last row
        self.assertEqual(line.rowAtOffset(len(text)), rowCount - 1)
        # rows are monotonic over offsets
        rows = [line.rowAtOffset(i) for i in range(len(text))]
        self.assertEqual(rows, sorted(rows))
        self.assertEqual(max(rows), rowCount - 1)

    def testOffsetRoundTripOnEveryRow(self):
        text = self.longText(30)
        line = self.makeLine(text)
        line.setWrap(True)
        line.setWrapWidth(70)
        line.ensureLayout()

        for offset in range(1, len(text) - 1, 7):
            row = line.rowAtOffset(offset)
            x = line.offsetToX(offset, row)
            back = line.offsetForPos(QPointF(x, 0), row)
            self.assertEqual(back, offset,
                             msg="offset %d row %d" % (offset, row))

    def testOffsetToXAutoPicksOwningRow(self):
        text = self.longText(30)
        line = self.makeLine(text)
        line.setWrap(True)
        line.setWrapWidth(70)
        line.ensureLayout()

        lastRow = line.visualLineCount() - 1
        endOffset = len(text) - 2
        self.assertEqual(line.rowAtOffset(endOffset), lastRow)
        # auto-row x equals explicit last-row x, and stays within a row
        self.assertEqual(line.offsetToX(endOffset),
                         line.offsetToX(endOffset, lastRow))

    def testEmptyLineKeepsOneRow(self):
        line = self.makeLine("")
        line.setWrap(True)
        line.setWrapWidth(60)
        line.ensureLayout()
        self.assertEqual(line.visualLineCount(), 1)
        self.assertEqual(line.offsetToX(0), 0)
        self.assertEqual(line.offsetForPos(QPointF(0, 0)), 0)

    def testWrapDisabledIgnoresWrapWidth(self):
        line = self.makeLine(self.longText())
        line.setWrapWidth(40)  # no-op: wrap not enabled
        line.ensureLayout()
        self.assertEqual(line.visualLineCount(), 1)
