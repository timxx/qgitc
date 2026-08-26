# -*- coding: utf-8 -*-
"""Unit tests for LogView's composite-mode incremental merge."""

from datetime import datetime, timedelta

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from qgitc.common import Commit
from qgitc.gitutils import Git
from qgitc.logview import LogView
from tests.base import TestBase


class TestLogViewCompositeMerge(TestBase):

    def doCreateRepo(self):
        """No repo needed for these unit-level tests."""
        pass

    def setUp(self):
        super().setUp()
        self._logView = LogView()
        self._logView.resize(400, 120)
        # pretend we are in composite mode without wiring up submodules
        self._logView._isCompositeMode = lambda: True
        self._now = datetime.now()

    def tearDown(self):
        self._logView.deleteLater()
        self.processEvents()
        super().tearDown()

    def _commit(self, name, minutesAgo):
        commit = Commit()
        commit.sha1 = name * 40
        commit.comments = "commit " + name
        commit.author = "author"
        commit.repoDir = "repo"
        commit.committerDateTime = self._now - timedelta(minutes=minutesAgo)
        return commit

    def _localCommit(self, sha1):
        commit = Commit()
        commit.sha1 = sha1
        commit.comments = "local"
        return commit

    def _emit(self, commits):
        """Simulate the worker thread: merge into _allLogs and emit tuple."""
        if not hasattr(self, '_allLogs'):
            self._allLogs = []
        if not self._allLogs:
            # First batch: emit as plain list
            self._allLogs = list(commits)
            self._logView._LogView__onLogsAvailable(commits)
        else:
            # Subsequent batches: merge and emit (allLogs, insertPositions)
            batch = sorted(commits, key=lambda c: c.committerDateTime, reverse=True)
            old = self._allLogs
            oldCount = len(old)
            insertPositions = []
            merged = []
            i = 0
            j = 0
            newCount = len(batch)
            runStart = i
            while i < oldCount and j < newCount:
                if batch[j].committerDateTime > old[i].committerDateTime:
                    if i > runStart:
                        merged.extend(old[runStart:i])
                    insertPositions.append(i)
                    merged.append(batch[j])
                    j += 1
                    runStart = i
                else:
                    i += 1
            if i > runStart:
                merged.extend(old[runStart:i])
            while j < newCount:
                insertPositions.append(i)
                merged.append(batch[j])
                j += 1
            if i < oldCount:
                merged.extend(old[i:])
            self._allLogs = merged
            self._logView._LogView__onLogsAvailable((merged, insertPositions))

    def _finishFetch(self):
        self._logView._LogView__onFetchFinished(0)

    # ------------------------------------------------------------------
    #  Merge ordering
    # ------------------------------------------------------------------
    def testFirstBatchPopulatesData(self):
        c1 = self._commit("a", 0)
        c2 = self._commit("b", 10)
        self._emit([c1, c2])

        self.assertEqual([c1, c2], self._logView.data)

    def testLogViewOwnsItsList(self):
        """The view must not alias the worker's batch, clear() would corrupt it."""
        batch = [self._commit("a", 0)]
        self._emit(batch)

        self.assertIsNot(batch, self._logView.data)

    def testSecondBatchMergesInOrder(self):
        c1 = self._commit("a", 10)
        c2 = self._commit("b", 30)
        self._emit([c1, c2])

        c3 = self._commit("c", 0)
        c4 = self._commit("d", 20)
        c5 = self._commit("e", 40)
        self._emit([c3, c4, c5])

        self.assertEqual([c3, c1, c4, c2, c5], self._logView.data)

    def testMergeKeepsExistingCommitObjects(self):
        c1 = self._commit("a", 10)
        self._emit([c1])
        self._emit([self._commit("c", 0)])

        self.assertIs(c1, self._logView.data[1])

    def testEqualTimestampsKeepExistingRowFirst(self):
        c1 = self._commit("a", 10)
        self._emit([c1])

        tie = self._commit("b", 10)
        self._emit([tie])

        self.assertEqual([c1, tie], self._logView.data)

    def testManyBatchesStayOrdered(self):
        import random
        expected = 0
        for _ in range(30):
            batch = [self._commit("a", random.randint(0, 5000))
                     for _ in range(20)]
            batch.sort(key=lambda c: c.committerDateTime, reverse=True)
            self._emit(batch)
            expected += len(batch)

        data = self._logView.data
        self.assertEqual(expected, len(data))
        for i in range(len(data) - 1):
            self.assertGreaterEqual(data[i].committerDateTime,
                                    data[i + 1].committerDateTime)

    def testMergeBatchWithDuplicateTimestamps(self):
        """A batch containing ties must interleave correctly with old rows."""
        # minutesAgo: larger = older
        old = [self._commit("a", 10), self._commit("b", 20), self._commit("c", 30)]
        self._emit(old)

        # ties with existing rows at 10 and 30, plus newer and older rows;
        # batches arrive newest-first (sorted by the worker)
        batch = [self._commit("d", 5), self._commit("e", 10),
                 self._commit("f", 30), self._commit("g", 40)]
        self._emit(batch)

        # ties keep the existing row first
        self.assertEqual(
            ["d", "a", "e", "b", "c", "f", "g"],
            [c.sha1[0] for c in self._logView.data])

    def testMergeAllNewOlderThanExisting(self):
        """A fully-older batch appends at the end."""
        self._emit([self._commit("a", 5), self._commit("b", 10)])
        self._emit([self._commit("c", 30), self._commit("d", 40)])

        self.assertEqual(
            ["a", "b", "c", "d"],
            [c.sha1[0] for c in self._logView.data])

    def testMergeAllNewNewerThanExisting(self):
        """A fully-newer batch prepends at the front."""
        self._emit([self._commit("c", 30), self._commit("d", 40)])
        # newest-first batch
        self._emit([self._commit("a", 5), self._commit("b", 10)])

        self.assertEqual(
            ["a", "b", "c", "d"],
            [c.sha1[0] for c in self._logView.data])

    def testEmptyBatchIsIgnored(self):
        c1 = self._commit("a", 0)
        self._emit([c1])
        self._emit([])

        self.assertEqual([c1], self._logView.data)

    # ------------------------------------------------------------------
    #  Selection remapping
    # ------------------------------------------------------------------
    def testSelectionFollowsCommitWhenNewerArrives(self):
        c1 = self._commit("a", 10)
        c2 = self._commit("b", 20)
        self._emit([c1, c2])

        self._logView.setCurrentIndex(1)
        self.assertIs(c2, self._logView.data[1])

        # two newer commits land above the selection
        self._emit([self._commit("c", 0), self._commit("d", 5)])

        self.assertEqual(3, self._logView.currentIndex())
        self.assertIs(c2, self._logView.data[self._logView.currentIndex()])
        self.assertEqual([3], self._logView.getSelectedIndices())

    def testSelectionUnchangedWhenOlderArrives(self):
        c1 = self._commit("a", 10)
        c2 = self._commit("b", 20)
        self._emit([c1, c2])
        self._logView.setCurrentIndex(0)

        self._emit([self._commit("c", 30), self._commit("d", 40)])

        self.assertEqual(0, self._logView.currentIndex())
        self.assertIs(c1, self._logView.data[0])

    def testMultiSelectionRemapped(self):
        commits = [self._commit(n, i * 10)
                   for i, n in enumerate(["a", "b", "c"])]
        self._emit(commits)

        self._logView.setCurrentIndex(0)
        self._logView.selectedIndices = {0, 2}

        self._emit([self._commit("d", 5)])

        self.assertEqual([0, 3], self._logView.getSelectedIndices())
        self.assertIs(commits[0], self._logView.data[0])
        self.assertIs(commits[2], self._logView.data[3])

    def testAutoSelectFirstOnFirstBatch(self):
        c1 = self._commit("a", 0)
        self._emit([c1])
        self.assertEqual(0, self._logView.currentIndex())

    def testPreferSha1SelectedOnFirstBatch(self):
        c1 = self._commit("a", 0)
        c2 = self._commit("b", 10)
        self._logView.preferSha1 = c2.sha1
        self._emit([c1, c2])

        self.assertEqual(1, self._logView.currentIndex())

    # ------------------------------------------------------------------
    #  The auto selection is provisional until the fetch ends
    # ------------------------------------------------------------------
    def testAutoSelectionMovesToNewestRowOnFetchFinished(self):
        self._emit([self._commit("a", 10)])
        self.assertEqual(0, self._logView.currentIndex())

        newest = self._commit("b", 0)
        self._emit([newest])
        self.assertEqual(1, self._logView.currentIndex())

        self._finishFetch()

        self.assertEqual(0, self._logView.currentIndex())
        self.assertIs(newest, self._logView.data[0])
        self.assertEqual([0], self._logView.getSelectedIndices())

    def testNewestRowNotReselectedWhenAlreadyCurrent(self):
        self._emit([self._commit("a", 0)])

        emitted = []
        self._logView.currentIndexChanged.connect(emitted.append)
        self._finishFetch()

        self.assertEqual([], emitted)

    def testClickedRowKeptOnFetchFinished(self):
        c1 = self._commit("a", 10)
        c2 = self._commit("b", 20)
        self._emit([c1, c2])

        self._logView.setCurrentIndex(1)
        self._emit([self._commit("c", 0)])
        self._finishFetch()

        self.assertIs(c2, self._logView.data[self._logView.currentIndex()])

    def testClickedNewestRowKeptOnFetchFinished(self):
        """Clicking the row we auto selected must make the selection the user's."""
        c1 = self._commit("a", 10)
        self._emit([c1])

        self._logView.setCurrentIndex(0)
        self._emit([self._commit("b", 0)])
        self._finishFetch()

        self.assertIs(c1, self._logView.data[self._logView.currentIndex()])

    def testKeyboardSelectionKeptOnFetchFinished(self):
        c1 = self._commit("a", 10)
        c2 = self._commit("b", 20)
        self._emit([c1, c2])
        self.assertEqual(0, self._logView.currentIndex())

        self._logView.keyPressEvent(
            QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
        self.assertIs(c2, self._logView.data[self._logView.currentIndex()])

        self._emit([self._commit("c", 0)])
        self._finishFetch()

        self.assertIs(c2, self._logView.data[self._logView.currentIndex()])

    def testPreferSha1RowKeptOnFetchFinished(self):
        c1 = self._commit("a", 10)
        c2 = self._commit("b", 20)
        self._logView.preferSha1 = c2.sha1
        self._emit([c1, c2])

        self._emit([self._commit("c", 0)])
        self._finishFetch()

        self.assertIs(c2, self._logView.data[self._logView.currentIndex()])

    def testPreferSha1WinsOverAutoSelection(self):
        self._emit([self._commit("a", 10)])
        self.assertEqual(0, self._logView.currentIndex())

        wanted = self._commit("b", 20)
        self._logView.switchToCommit(wanted.sha1, delay=True)
        self._emit([wanted])
        self.assertIs(wanted, self._logView.data[self._logView.currentIndex()])

        self._finishFetch()

        self.assertIs(wanted, self._logView.data[self._logView.currentIndex()])

    def testEmptyNormalBatchSelectsNothing(self):
        """A parse that yielded no commit must not select a row that isn't there."""
        self._logView._isCompositeMode = lambda: False
        self._emit([])

        self.assertEqual(-1, self._logView.currentIndex())

    # ------------------------------------------------------------------
    #  Local change rows stay pinned on top
    # ------------------------------------------------------------------
    def testLocalChangeRowsStayOnTop(self):
        c1 = self._commit("a", 10)
        self._emit([c1])

        luc = self._localCommit(Git.LUC_SHA1)
        self._logView.data.insert(0, luc)

        newest = self._commit("c", 0)
        self._emit([newest])

        self.assertEqual([luc, newest, c1], self._logView.data)

    # ------------------------------------------------------------------
    #  Scroll anchoring
    # ------------------------------------------------------------------
    def testScrollAnchorFollowsTopCommit(self):
        commits = [self._commit(chr(ord('a') + i % 26), i * 10)
                   for i in range(100)]
        self._emit(commits)

        scrollBar = self._logView.verticalScrollBar()
        self.assertGreater(scrollBar.maximum(), 10,
                           "viewport too tall for this test")
        scrollBar.setValue(10)
        topCommit = self._logView.data[10]

        # three newer commits land above everything
        self._emit([self._commit("x", 0), self._commit("y", 1),
                    self._commit("z", 2)])

        self.assertEqual(13, scrollBar.value())
        self.assertIs(topCommit, self._logView.data[13])

    def testScrollStaysAtTopWhenNotScrolled(self):
        commits = [self._commit(chr(ord('a') + i % 26), (i + 1) * 10)
                   for i in range(100)]
        self._emit(commits)
        self._logView.verticalScrollBar().setValue(0)

        self._emit([self._commit("x", 0)])

        self.assertEqual(0, self._logView.verticalScrollBar().value())

    # ------------------------------------------------------------------
    #  Diff refresh once the selected row is fully merged
    # ------------------------------------------------------------------
    def testDiffRefreshedWhenSelectedRowGainedSubCommits(self):
        c1 = self._commit("a", 0)
        self._emit([c1])
        self.assertEqual(0, self._logView.currentIndex())

        emitted = []
        self._logView.currentIndexChanged.connect(emitted.append)

        # a later repo merged into the selected row
        c1.subCommits.append(self._commit("b", 0))
        self._logView._LogView__onFetchFinished(0)

        self.assertEqual([0], emitted)

    def testDiffNotRefreshedWhenSelectedRowUnchanged(self):
        c1 = self._commit("a", 0)
        self._emit([c1])

        emitted = []
        self._logView.currentIndexChanged.connect(emitted.append)
        self._logView._LogView__onFetchFinished(0)

        self.assertEqual([], emitted)

    # ------------------------------------------------------------------
    #  Index remapping helper
    # ------------------------------------------------------------------
    def testRemapIndex(self):
        remap = LogView._remapIndex
        self.assertEqual(-1, remap(-1, [0, 3]))
        self.assertEqual(1, remap(0, [0]))
        self.assertEqual(0, remap(0, [1]))
        self.assertEqual(5, remap(3, [0, 2]))
        self.assertEqual(3, remap(3, []))


class TestLogViewRepoTags(TestBase):
    """The repo tag row must stay O(1) no matter how many repos merged."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self._logView = LogView()

    def tearDown(self):
        self._logView.deleteLater()
        self.processEvents()
        super().tearDown()

    def _commit(self, repoDir, subRepoDirs):
        commit = Commit()
        commit.sha1 = "a" * 40
        commit.repoDir = repoDir
        for subRepoDir in subRepoDirs:
            sub = Commit()
            sub.repoDir = subRepoDir
            commit.subCommits.append(sub)
        return commit

    def testAllTagsShownWhenFewRepos(self):
        commit = self._commit(".", ["subA", "subB"])
        self.assertEqual(["<main>", "subA", "subB"],
                         LogView._repoTagTexts(commit))

    def testTagsFoldedWhenManyRepos(self):
        subs = ["sub%d" % i for i in range(20)]
        commit = self._commit(".", subs)

        texts = LogView._repoTagTexts(commit)
        self.assertEqual(LogView._MAX_REPO_TAGS, len(texts))
        self.assertEqual("<main>", texts[0])
        remaining = len(subs) - (LogView._MAX_REPO_TAGS - 2)
        self.assertEqual("+%d" % remaining, texts[-1])

    def testTagsNotFoldedAtExactLimit(self):
        subs = ["sub%d" % i for i in range(LogView._MAX_REPO_TAGS - 1)]
        commit = self._commit(".", subs)

        texts = LogView._repoTagTexts(commit)
        self.assertEqual(LogView._MAX_REPO_TAGS, len(texts))
        self.assertFalse(texts[-1].startswith("+"))

    def testDrawTagSkipsExhaustedRect(self):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QColor, QImage, QPainter

        image = QImage(200, 40, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(image)
        try:
            drawTag = self._logView._LogView__drawTag

            rect = QRect(10, 0, 0, 20)
            drawTag(painter, rect, QColor("red"), "sub")
            self.assertEqual(QRect(10, 0, 0, 20), rect,
                             "an exhausted rect must be left untouched")

            rect = QRect(0, 0, 200, 20)
            drawTag(painter, rect, QColor("red"), "sub")
            self.assertGreater(rect.left(), 0,
                               "a usable rect must still be consumed")
        finally:
            painter.end()
