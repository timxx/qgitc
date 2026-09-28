# -*- coding: utf-8 -*-
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from qgitc.textviewer import TextViewer
from tests.base import TestBase


class TestViewerFold(TestBase):
    """Block registration and fold interaction on TextViewer."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.viewer = TextViewer()
        self.viewer.resize(300, 200)
        self.viewer.show()
        self.processEvents()
        self.viewer.appendLines(
            ["line %d" % i for i in range(30)])
        self.processEvents()
        self.lineH = self.viewer.lineHeight

    def anchorY(self, lineNo):
        return lineNo * self.lineH + self.lineH // 3

    def addBlockAt(self, start, end):
        block = self.viewer._blockModel.addBlock(start, end)
        self.viewer._syncGutter()
        return block

    def stripInk(self, image, baseline, top, rows=1):
        """Pixels of the fold strip that differ from the blank strip."""
        gutter = self.viewer.gutterWidth()
        return [(x, y)
                for y in range(top, top + self.lineH * rows)
                for x in range(gutter)
                if image.pixel(x, y) != baseline.pixel(x, y)]

    def inkSize(self, ink):
        xs = [p[0] for p in ink]
        ys = [p[1] for p in ink]
        return max(xs) - min(xs) + 1, max(ys) - min(ys) + 1

    def blankStrip(self):
        """The strip reserved with no indicator painted."""
        self.viewer._blockModel.clearBlocks()
        self.viewer._blockModel.addBlock(0, 0)
        self.viewer._syncGutter()
        self.processEvents()
        return self.viewer.viewport().grab().toImage()

    # -- block registration ------------------------------------------------

    def testBeginEndBlockRegisters(self):
        self.viewer.beginBlock({"kind": "file", "path": "a.c"})
        self.viewer.appendLines(["extra 1", "extra 2"])
        self.viewer.endBlock()

        blocks = self.viewer._blockModel.blocks()
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].startLine, 30)
        self.assertEqual(blocks[0].endLine, 31)
        self.assertEqual(blocks[0].meta["path"], "a.c")
        # gutter reserved once a foldable block exists; just wide enough
        # for the fold triangle, so the text starts closer to the edge
        gutter = self.viewer.gutterWidth()
        width, _ = self.viewer.foldIndicatorSize()
        self.assertGreater(gutter, width)
        self.assertLessEqual(gutter, self.lineH)
        self.assertLess(self.viewer._foldStripWidth(), self.lineH)
        self.assertEqual(self.viewer.wrapWidth(),
                         self.viewer.viewport().width() - gutter)

    def testUnclosedBlockAutoClosesOnNextBegin(self):
        self.viewer.beginBlock()
        self.viewer.appendLines(["a", "b"])   # lines 30, 31
        self.viewer.beginBlock()  # closes the previous block
        self.viewer.appendLine("c")           # line 32
        self.viewer.endBlock()

        blocks = self.viewer._blockModel.blocks()
        self.assertEqual(len(blocks), 2)
        self.assertEqual((blocks[0].startLine, blocks[0].endLine),
                         (30, 31))
        self.assertEqual((blocks[1].startLine, blocks[1].endLine),
                         (32, 32))

    def testEmptyBlockIsDropped(self):
        self.viewer.beginBlock()
        self.viewer.endBlock()
        self.assertEqual(self.viewer._blockModel.blocks(), [])

    def testClearResetsBlocksAndGutter(self):
        self.viewer.beginBlock()
        self.viewer.appendLine("child")
        self.viewer.endBlock()
        self.assertGreater(self.viewer.gutterWidth(), 0)

        self.viewer.clear()
        self.assertEqual(self.viewer._blockModel.blocks(), [])
        self.assertEqual(self.viewer.gutterWidth(), 0)
        self.viewer.appendLines(["a", "b"])
        self.assertEqual(self.viewer.wrapWidth(),
                         self.viewer.viewport().width())

    # -- fold geometry -----------------------------------------------------

    def testFoldReducesScrollRange(self):
        block = self.addBlockAt(9, 19)
        bar = self.viewer.verticalScrollBar()
        before = bar.maximum()

        self.viewer.toggleFoldAt(9)
        self.assertTrue(block.folded)
        self.assertEqual(bar.maximum(), before - 10 * self.lineH)
        # line 20 resumes right after the anchor line 9
        self.assertEqual(self.viewer.textRowForPos(
            QPointF(0, self.viewer._blockModel.lineTop(20) + 3)), 20)

    def testHiddenLineUnreachableByPositionQueries(self):
        self.addBlockAt(9, 19)
        self.viewer.toggleFoldAt(9)

        y = 12 * self.lineH + 3
        self.assertNotEqual(
            self.viewer.textRowForPos(QPointF(0, y)), 12)

    def testFoldIndicatorFillsTheStrip(self):
        """The affordance is a painted triangle sized from the line height;
        the font glyph it replaced was a speck inside the reserved strip."""
        self.addBlockAt(0, 5)
        self.processEvents()
        withIndicator = self.viewer.viewport().grab().toImage()
        top = self.viewer._blockModel.lineTop(0)
        ink = self.stripInk(withIndicator, self.blankStrip(), top)
        self.assertTrue(ink)

        width, height = self.viewer.foldIndicatorSize()
        inkWidth, inkHeight = self.inkSize(ink)
        self.assertLessEqual(inkWidth, width + 1)
        self.assertLessEqual(inkHeight, height + 1)
        # large enough to be a control, and centred in the strip
        self.assertGreaterEqual(inkWidth, 6)
        xs = [p[0] for p in ink]
        gutter = self.viewer.gutterWidth()
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, (gutter - 1) / 2,
                               delta=2)

    def testCollapsedIndicatorIsTheExpandedOneRotated(self):
        """A folded block points right with the same triangle, so its tip is
        as blunt as the downward one; the old one kept the same bounding box
        and came out long and narrow, looking like a spike."""
        self.addBlockAt(0, 5)
        self.processEvents()
        expanded = self.viewer.viewport().grab().toImage()

        self.viewer.toggleFoldAt(0)
        self.processEvents()
        folded = self.viewer.viewport().grab().toImage()

        top = self.viewer._blockModel.lineTop(0)
        baseline = self.blankStrip()
        bodyWidth, bodyHeight = self.inkSize(self.stripInk(expanded, baseline, top))
        tipWidth, tipHeight = self.inkSize(self.stripInk(folded, baseline, top))

        # the downward triangle is the wider one ...
        self.assertGreater(bodyWidth, bodyHeight)
        # ... and the right-pointing one is that shape rotated, so it is the
        # taller one: pointing sideways must not sharpen the tip
        self.assertGreater(tipHeight, tipWidth)

    def testFoldedAnchorStillPaintsTheChip(self):
        """The indicator paints with its own pen and brush; the folded-content
        chip drawn after the anchor text must survive that."""
        self.addBlockAt(2, 8)
        self.processEvents()
        expanded = self.viewer.viewport().grab().toImage()

        self.viewer.toggleFoldAt(2)
        self.processEvents()
        folded = self.viewer.viewport().grab().toImage()

        textLine = self.viewer.textLineAt(2)
        rows = textLine.visualLineCount()
        chipX = int(self.viewer._foldChipX(textLine))
        chipTop = self.viewer._blockModel.lineTop(2) + (rows - 1) * self.lineH
        ink = [(x, y) for y in range(chipTop, chipTop + self.lineH)
               for x in range(chipX, chipX + 12)
               if expanded.pixel(x, y) != folded.pixel(x, y)]
        self.assertTrue(ink, "the folded-content chip was not painted")

    # -- click interaction -------------------------------------------------

    def testGutterClickTogglesAndEmits(self):
        block = self.addBlockAt(2, 8)

        spy = QSignalSpy(self.viewer.textLineClicked)
        x = self.viewer.gutterWidth() // 2
        QTest.mouseClick(self.viewer.viewport(), Qt.LeftButton,
                         pos=QPoint(x, int(self.anchorY(2))))

        self.assertTrue(block.folded)
        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0)[0].lineNo(), 2)

        # click again expands
        QTest.mouseClick(self.viewer.viewport(), Qt.LeftButton,
                         pos=QPoint(x, int(self.anchorY(2))))
        self.assertFalse(block.folded)

    def testGutterClickOnPlainLineDoesNothing(self):
        block = self.addBlockAt(2, 8)
        spy = QSignalSpy(self.viewer.textLineClicked)
        x = self.viewer.gutterWidth() // 2
        QTest.mouseClick(self.viewer.viewport(), Qt.LeftButton,
                         pos=QPoint(x, int(self.anchorY(0))))

        self.assertFalse(block.folded)
        self.assertEqual(spy.count(), 0)

    def testAnchorTextClickPlacesCursorWithoutFolding(self):
        block = self.addBlockAt(2, 8)
        spy = QSignalSpy(self.viewer.textLineClicked)

        x = self.viewer.gutterWidth() + 20
        QTest.mouseClick(self.viewer.viewport(), Qt.LeftButton,
                         pos=QPoint(x, int(self.anchorY(2))))

        self.assertFalse(block.folded)
        self.assertEqual(spy.count(), 1)
        self.assertEqual(self.viewer.textCursor.beginLine(), 2)

    def testGutterDragDoesNotToggle(self):
        block = self.addBlockAt(2, 8)
        x = self.viewer.gutterWidth() // 2

        QTest.mousePress(self.viewer.viewport(), Qt.LeftButton,
                         pos=QPoint(x, int(self.anchorY(2))))
        QTest.mouseMove(self.viewer.viewport(),
                        QPoint(x, int(self.anchorY(6))))
        QTest.mouseRelease(self.viewer.viewport(), Qt.LeftButton,
                           pos=QPoint(x, int(self.anchorY(6))))

        self.assertFalse(block.folded)

    def testChipClickExpandsFoldedBlock(self):
        block = self.addBlockAt(2, 8)
        self.viewer.toggleFoldAt(2)
        self.assertTrue(block.folded)

        # chip sits right after the anchor text
        chipX = self.viewer._foldChipX(self.viewer.textLineAt(2))
        QTest.mouseClick(self.viewer.viewport(), Qt.LeftButton,
                         pos=QPoint(int(chipX) + 3,
                                    int(self.anchorY(2))))
        self.assertFalse(block.folded)

    # -- fold all / expand all --------------------------------------------

    def testFoldAllExpandAllTopLevelOnly(self):
        outer = self.addBlockAt(0, 29)
        # nested child block: lines 5..9 inside outer
        inner = self.viewer._blockModel.addBlock(5, 9, parent=outer)
        self.viewer._blockModel.setFolded(inner, True)

        self.viewer.foldAllBlocks()
        self.assertTrue(outer.folded)
        self.assertTrue(inner.folded)

        self.viewer.expandAllBlocks()
        self.assertFalse(outer.folded)
        # child keeps its own folded state
        self.assertTrue(inner.folded)
        self.assertTrue(self.viewer._blockModel.isLineHidden(7))
        # outside the child everything is visible again
        self.assertFalse(self.viewer._blockModel.isLineHidden(15))

    # -- auto expand on jump / find ---------------------------------------

    def testGotoLineExpandsFoldedTarget(self):
        block = self.addBlockAt(3, 9)
        self.viewer.toggleFoldAt(3)
        self.assertTrue(block.folded)

        self.viewer.gotoLine(5, centralOnView=False)
        self.assertFalse(block.folded)
        self.assertTrue(self.viewer._blockModel.isLineVisible(5))

    def testFindSelectExpandsFoldedBlock(self):
        self.viewer.appendLines(["x", "needle here", "y"])
        block = self.addBlockAt(30, 33)
        self.viewer.toggleFoldAt(30)
        self.assertTrue(block.folded)

        results = self.viewer.findAll("needle")
        self.assertEqual(len(results), 1)
        self.viewer.select(results[0])
        self.assertFalse(block.folded)

    # -- selection / copy includes folded content --------------------------

    def testSelectAllIncludesFoldedLines(self):
        self.addBlockAt(3, 9)
        self.viewer.toggleFoldAt(3)

        self.viewer.selectAll()
        text = self.viewer.selectedText
        self.assertIn("line 5", text)
        self.assertIn("line 29", text)
        # every logical line is included
        for i in range(30):
            self.assertIn("line %d" % i, text)

    def testCopyIncludesFoldedLines(self):
        self.addBlockAt(3, 9)
        self.viewer.toggleFoldAt(3)

        self.viewer.selectAll()
        self.viewer.copy()
        clipboard = QApplication.clipboard().text()
        self.assertIn("line 5", clipboard)
        self.assertEqual(clipboard, self.viewer.selectedText)

    # -- context menu / tooltip --------------------------------------------

    def testContextMenuVisibility(self):
        # build the menu first; line 0 has no block anchored
        menu = self.viewer.contextMenu
        self.viewer._contextLine = 0
        self.viewer.updateContextMenu(None)
        self.assertFalse(self.viewer._acFoldBlock.isVisible())

        self.addBlockAt(0, 10)
        self.viewer._contextLine = 0
        self.viewer.updateContextMenu(None)
        self.assertTrue(self.viewer._acFoldBlock.isVisible())

    def testFoldTipForLine(self):
        self.assertIsNone(self.viewer.foldTipForLine(5))
        block = self.addBlockAt(2, 9)
        tip = self.viewer.foldTipForLine(2)
        self.assertIn("7", tip)  # lines 3..9 hidden => 7 lines
        self.viewer.toggleFoldAt(2)
        tip = self.viewer.foldTipForLine(2)
        self.assertIn("7", tip)

    def testAddBlockOverExistingLines(self):
        block = self.viewer.addBlock(2, 5, meta={"title": "middle"})

        self.assertEqual((2, 5), (block.startLine, block.endLine))
        self.assertEqual(1, len(self.viewer._blockModel.blocks()))
        self.assertTrue(self.viewer.canFoldAt(2))
        self.assertGreater(self.viewer.gutterWidth(), 0)

        self.viewer.toggleFoldAt(2)
        self.assertTrue(self.viewer._blockModel.isLineVisible(2))
        self.assertFalse(self.viewer._blockModel.isLineVisible(5))
        self.assertIn("middle", self.viewer.foldTipForLine(2))

    def testAddBlockDropsAnEmptyRange(self):
        self.assertIsNone(self.viewer.addBlock(4, 3))
        self.assertEqual([], self.viewer._blockModel.blocks())

    def testFoldGlyphDoesNotLeakItsPen(self):
        """The fold affordance must not recolour what follows it: a line
        without an explicit format keeps the widget text colour whether
        or not a fold glyph was painted earlier in the same pass."""
        self.addBlockAt(0, 5)
        self.processEvents()
        withGlyph = self.viewer.viewport().grab().toImage()

        # same geometry (a block still reserves the gutter), no glyph
        self.viewer._blockModel.clearBlocks()
        self.viewer._blockModel.addBlock(0, 0)
        self.viewer._syncGutter()
        self.processEvents()
        noGlyph = self.viewer.viewport().grab().toImage()

        self.assertEqual(withGlyph.size(), noGlyph.size())
        top = self.viewer._blockModel.lineTop(3)
        differing = [(x, y)
                     for y in range(top, top + self.lineH)
                     for x in range(withGlyph.width())
                     if withGlyph.pixel(x, y) != noGlyph.pixel(x, y)]
        self.assertEqual([], differing[:5],
                         "line 3 was recoloured by the fold glyph")
