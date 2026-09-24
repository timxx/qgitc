# -*- coding: utf-8 -*-
import gc

from qgitc.diffutils import DiffType
from qgitc.patchviewer import PatchViewer
from qgitc.textline import TextLine
from tests.base import TestBase


class TestCopyPlainText(TestBase):
    def doCreateRepo(self):
        pass

    def _makeViewer(self, texts):
        """Create a PatchViewer with the given raw diff text lines loaded."""
        viewer = PatchViewer()
        font = viewer.font()
        for text in texts:
            viewer.appendTextLine(TextLine(text, font))
        return viewer

    def _copyWithCursor(self, viewer, beginLine, beginPos, endLine, endPos):
        """Select via cursor positions, invoke copyPlainText, return clipboard text."""
        viewer._cursor.moveTo(beginLine, beginPos)
        viewer._cursor.selectTo(endLine, endPos)
        viewer.copyPlainText()
        return self.app.clipboard().text()

    def testNoExtraTrailingNewlineSelectAll(self):
        """selectAll() copy must not produce an extra trailing newline.
        selectedText() returns text without a trailing '\\n', so neither should
        the copied result."""
        viewer = self._makeViewer(["+foo", " bar", "-baz"])
        viewer.selectAll()
        viewer.copyPlainText()
        result = self.app.clipboard().text()
        del viewer
        gc.collect()
        self.assertEqual(result, "foo\nbar\nbaz")

    def testExtraNewlineWhenSelectionEndsAtLineStart(self):
        """Regression: selecting to position 0 of a following line must not
        produce a double trailing newline in the copied text."""
        viewer = self._makeViewer(["+foo", " bar"])
        result = self._copyWithCursor(viewer, 0, 0, 1, 0)
        del viewer
        gc.collect()
        self.assertEqual(result, "foo\n")

    def testSingleLine(self):
        """Copying a single diff line strips the prefix without adding extra newline."""
        viewer = self._makeViewer(["+hello"])
        result = self._copyWithCursor(viewer, 0, 0, 0, len("+hello"))
        del viewer
        gc.collect()
        self.assertEqual(result, "hello")

    def testContextLine(self):
        """Space-prefixed context lines have their prefix stripped."""
        viewer = self._makeViewer([" context"])
        result = self._copyWithCursor(viewer, 0, 0, 0, len(" context"))
        del viewer
        gc.collect()
        self.assertEqual(result, "context")

    def testRemovedLine(self):
        """Minus-prefixed removed lines have their prefix stripped."""
        viewer = self._makeViewer(["-removed"])
        result = self._copyWithCursor(viewer, 0, 0, 0, len("-removed"))
        del viewer
        gc.collect()
        self.assertEqual(result, "removed")

    def testNonDiffLine(self):
        """Lines without a diff prefix (e.g. hunk headers) are copied as-is."""
        viewer = self._makeViewer(["@@ -1,3 +1,3 @@"])
        result = self._copyWithCursor(viewer, 0, 0, 0, len("@@ -1,3 +1,3 @@"))
        del viewer
        gc.collect()
        self.assertEqual(result, "@@ -1,3 +1,3 @@")

    def testMixedLines(self):
        """Mixed diff and non-diff lines are handled correctly."""
        viewer = self._makeViewer(["@@ -1,2 +1,2 @@", "-old", "+new"])
        viewer.selectAll()
        viewer.copyPlainText()
        result = self.app.clipboard().text()
        del viewer
        gc.collect()
        self.assertEqual(result, "@@ -1,2 +1,2 @@\nold\nnew")


class TestCurrentFileRow(TestBase):
    """currentFileRow/fileRowChanged must resolve from the top visible
    logical line, never from the pixel scrollbar value."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.viewer = PatchViewer()
        self.viewer.resize(300, 200)
        self.viewer.show()
        self.processEvents()

        self.viewer.addAuthorLine("Author: foo <foo@example.com>")
        self.viewer.addNormalTextLine("", False)
        lineItems = [(DiffType.File, b"a.txt")]
        lineItems += [(DiffType.Diff, b"+a%02d" % i) for i in range(40)]
        lineItems.append((DiffType.File, b"b.txt"))
        lineItems.append((DiffType.Diff, b"+b1"))
        self.viewer.appendLines(lineItems)
        self.processEvents()
        self.lineH = self.viewer.lineHeight
        # a.txt: marker at line 2, body 3..42; b.txt: marker at 43

    def testCurrentFileRowUsesTopVisibleLine(self):
        # scroll into a.txt's body; the wrapped author line makes pixel
        # positions diverge from lineNo * lineHeight, so ask the model
        self.viewer.verticalScrollBar().setValue(
            self.viewer._blockModel.lineTop(6))
        self.assertEqual(self.viewer.firstVisibleLine(), 6)
        self.assertEqual(self.viewer.currentFileRow(), 2)

    def testFileRowChangedFollowsPixelScroll(self):
        rows = []
        self.viewer.verticalScrollBar().setValue(
            self.viewer._blockModel.lineTop(6))
        self.viewer.fileRowChanged.connect(rows.append)
        self.viewer._onVScollBarValueChanged(
            self.viewer.verticalScrollBar().value())
        self.assertEqual(rows, [2])

    def testCurrentFileRowAtCommentsTop(self):
        self.viewer.verticalScrollBar().setValue(0)
        self.assertEqual(self.viewer.currentFileRow(), 0)


class TestCommentsWrap(TestBase):
    """Comments-region lines opt into word wrap; diff content stays
    unwrapped so horizontal scrolling keeps diffs byte-faithful."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.viewer = PatchViewer()
        self.viewer.resize(300, 200)
        self.viewer.show()
        self.processEvents()
        self.longText = " ".join("word%02d" % i for i in range(60))

    def testCommentLinesOptIntoWrap(self):
        self.viewer.addAuthorLine("Author: " + self.longText)
        self.viewer.addSHA1Line("Commit: " + self.longText, False)
        self.viewer.addNormalTextLine("", False)
        self.viewer.addSummaryTextLine(self.longText)
        self.processEvents()

        for i in range(4):
            line = self.viewer.textLineAt(i)
            self.assertTrue(line.wrap(), "line %d should wrap" % i)
            self.assertEqual(line.wrapWidth(), self.viewer.wrapWidth())

    def testSummaryLineWrapsIntoMultipleRows(self):
        self.viewer.addSummaryTextLine(self.longText)
        self.processEvents()

        line = self.viewer.textLineAt(0)
        self.assertGreater(line.visualLineCount(), 1)
        self.assertEqual(
            self.viewer._blockModel.lineHeight(0),
            line.visualLineCount() * self.viewer.lineHeight)

    def testDiffLinesDoNotWrap(self):
        self.viewer.appendLines([
            (DiffType.File, b"a.txt"),
            (DiffType.FileInfo, b"index 9122d00..da719d5 100644"),
            (DiffType.Diff, b"@@ -1 +1 @@" + b"x" * 400),
            (DiffType.Diff, ("+" + self.longText).encode()),
        ])
        self.processEvents()

        for i in range(4):
            line = self.viewer.textLineAt(i)
            self.assertFalse(line.wrap(), "diff line %d must not wrap" % i)
            self.assertEqual(line.visualLineCount(), 1)

    def testContextMenuUpdatesBaseEntries(self):
        # the base class owns copy/fold entry state; the subclass must
        # not swallow it
        menu = self.viewer.contextMenu
        self.viewer._contextLine = 0
        self.viewer.updateContextMenu(None)
        self.assertFalse(self.viewer._acCopy.isEnabled())
        self.assertFalse(self.viewer._acFoldBlock.isVisible())


