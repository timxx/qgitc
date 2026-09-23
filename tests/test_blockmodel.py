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
