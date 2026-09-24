# -*- coding: utf-8 -*-
import unittest

from qgitc.blockmodel import Block, BlockModel


class TestBlock(unittest.TestCase):
    def testContainsLine(self):
        block = Block(2, 5)
        self.assertFalse(block.containsLine(1))
        # anchor line stays visible but still belongs to the block
        self.assertTrue(block.containsLine(2))
        self.assertTrue(block.containsLine(5))
        self.assertFalse(block.containsLine(6))

    def testParentAndChildren(self):
        parent = Block(0, 9)
        child = Block(3, 4, parent=parent)
        self.assertIs(child.parent, parent)
        self.assertIn(child, parent.children)

    def testIsTopLevel(self):
        parent = Block(0, 9)
        child = Block(3, 4, parent=parent)
        self.assertTrue(parent.isTopLevel())
        self.assertFalse(child.isTopLevel())


class TestBlockModelMapping(unittest.TestCase):
    """lineNo <-> pixel-Y mapping without any folded block."""

    def setUp(self):
        self.model = BlockModel(defaultHeight=10)
        self.model.setLineCount(5)

    def testLineTop(self):
        self.assertEqual(self.model.lineTop(0), 0)
        self.assertEqual(self.model.lineTop(3), 30)

    def testContentHeight(self):
        self.assertEqual(self.model.contentHeight(), 50)

    def testLineAt(self):
        self.assertEqual(self.model.lineAt(0), 0)
        self.assertEqual(self.model.lineAt(29), 2)
        self.assertEqual(self.model.lineAt(30), 3)
        # clamp to last line instead of raising
        self.assertEqual(self.model.lineAt(999), 4)

    def testCustomLineHeight(self):
        self.model.setLineHeight(1, 30)
        self.assertEqual(self.model.lineTop(2), 40)
        self.assertEqual(self.model.contentHeight(), 70)
        self.assertEqual(self.model.lineAt(39), 1)
        self.assertEqual(self.model.lineAt(40), 2)

    def testLineBottom(self):
        self.assertEqual(self.model.lineBottom(0), 10)
        self.assertEqual(self.model.lineBottom(4), 50)

    def testPlainFastPathMatchesExplicitHeights(self):
        # no overrides, no folds: O(1) arithmetic must equal prefix sums
        for i in range(5):
            self.assertEqual(self.model.lineTop(i), i * 10)
            self.assertEqual(self.model.lineBottom(i), (i + 1) * 10)
        self.assertEqual(self.model.contentHeight(), 50)
        self.assertEqual(self.model.lineAt(49), 4)
        self.assertEqual(self.model.lineAt(50), 4)  # clamped to last


class TestBlockModelFold(unittest.TestCase):
    def setUp(self):
        self.model = BlockModel(defaultHeight=10)
        self.model.setLineCount(10)
        # block: anchor=0, hides lines 1..4 when folded
        self.block = self.model.addBlock(0, 4)

    def testAddBlockReturnsBlock(self):
        self.assertIsInstance(self.block, Block)
        self.assertEqual(self.model.blocks(), [self.block])

    def testInitiallyExpanded(self):
        self.assertFalse(self.block.folded)
        self.assertTrue(all(self.model.isLineVisible(i)
                            for i in range(10)))
        self.assertEqual(self.model.contentHeight(), 100)

    def testFoldHidesLinesButKeepsAnchor(self):
        self.model.setFolded(self.block, True)
        self.assertTrue(self.model.isLineVisible(0))   # anchor visible
        for i in range(1, 5):
            self.assertFalse(self.model.isLineVisible(i))
        self.assertTrue(self.model.isLineVisible(5))

    def testFoldShrinksContentHeight(self):
        self.model.setFolded(self.block, True)
        # anchor 10px + hidden 4 lines * 0px + rest 5 lines * 10px
        self.assertEqual(self.model.contentHeight(), 60)
        self.assertEqual(self.model.lineTop(0), 0)
        self.assertEqual(self.model.lineTop(1), 10)  # zero-height hidden line
        self.assertEqual(self.model.lineTop(5), 10)
        # hidden lines collapse to zero height
        self.assertEqual(self.model.lineBottom(2), self.model.lineTop(2))
        self.assertEqual(self.model.lineBottom(5), 20)

    def testLineAtSkipsHiddenLinesAtPlateauEdge(self):
        # fold to the very end: lineAt must not report a hidden line
        tail = self.model.addBlock(5, 9)
        self.model.setFolded(tail, True)
        self.assertTrue(self.model.isLineHidden(9))
        self.assertEqual(self.model.lineAt(999), 5)

    def testFoldDoesNotChangeLineNumbers(self):
        self.model.setFolded(self.block, True)
        # hidden lines occupy no Y, y=15 falls into visible line 5
        self.assertEqual(self.model.lineAt(9), 0)
        self.assertEqual(self.model.lineAt(15), 5)
        self.assertEqual(self.model.lineAt(999), 9)

    def testToggleFold(self):
        self.assertIs(self.model.toggleFold(0), self.block)
        self.assertTrue(self.block.folded)
        self.assertIs(self.model.toggleFold(0), self.block)
        self.assertFalse(self.block.folded)

    def testToggleFoldOnNonAnchorLineDoesNothing(self):
        self.assertIsNone(self.model.toggleFold(3))
        self.assertFalse(self.block.folded)

    def testFoldAllAndExpandAllOnlyTopLevel(self):
        child = self.model.addBlock(6, 9, parent=self.block)
        self.model.setFolded(child, True)
        self.model.foldAll()
        self.assertTrue(self.block.folded)
        self.assertTrue(child.folded)
        # expandAll only touches top level, child stays folded
        self.model.expandAll()
        self.assertFalse(self.block.folded)
        self.assertTrue(child.folded)
        self.assertFalse(self.model.isLineVisible(7))