class TestFileBlocks(TestBase):
    """Each file section is registered as one foldable block anchored on
    its DiffType.File marker, so a whole file's diff folds away while the
    marker line stays visible."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.viewer = PatchViewer()
        self.viewer.resize(400, 300)
        self.viewer.show()
        self.processEvents()
        self.lineH = self.viewer.lineHeight

    def appendTwoFiles(self):
        """a.txt: marker line 0, section 0..3; b.txt: marker 4, 4..5."""
        self.viewer.beginReading()
        self.viewer.appendLines([
            (DiffType.File, b"a.txt"),
            (DiffType.FileInfo, b"index 9122d00..da719d5 100644"),
            (DiffType.Diff, b"@@ -1 +1 @@"),
            (DiffType.Diff, b"+a1"),
        ])
        # a continuation chunk carries the next file's marker
        self.viewer.appendLines([
            (DiffType.File, b"b.txt"),
            (DiffType.Diff, b"+b1"),
        ])
        self.processEvents()

    def blocks(self):
        return self.viewer._blockModel.blocks()

    def testSectionStaysOpenUntilTheStreamEnds(self):
        self.appendTwoFiles()

        # a.txt was closed by b.txt's marker, b.txt is still being read
        self.assertEqual(1, len(self.blocks()))
        self.assertEqual((0, 3), (
            self.blocks()[0].startLine, self.blocks()[0].endLine))

        self.viewer.endReading()
        self.assertEqual(2, len(self.blocks()))

    def testEveryFileSectionRegistersOneBlock(self):
        self.appendTwoFiles()
        self.viewer.endReading()

        blocks = self.blocks()
        self.assertEqual((0, 3), (blocks[0].startLine, blocks[0].endLine))
        self.assertEqual((4, 5), (blocks[1].startLine, blocks[1].endLine))
        self.assertEqual("a.txt", blocks[0].meta["path"])
        self.assertEqual("b.txt", blocks[1].meta["path"])

    def testContinuationChunkDoesNotStartANewBlock(self):
        self.appendTwoFiles()
        self.viewer.appendLines([(DiffType.Diff, b"+b2")])
        self.viewer.endReading()

        blocks = self.blocks()
        self.assertEqual(2, len(blocks))
        self.assertEqual(4, blocks[1].startLine)
        self.assertEqual(6, blocks[1].endLine)

    def testFoldHidesSectionBodyButKeepsMarker(self):
        self.appendTwoFiles()
        self.viewer.endReading()

        self.viewer.toggleFoldAt(0)
        self.assertTrue(self.viewer._blockModel.isLineVisible(0))
        for lineNo in (1, 2, 3):
            self.assertFalse(
                self.viewer._blockModel.isLineVisible(lineNo),
                "line %d belongs to the folded section" % lineNo)
        # the next file is untouched
        self.assertTrue(self.viewer._blockModel.isLineVisible(4))
        self.assertEqual(3 * self.lineH,
                         self.viewer._blockModel.contentHeight())

    def testOnlyFileMarkersAreFoldAnchors(self):
        self.appendTwoFiles()
        self.viewer.endReading()

        self.assertTrue(self.viewer.canFoldAt(0))
        self.assertTrue(self.viewer.canFoldAt(4))
        for lineNo in (1, 2, 3, 5):
            self.assertFalse(self.viewer.canFoldAt(lineNo))

    def testFoldTipNamesTheFile(self):
        self.appendTwoFiles()
        self.viewer.endReading()

        tip = self.viewer.foldTipForLine(0)
        self.assertIn("a.txt", tip)
        self.assertIn("3", tip)  # lines 1..3 hidden

        self.viewer.toggleFoldAt(0)
        self.assertIn("a.txt", self.viewer.foldTipForLine(0))
