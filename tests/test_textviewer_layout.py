# -*- coding: utf-8 -*-
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QSignalSpy, QTest

from qgitc.textviewer import TextViewer
from tests.base import TestBase


class TestTextViewerPixelScroll(TestBase):
    """Pixel-based vertical scrolling with logical-line public APIs.

    In the degenerate case (no wrap, no folds) one line is exactly
    lineHeight pixels, so every observable behavior must match the old
    scrollBar-value == line-number model.
    """

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.viewer = TextViewer()
        self.viewer.resize(300, 200)
        # the scroll range follows the viewport size: show the viewer so
        # the viewport geometry is settled before it is asserted on
        self.viewer.show()
        self.viewer.appendLines(["line %d" % i for i in range(100)])
        self.processEvents()

    def testScrollbarRangeIsPixels(self):
        bar = self.viewer.verticalScrollBar()
        lineH = self.viewer.lineHeight
        expected = max(0, 100 * lineH - self.viewer.viewport().height())
        self.assertEqual(bar.maximum(), expected)
        self.assertEqual(bar.pageStep(),
                         self.viewer.viewport().height())
        self.assertEqual(bar.singleStep(), lineH)

    def testFirstVisibleLineIsLogicalLineAtTop(self):
        lineH = self.viewer.lineHeight
        bar = self.viewer.verticalScrollBar()
        bar.setValue(3 * lineH + lineH // 3)  # lands inside line 3
        self.assertEqual(self.viewer.firstVisibleLine(), 3)

    def testGotoLineWithoutCentering(self):
        self.viewer.gotoLine(50, centralOnView=False)
        self.assertEqual(self.viewer.firstVisibleLine(), 50)
        self.assertEqual(self.viewer.verticalScrollBar().value(),
                         50 * self.viewer.lineHeight)

    def testGotoLineCenters(self):
        self.viewer.gotoLine(90, centralOnView=True)
        first = self.viewer.firstVisibleLine()
        halfPage = self.viewer.viewport().height() \
            // self.viewer.lineHeight // 2
        self.assertEqual(first, 90 - halfPage)

    def testGotoLineClampsOutOfRange(self):
        before = self.viewer.verticalScrollBar().value()
        self.viewer.gotoLine(-5)
        self.viewer.gotoLine(9999)
        self.assertEqual(self.viewer.verticalScrollBar().value(), before)

    def testTextRowForPosMapsYToLine(self):
        lineH = self.viewer.lineHeight
        pos = QPointF(10, 3 * lineH + lineH // 3)
        self.assertEqual(self.viewer.textRowForPos(pos), 3)
        self.assertEqual(self.viewer.textRowForPos(QPointF(10, 0)), 0)

    def testTextRowForPosSkipsFoldedLines(self):
        # fold lines 40..59 behind anchor 39
        self.viewer._blockModel.addBlock(39, 59)
        self.viewer._blockModel.setFolded(
            self.viewer._blockModel.blocks()[0], True)
        self.viewer._adjustScrollbars()
        lineH = self.viewer.lineHeight

        # the anchor still occupies its own row right after line 38;
        # hidden lines 40..59 take no space, so line 60 starts exactly
        # where line 40 would have: 40 * lineH
        yOfLine60 = 40 * lineH
        pos = QPointF(5, yOfLine60 + lineH // 3)
        self.assertEqual(self.viewer.textRowForPos(pos), 60)

    def testEnsureLineVisibleScrollsToLogicalLine(self):
        self.viewer.ensureLineVisible(80, centralOnView=False)
        self.assertEqual(self.viewer.firstVisibleLine(), 80)

    def testClickStillEmitsLogicalLine(self):
        spy = QSignalSpy(self.viewer.textLineClicked)
        # click near the top of the viewport: line 0
        QTest.mouseClick(self.viewer.viewport(), Qt.LeftButton,
                         pos=QPointF(10, 5).toPoint())
        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0)[0].lineNo(), 0)

    def testClickHitsLineAfterScroll(self):
        self.viewer.gotoLine(50, centralOnView=False)
        spy = QSignalSpy(self.viewer.textLineClicked)
        QTest.mouseClick(self.viewer.viewport(), Qt.LeftButton,
                         pos=QPointF(10, self.viewer.lineHeight + 3).toPoint())
        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0)[0].lineNo(), 51)


class TestTextViewerWrapGeometry(TestBase):
    """Viewer feeds wrap width to opted-in lines and maps their height."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.viewer = TextViewer()
        self.viewer.resize(300, 200)
        # QAbstractScrollArea only syncs the viewport on show, and
        # wrap width follows the viewport
        self.viewer.show()
        self.processEvents()
        self.longText = " ".join("comment%02d" % i for i in range(50))

    def appendWrapped(self, text):
        textLine = self.viewer.toTextLine(text)
        textLine.setWrap(True)
        self.viewer.appendTextLine(textLine)
        return textLine

    def testWrappedLineHeightUsesVisualRowCount(self):
        self.viewer.appendLine("head")
        self.appendWrapped(self.longText)
        self.viewer.appendLine("tail")
        self.processEvents()

        model = self.viewer._blockModel
        lineH = self.viewer.lineHeight
        self.assertEqual(model.lineHeight(0), lineH)
        textLine = self.viewer.textLineAt(1)
        self.assertGreater(textLine.visualLineCount(), 1)
        self.assertEqual(model.lineHeight(1),
                         textLine.visualLineCount() * lineH)
        self.assertGreater(model.contentHeight(), 3 * lineH)

    def testWrapWidthFollowsViewport(self):
        self.appendWrapped(self.longText)
        self.processEvents()
        self.assertEqual(self.viewer.textLineAt(0).wrapWidth(),
                         self.viewer.viewport().width())

    def testResizeReflowsWrappedLine(self):
        self.appendWrapped(self.longText)
        self.processEvents()
        before = self.viewer.textLineAt(0).visualLineCount()

        self.viewer.resize(150, 200)
        self.processEvents()

        textLine = self.viewer.textLineAt(0)
        self.assertGreater(textLine.visualLineCount(), before)
        self.assertEqual(self.viewer._blockModel.lineHeight(0),
                         textLine.visualLineCount()
                         * self.viewer.lineHeight)
        self.assertEqual(textLine.wrapWidth(),
                         self.viewer.viewport().width())

    def testScrollRangeAccountsForWrap(self):
        self.viewer.appendLines(["a", "b"])
        self.appendWrapped(self.longText)
        self.processEvents()
        bar = self.viewer.verticalScrollBar()
        expected = max(0, self.viewer._blockModel.contentHeight()
                       - self.viewer.viewport().height())
        self.assertEqual(bar.maximum(), expected)

    def testFirstVisibleLineSkipsIntoWrappedContent(self):
        self.viewer.appendLines(["a", "b"])
        self.appendWrapped(self.longText)
        self.processEvents()
        model = self.viewer._blockModel

        # scroll so that the middle of the wrapped line is at the top
        midY = model.lineTop(2) + 2 * self.viewer.lineHeight
        self.viewer.verticalScrollBar().setValue(midY)
        self.assertEqual(self.viewer.firstVisibleLine(), 2)

    def testClearDropsWrappedTracking(self):
        self.appendWrapped(self.longText)
        self.processEvents()
        self.viewer.clear()
        self.assertEqual(self.viewer._blockModel.contentHeight(), 0)
        self.viewer.appendLines(["x"])
        self.assertEqual(self.viewer._blockModel.contentHeight(),
                         self.viewer.lineHeight)