class TestBlockModelNestedFold(unittest.TestCase):
    def setUp(self):
        self.model = BlockModel(defaultHeight=10)
        self.model.setLineCount(10)
        self.parent = self.model.addBlock(0, 9)
        self.child = self.model.addBlock(4, 6)

    def testFoldingParentHidesChildLines(self):
        self.model.setFolded(self.parent, True)
        for i in range(1, 10):
            self.assertFalse(self.model.isLineVisible(i))

    def testChildFoldStatePreservedAcrossParentToggle(self):
        self.model.setFolded(self.child, True)
        self.model.setFolded(self.parent, True)
        self.model.setFolded(self.parent, False)
        # child still folded after parent expands
        self.assertFalse(self.model.isLineVisible(5))
        self.assertTrue(self.model.isLineVisible(7))

    def testNestedFoldHeights(self):
        self.model.setFolded(self.child, True)
        # anchor line 4 stays visible, only 5..6 hidden => 2 * 10px
        self.assertEqual(self.model.contentHeight(), 100 - 20)


class TestBlockModelClear(unittest.TestCase):
    def testClearResetsBlocksAndHeights(self):
        model = BlockModel(defaultHeight=10)
        model.setLineCount(4)
        model.addBlock(0, 3)
        model.foldAll()
        model.clear()
        self.assertEqual(model.blocks(), [])
        model.setLineCount(4)
        self.assertEqual(model.contentHeight(), 40)
        self.assertTrue(all(model.isLineVisible(i) for i in range(4)))


class TestBlockModelInsertion(unittest.TestCase):
    """insertLines(at, count) splices `count` lines in before line `at`,
    so everything from that point on moves down."""

    def setUp(self):
        self.model = BlockModel(defaultHeight=10)
        self.model.setLineCount(6)

    def testInsertAfterABlockKeepsItInPlace(self):
        block = self.model.addBlock(0, 2)
        self.model.insertLines(4, 2)

        self.assertEqual((0, 2), (block.startLine, block.endLine))
        self.assertEqual(8, self.model.lineCount())
        self.assertEqual(80, self.model.contentHeight())

    def testInsertBeforeABlockShiftsIt(self):
        block = self.model.addBlock(2, 4)
        self.model.insertLines(2, 3)

        self.assertEqual((5, 7), (block.startLine, block.endLine))
        self.assertEqual(9, self.model.lineCount())
        self.assertEqual(90, self.model.contentHeight())

    def testInsertInsideABlockExtendsIt(self):
        block = self.model.addBlock(0, 5)
        self.model.insertLines(3, 2)

        self.assertEqual((0, 7), (block.startLine, block.endLine))
        self.assertEqual(8, self.model.lineCount())

    def testInsertBeforeAFoldedBlockShiftsAnchorAndGeometry(self):
        block = self.model.addBlock(3, 5)
        self.model.setFolded(block, True)
        self.model.insertLines(1, 4)

        self.assertEqual((7, 9), (block.startLine, block.endLine))
        self.assertEqual(self.model.lineTop(7), 70)
        self.assertEqual(self.model.lineHeight(8), 0)
        # anchor plus the 7 lines before it
        self.assertEqual(self.model.contentHeight(), 80)
        self.assertEqual(self.model.lineAt(80), 7)

    def testInsertShiftsHeightOverrides(self):
        self.model.setLineHeight(4, 30)
        self.model.insertLines(1, 2)

        self.assertEqual(8, self.model.lineCount())
        self.assertEqual(10, self.model.lineHeight(4))
        self.assertEqual(30, self.model.lineHeight(6))
        self.assertEqual(60, self.model.lineTop(6))
        self.assertEqual(100, self.model.contentHeight())

    def testInsertAtTheEndAppends(self):
        block = self.model.addBlock(0, 2)
        self.model.insertLines(6, 2)

        self.assertEqual((0, 2), (block.startLine, block.endLine))
        self.assertEqual(8, self.model.lineCount())
        # out-of-range insertion points clamp to the end
        self.model.insertLines(99, 1)
        self.assertEqual(9, self.model.lineCount())
        self.assertEqual(90, self.model.contentHeight())

    def testNothingIsInsertedForAnEmptyRange(self):
        self.model.insertLines(2, 0)
        self.model.insertLines(2, -1)
        self.assertEqual(6, self.model.lineCount())
