# -*- coding: utf-8 -*-
"""Unit tests for DiffView's incremental per-file diff accumulation."""

from qgitc.applicationbase import ApplicationBase
from qgitc.diffutils import DiffType, FileInfo, FileState
from qgitc.diffview import DiffView
from tests.base import TestBase


class TestDiffViewChunkedDiff(TestBase):
    """With sorting off, each buffered block is rendered as it arrives, so a
    file's diff shows up while git is still producing output. A block that
    spans several parse() chunks (QProcess delivers stdout in multiple
    readyRead chunks) must not be dropped."""

    def doCreateRepo(self):
        """No repo needed for these unit-level tests."""
        pass

    def setUp(self):
        super().setUp()
        self._view = DiffView()
        # Mirror _doShowCommit, which captures the setting when the fetch starts
        self._view._sortByFile = \
            ApplicationBase.instance().settings().sortDiffByFile()

    def tearDown(self):
        self._view.deleteLater()
        self.processEvents()
        super().tearDown()

    def _emitChunk(self, lineItems, fileItems):
        self._view._DiffView__onDiffAvailable(lineItems, fileItems)

    def _renderedFiles(self):
        return [f for f, _ in self._view.fileListModel._fileList]

    def testBlockRenderedAsSoonAsItArrives(self):
        """The block is rendered on arrival — no waiting for the next file's
        marker nor for the fetch to finish."""
        self._emitChunk(
            [(DiffType.File, b"a.txt"),
             (DiffType.FileInfo, b"index 9122d00..da719d5 100644"),
             (DiffType.Diff, b"@@ -1 +1 @@"),
             (DiffType.Diff, b"+first")],
            {"a.txt": FileInfo(3)})

        self.assertEqual(["a.txt"], self._renderedFiles())
        self.assertEqual(4, self._view.viewer.textLineCount())
        self.assertEqual({}, self._view._pendingDiffs)

    def testMultipleChunksRenderedIncrementally(self):
        """Each readyRead chunk appends to the viewer as it is parsed."""
        self._emitChunk(
            [(DiffType.File, b"a.txt"),
             (DiffType.Diff, b"+first")],
            {"a.txt": FileInfo(1)})
        self.assertEqual(2, self._view.viewer.textLineCount())

        # Continuation chunk of the same file plus the next file's marker
        self._emitChunk(
            [(DiffType.Diff, b"+second"),
             (DiffType.File, b"b.txt"),
             (DiffType.Diff, b"+third")],
            {"b.txt": FileInfo(3)})

        self.assertEqual(["a.txt", "b.txt"], self._renderedFiles())
        self.assertEqual(5, self._view.viewer.textLineCount(),
                         "no line may be dropped or duplicated")

    def testRowNumbersMatchViewerLines(self):
        """Each file's row is the viewer line of its DiffType.File marker."""
        self._emitChunk(
            [(DiffType.File, b"a.txt"),
             (DiffType.Diff, b"+a1"),
             (DiffType.Diff, b"+a2")],
            {"a.txt": FileInfo(0)})
        self._emitChunk(
            [(DiffType.File, b"b.txt"),
             (DiffType.Diff, b"+b1")],
            {"b.txt": FileInfo(3)})

        rows = {f: info.row
                for f, info in self._view.fileListModel._fileList}
        self.assertEqual({"a.txt": 0, "b.txt": 3}, rows)
        # a.txt: marker + 2 lines, b.txt: marker + 1 line
        self.assertEqual(5, self._view.viewer.textLineCount())

    def testStateUpdateReachesRenderedFile(self):
        """State lines arrive right after a file's marker, i.e. after the block
        has been rendered, so the file list entry picks the state up."""
        info = FileInfo(0)
        self._emitChunk(
            [(DiffType.File, b"new.txt"),
             (DiffType.Diff, b"+content")],
            {"new.txt": info})
        self._view._DiffView__onDiffFileStateChanged("new.txt", FileState.Added)

        self.assertEqual(FileState.Added, info.state)
        self.assertEqual(FileState.Added,
                         self._view.fileListModel._fileList[0][1].state)

    def testClearResetsSplitState(self):
        self._emitChunk(
            [(DiffType.File, b"a.txt"),
             (DiffType.Diff, b"+x")],
            {"a.txt": FileInfo(1)})

        self._view.clear()

        self.assertIsNone(self._view._splitFile)
        self.assertIsNone(self._view._splitInfo)
        self.assertEqual([], self._view._splitLines)
        self.assertEqual({}, self._view._pendingDiffs)
        self.assertFalse(self._view._sortByFile)


