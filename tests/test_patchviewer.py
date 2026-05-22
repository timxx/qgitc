# -*- coding: utf-8 -*-
import gc

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
