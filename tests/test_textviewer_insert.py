# -*- coding: utf-8 -*-
from qgitc.textviewer import TextViewer
from tests.base import TestBase


class TestTextViewerInsert(TestBase):
    """insertLines(index, lines) splices new lines in and renumbers the
    ones after them, so every line-numbered piece of state moves along."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.viewer = TextViewer()
        self.viewer.resize(300, 200)
        self.viewer.show()
        self.processEvents()

        self.viewer.appendLines(["line %d" % i for i in range(5)])
        self.processEvents()
        self.lineH = self.viewer.lineHeight

    def texts(self):
        return [self.viewer.textLineAt(i).text()
                for i in range(self.viewer.textLineCount())]

    def testInsertInTheMiddle(self):
        self.viewer.insertLines(2, ["new a", "new b"])

        self.assertEqual(7, self.viewer.textLineCount())
        self.assertEqual(["line 0", "line 1", "new a", "new b",
                          "line 2", "line 3", "line 4"], self.texts())

    def testInsertAtTheEndAppends(self):
        self.viewer.insertLines(5, ["tail"])

        self.assertEqual(6, self.viewer.textLineCount())
        self.assertEqual("tail", self.viewer.textLineAt(5).text())

    def testOutOfRangeIndexClamps(self):
        self.viewer.insertLines(99, ["tail"])
        self.assertEqual("tail", self.viewer.textLineAt(5).text())

        self.viewer.insertLines(-5, ["head"])
        self.assertEqual("head", self.viewer.textLineAt(0).text())

    def testInsertedTextLineKeepsItsLineNumber(self):
        moved = self.viewer.textLineAt(4)
        self.viewer.insertLines(1, ["x", "y"])

        self.assertEqual(6, moved.lineNo())
        self.assertIs(moved, self.viewer.textLineAt(6))

    def testWrappedLineHeightFollowsTheShift(self):
        longText = " ".join("word%02d" % i for i in range(60))
        self.viewer.insertLines(1, [longText])
        line = self.viewer.textLineAt(1)
        line.setWrap(True)
        self.viewer.initTextLine(line, 1)
        self.processEvents()
        rows = line.visualLineCount()
        self.assertGreater(rows, 1)
        self.assertEqual(rows * self.lineH,
                         self.viewer._blockModel.lineHeight(1))

        self.viewer.insertLines(0, ["a", "b"])

        self.assertEqual(3, line.lineNo())
        self.assertEqual(rows * self.lineH,
                         self.viewer._blockModel.lineHeight(3))
        self.assertEqual(self.lineH, self.viewer._blockModel.lineHeight(1))

    def testSelectionFollowsTheInsertedLines(self):
        cursor = self.viewer.textCursor
        cursor.moveTo(3, 1)
        cursor.selectTo(4, 2)

        self.viewer.insertLines(0, ["a", "b"])

        self.assertEqual(5, cursor.beginLine())
        self.assertEqual(1, cursor.beginPos())
        self.assertEqual(6, cursor.endLine())
        self.assertEqual(2, cursor.endPos())

    def testFindHighlightsFollowTheShift(self):
        results = self.viewer.findAll("line 3")
        self.viewer.highlightFindResult(results)
        self.assertEqual(1, len(self.viewer._highlightFind))

        self.viewer.insertLines(0, ["a"])

        self.assertEqual(4, self.viewer._highlightFind[0].beginLine())
        self.assertEqual(4, self.viewer._highlightFind[0].endLine())

    def testInsertAboveTheViewportKeepsTheContentInPlace(self):
        self.viewer.appendLines(["line %d" % i for i in range(5, 30)])
        self.wait(300)
        self.viewer.verticalScrollBar().setValue(
            self.viewer._blockModel.lineTop(10))
        self.assertEqual(10, self.viewer.firstVisibleLine())
        value = self.viewer.verticalScrollBar().value()

        self.viewer.insertLines(0, ["a", "b"])

        self.assertEqual(12, self.viewer.firstVisibleLine())
        self.assertEqual(value + 2 * self.lineH,
                         self.viewer.verticalScrollBar().value())

    def testInsertBelowTheViewportKeepsTheScrollValue(self):
        self.viewer.appendLines(["line %d" % i for i in range(5, 30)])
        self.wait(300)
        self.viewer.verticalScrollBar().setValue(
            self.viewer._blockModel.lineTop(2))
        value = self.viewer.verticalScrollBar().value()

        self.viewer.insertLines(20, ["a", "b"])

        self.assertEqual(value, self.viewer.verticalScrollBar().value())
        self.assertEqual(2, self.viewer.firstVisibleLine())

    def testLongLineInsertedBehindTheSweepWidensHScroll(self):
        # drain the conversion sweep first, so the insertion lands behind it
        self.wait(300)
        self.assertEqual(0, self.viewer.horizontalScrollBar().maximum())

        self.viewer.insertLines(1, ["x" * 400])
        self.wait(300)

        self.assertGreater(self.viewer.horizontalScrollBar().maximum(), 0)

    def testRescanOfBuiltLinesIsBatched(self):
        # a sweep that rewinds must not cost one event-loop turn per line
        self.viewer.appendLines(["line %d" % i for i in range(5, 200)])
        self.wait(400)

        turns = []
        original = self.viewer._onConvertEvent
        self.viewer._onConvertEvent = lambda: (turns.append(1), original())

        self.viewer.insertLines(1, ["x" * 400])
        self.wait(400)

        self.assertLess(len(turns), 50)