class TestDiffViewSortedMode(TestBase):
    """With 'sort files by name' on, the sorted order is unknown until every
    file has been read, so blocks are buffered and rendered on completion."""

    def doCreateRepo(self):
        """No repo needed for these unit-level tests."""
        pass

    def setUp(self):
        super().setUp()
        self._view = DiffView()
        self._view._sortByFile = True

    def tearDown(self):
        self._view.deleteLater()
        self.processEvents()
        super().tearDown()

    def _emitChunk(self, lineItems, fileItems):
        self._view._DiffView__onDiffAvailable(lineItems, fileItems)

    def _renderedFiles(self):
        return [f for f, _ in self._view.fileListModel._fileList]

    def testFileDiffSpanningChunks(self):
        """Continuation chunks (no DiffType.File marker) must not be dropped."""
        # Chunk 1: the file marker, its info line and the first hunk lines.
        self._emitChunk(
            [(DiffType.File, b"include/shell/et.h"),
             (DiffType.FileInfo, b"index 9122d00ef..da719d5f5 100644"),
             (DiffType.Diff, b"@@ -2122,6 +2122,39 @@ struct ShellEtFindOptions"),
             (DiffType.Diff, b"+struct ShellEtFindResult")],
            {"include/shell/et.h": FileInfo(3)})

        # Chunk 2: continuation of the same file's diff — no file marker.
        self._emitChunk(
            [(DiffType.Diff, b"+{"),
             (DiffType.Diff, b"+       std::u16string searchText;"),
             (DiffType.Diff, b"+};")],
            {})

        self._view._flushSplitFile()

        self.assertIn("include/shell/et.h", self._view._pendingDiffs)
        lineItems, _ = self._view._pendingDiffs["include/shell/et.h"]
        # marker + info + hunk header + 4 content lines = 7
        self.assertEqual(7, len(lineItems),
                         "all lines from both chunks must be kept")

    def testNextFileMarkerBuffersPrevious(self):
        """A new file marker must buffer the accumulated previous file."""
        self._emitChunk(
            [(DiffType.File, b"a.txt"),
             (DiffType.Diff, b"+first")],
            {"a.txt": FileInfo(1)})

        self.assertEqual([], self._renderedFiles(),
                         "nothing may be rendered before the sort is possible")

        self._emitChunk(
            [(DiffType.Diff, b"+second"),
             (DiffType.File, b"b.txt"),
             (DiffType.Diff, b"+other")],
            {"b.txt": FileInfo(3)})

        self.assertIn("a.txt", self._view._pendingDiffs)
        lineItems, _ = self._view._pendingDiffs["a.txt"]
        self.assertEqual(3, len(lineItems),
                         "a.txt must carry its marker line and both diff lines")
        self.assertEqual([b"+first", b"+second"],
                         [d for t, d in lineItems if t == DiffType.Diff])

        # b.txt is still being split (no following marker yet)
        self.assertNotIn("b.txt", self._view._pendingDiffs)
        self.assertEqual("b.txt", self._view._splitFile)

    def testBufferedThenRenderedSorted(self):
        self._emitChunk(
            [(DiffType.File, b"zebra.txt"),
             (DiffType.Diff, b"+z")],
            {"zebra.txt": FileInfo(0)})
        self._emitChunk(
            [(DiffType.File, b"alpha.txt"),
             (DiffType.Diff, b"+a")],
            {"alpha.txt": FileInfo(2)})

        self.assertEqual([], self._renderedFiles())

        self._view._flushPendingDiffs()

        self.assertEqual(["alpha.txt", "zebra.txt"], self._renderedFiles())
        self.assertEqual(0, self._view.fileListModel._fileList[0][1].row)
        self.assertEqual(2, self._view.fileListModel._fileList[1][1].row)

    def testStateUpdateAppliedToPendingFile(self):
        """fileStateChanged for the file being split must update its
        pending FileInfo (state lines arrive right after the marker, while
        the file is still being split and thus not in the list yet)."""
        info = FileInfo(1)
        self._emitChunk(
            [(DiffType.File, b"new.txt"),
             (DiffType.Diff, b"+content")],
            {"new.txt": info})

        self._view._DiffView__onDiffFileStateChanged("new.txt", FileState.Added)

        self.assertEqual(FileState.Added, info.state)

        self._view._flushPendingDiffs()
        self.assertEqual(FileState.Added,
                         self._view.fileListModel._fileList[0][1].state)


class TestDiffViewFileOrder(TestBase):
    """File order in the diff view follows the sortDiffByFile setting."""

    def doCreateRepo(self):
        """No repo needed for these unit-level tests."""
        pass

    def setUp(self):
        super().setUp()
        self._view = DiffView()
        # Mirror _doShowCommit, which captures the setting when the fetch starts
        self._view._sortByFile = \
            ApplicationBase.instance().settings().sortDiffByFile()

    def tearDown(self):
        self._view.deleteLater()
        self.processEvents()
        super().tearDown()

    def _addFiles(self, *names):
        """Feed one file's block per name, in the given (git output) order."""
        for i, name in enumerate(names):
            self._view._DiffView__onDiffAvailable(
                [(DiffType.File, name.encode()),
                 (DiffType.Diff, b"+content")],
                {name: FileInfo(i)})

    def _renderedFileOrder(self):
        return [f for f, _ in self._view.fileListModel._fileList]

    def testDefaultIsUnsorted(self):
        """The setting defaults to off: keep the git output order."""
        settings = ApplicationBase.instance().settings()
        self.assertFalse(settings.sortDiffByFile())

        self._addFiles("zebra.txt", "alpha.txt", "mid.txt")
        self.assertEqual(["zebra.txt", "alpha.txt", "mid.txt"],
                         self._renderedFileOrder())

    def testSortedWhenEnabled(self):
        settings = ApplicationBase.instance().settings()
        settings.setSortDiffByFile(True)
        try:
            self._view._sortByFile = True
            self._addFiles("zebra.txt", "alpha.txt", "mid.txt")
            self.assertEqual([], self._renderedFileOrder())
            self._view._flushPendingDiffs()
            self.assertEqual(["alpha.txt", "mid.txt", "zebra.txt"],
                             self._renderedFileOrder())
        finally:
            settings.setSortDiffByFile(False)

    def testRenderedBeforeFetchCompletesWhenUnsorted(self):
        """With sorting off each block is rendered as soon as it arrives,
        instead of waiting for the whole commit."""
        self._addFiles("a.txt")

        self.assertEqual(["a.txt"], self._renderedFileOrder())
        self.assertEqual(2, self._view.viewer.textLineCount())
