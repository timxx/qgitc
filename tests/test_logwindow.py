# -*- coding: utf-8 -*-
import os

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QSignalSpy, QTest

from qgitc.gitutils import Git
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestLogWindowBase(TestBase):
    def setUp(self):
        super().setUp()
        self.afterAppSetup()
        self.window = self.app.getWindow(WindowType.LogWindow)

    def afterAppSetup(self):
        pass

    def tearDown(self):
        self.window.close()
        self.processEvents()
        super().tearDown()

    def waitForLoaded(self):
        spySubmodule = QSignalSpy(self.app.submoduleSearchCompleted)

        self.window.show()
        QTest.qWaitForWindowExposed(self.window)

        delayTimer = self.window._delayTimer
        self.wait(10000, delayTimer.isActive)
        self.wait(10000, lambda: spySubmodule.count() == 0)

        logview = self.window.ui.gitViewA.ui.logView
        self.wait(10000, logview.fetcher.isLoading)
        self.wait(50)


class TestLogWindow(TestLogWindowBase):
    def createSubRepo(self):
        return True

    def testReloadRepo(self):
        self.assertFalse(self.window.isWindowReady)
        self.waitForLoaded()
        self.assertTrue(self.window.isWindowReady)

        logview = self.window.ui.gitViewA.ui.logView
        # now reload the repo
        spyBegin = QSignalSpy(logview.beginFetch)
        spyEnd = QSignalSpy(logview.endFetch)
        spyTimer = QSignalSpy(self.window.ui.gitViewA._delayTimer.timeout)

        self.window.reloadRepo()

        spyEnd.wait(3000)
        # we don't do any abort operation, so the begin and end should be called only once
        self.assertEqual(1, spyBegin.count())
        self.assertEqual(1, spyEnd.count())

        # the timer should never be triggered
        self.assertEqual(0, spyTimer.count())

    def testCompositeMode(self):
        self.waitForLoaded()

        self.assertEqual(2, self.window.ui.cbSubmodule.count())
        self.assertEqual(".", self.window.ui.cbSubmodule.itemText(0))
        self.assertEqual("subRepo", self.window.ui.cbSubmodule.itemText(1))

        logView = self.window.ui.gitViewA.ui.logView
        spyFetch = QSignalSpy(logView.fetcher.fetchFinished)
        self.window.ui.acCompositeMode.trigger()
        self.assertTrue(self.window.ui.acCompositeMode.isChecked())

        self.wait(10000, lambda: spyFetch.count() == 0)

        self.assertFalse(self.window.ui.cbSubmodule.isEnabled())

        self.assertEqual(logView.getCount(), 3)
        commit = logView.getCommit(0)
        self.assertEqual(commit.repoDir, ".")
        self.assertEqual(0, len(commit.subCommits))

        commit = logView.getCommit(1)
        self.assertTrue(commit.repoDir in [".", "subRepo"])
        self.assertEqual(1, len(commit.subCommits))

        commit = logView.getCommit(2)
        self.assertTrue(commit.repoDir in [".", "subRepo"])
        self.assertEqual(1, len(commit.subCommits))

        self.window.cancel(True)
        self.processEvents()

    def testLocalChanges(self):
        self.waitForLoaded()

        with open(os.path.join(self.gitDir.name, "test.txt"), "w+") as f:
            f.write("test")

        Git.addFiles(repoDir=self.gitDir.name, files=["test.txt"])

        subRepoFile = os.path.join("subRepo", "test.py")
        with open(os.path.join(self.gitDir.name, subRepoFile), "a+") as f:
            f.write("# new line\n")

        logView = self.window.ui.gitViewA.ui.logView

        self.window.ui.leOpts.clear()
        spyBegin = QSignalSpy(logView.beginFetch)
        QTest.keyClick(self.window.ui.leOpts, Qt.Key_Enter)
        self.wait(100, lambda: spyBegin.count() == 0)
        self.wait(1000, logView.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(4, logView.getCount())
        self.assertEqual(Git.LCC_SHA1, logView.getCommit(0).sha1)
        self.assertEqual(2, self.window.ui.cbSubmodule.count())

        spyBegin = QSignalSpy(self.app.submoduleSearchCompleted)
        self.window.ui.cbSubmodule.setCurrentIndex(1)
        self.wait(100, lambda: spyBegin.count() == 0)
        self.wait(1000, logView.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(3, logView.getCount())
        self.assertEqual(Git.LUC_SHA1, logView.getCommit(0).sha1)

        spyBegin = QSignalSpy(logView.beginFetch)
        self.window.ui.acCompositeMode.trigger()
        self.wait(100, lambda: spyBegin.count() == 0)
        self.wait(1000, logView.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(5, logView.getCount())
        self.assertEqual(Git.LUC_SHA1, logView.getCommit(0).sha1)
        self.assertEqual(Git.LCC_SHA1, logView.getCommit(1).sha1)

        diffView = self.window.ui.gitViewA.ui.diffView
        self.wait(1000, lambda: diffView.viewer._inReading)
        model = diffView.fileListModel
        self.assertEqual(model.rowCount(), 2)
        file: str = model.data(model.index(1, 0))
        self.assertTrue(file.endswith("subRepo/test.py"))

    def testInvalidFileFilter(self):
        self.waitForLoaded()

        logView = self.window.ui.gitViewA.ui.logView
        self.window.ui.leOpts.setText("-- invalidfile.txt")
        QTest.keyClick(self.window.ui.leOpts, Qt.Key_Enter)
        self.wait(1000, logView.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(0, logView.getCount())
        self.assertEqual(-1, logView.currentIndex())

        self.window.ui.leOpts.setText("-- invalidfile.py")
        QTest.keyClick(self.window.ui.leOpts, Qt.Key_Enter)
        self.wait(1000, logView.fetcher.isLoading)
        self.wait(50)

        self.assertEqual(0, logView.getCount())
        self.assertEqual(-1, logView.currentIndex())

    def testSubmodules(self):
        self.waitForLoaded()

        self.assertEqual(2, self.window.ui.cbSubmodule.count())

        # change to subRepo
        subRepo = os.path.join(self.gitDir.name, "subRepo")
        self.window.ui.leRepo.setText(subRepo)
        self.waitForLoaded()

        self.assertEqual(0, self.window.ui.cbSubmodule.count())

        self.window.ui.leRepo.setText(self.gitDir.name)
        self.waitForLoaded()

        self.assertEqual(2, self.window.ui.cbSubmodule.count())

    def testMultipleSelectionMouseClick(self):
        """Test multiple selection with mouse clicks"""
        self.waitForLoaded()

        logView = self.window.ui.gitViewA.ui.logView
        self.assertGreaterEqual(logView.getCount(), 3)

        # Ensure we're at the top and items 0-3 are visible
        logView.verticalScrollBar().setValue(0)
        logView.setCurrentIndex(0)
        logView.selectedIndices.clear()
        self.processEvents()

        # Normal click - should clear selection and set active item
        self.assertEqual(0, logView.currentIndex())
        self.assertEqual([], logView.getSelectedIndices())

        # Ctrl+Click to toggle selection on item 0
        self._clickItem(logView, 0, Qt.ControlModifier)
        self.assertIn(0, logView.selectedIndices)
        self.assertEqual([0], logView.getSelectedIndices())
        self.assertEqual(0, logView.currentIndex())

        # Ctrl+Click on another item to add to selection
        self._clickItem(logView, 1, Qt.ControlModifier)
        self.assertIn(0, logView.selectedIndices)
        self.assertIn(1, logView.selectedIndices)
        self.assertEqual([0, 1], logView.getSelectedIndices())
        self.assertEqual(1, logView.currentIndex())

        # Ctrl+Click on already selected item to deselect
        self._clickItem(logView, 0, Qt.ControlModifier)
        self.assertNotIn(0, logView.selectedIndices)
        self.assertIn(1, logView.selectedIndices)
        self.assertEqual([1], logView.getSelectedIndices())
        self.assertEqual(0, logView.currentIndex())

        # Shift+Click for range selection from current position (0) to 2
        self._clickItem(logView, 2, Qt.ShiftModifier)
        self.assertEqual([0, 1, 2], logView.getSelectedIndices())
        self.assertEqual(2, logView.currentIndex())

        # Normal click to clear previous selections and select only clicked item
        self._clickItem(logView, 1, Qt.NoModifier)
        self.processEvents()
        self.assertEqual([1], logView.getSelectedIndices())
        self.assertEqual(1, logView.currentIndex())

    def testMultipleSelectionKeyboard(self):
        """Test multiple selection with keyboard navigation"""
        self.waitForLoaded()

        logView = self.window.ui.gitViewA.ui.logView
        self.assertGreaterEqual(logView.getCount(), 3)

        # Set initial position
        logView.setCurrentIndex(0)
        self.assertEqual(0, logView.currentIndex())
        self.assertEqual([0], logView.getSelectedIndices())

        # Normal arrow key navigation should not change selection
        QTest.keyClick(logView, Qt.Key_Down)
        self.assertEqual(1, logView.currentIndex())
        self.assertEqual([0], logView.getSelectedIndices())

        QTest.keyClick(logView, Qt.Key_Up)
        self.assertEqual(0, logView.currentIndex())
        self.assertEqual([0], logView.getSelectedIndices())

        # Space to toggle selection of current item
        QTest.keyClick(logView, Qt.Key_Space)
        self.assertNotIn(0, logView.selectedIndices)
        self.assertEqual([], logView.getSelectedIndices())

        # Space again to deselect
        QTest.keyClick(logView, Qt.Key_Space)
        self.assertIn(0, logView.selectedIndices)
        self.assertEqual([0], logView.getSelectedIndices())

        # Shift+Down for range selection
        logView.setCurrentIndex(1)
        logView.selectedIndices.clear()
        QTest.keyClick(logView, Qt.Key_Down, Qt.ShiftModifier)
        self.assertEqual([1, 2], logView.getSelectedIndices())
        self.assertEqual(2, logView.currentIndex())

        # Shift+Up for range selection
        logView.setCurrentIndex(2)
        logView.selectedIndices.clear()
        QTest.keyClick(logView, Qt.Key_Up, Qt.ShiftModifier)
        self.assertEqual([1, 2], logView.getSelectedIndices())
        self.assertEqual(1, logView.currentIndex())

    def testSelectAll(self):
        """Test Ctrl+A to select all items"""
        self.waitForLoaded()

        logView = self.window.ui.gitViewA.ui.logView
        count = logView.getCount()
        self.assertGreater(count, 0)

        # Give focus to logView
        logView.setFocus()
        self.processEvents()

        # Initially selection
        self.assertEqual([0], logView.getSelectedIndices())

        # Ctrl+A to select all
        QTest.keyClick(logView, Qt.Key_A, Qt.ControlModifier)
        self.processEvents()
        self.assertEqual(count, len(logView.getSelectedIndices()))
        self.assertEqual(list(range(count)), logView.getSelectedIndices())

        # Clear selection
        logView.selectedIndices.clear()
        self.assertEqual([], logView.getSelectedIndices())

    def testGetSelectedCommits(self):
        """Test getting selected commits"""
        self.waitForLoaded()

        logView = self.window.ui.gitViewA.ui.logView
        self.assertGreater(logView.getCount(), 2)

        self.assertEqual([0], logView.getSelectedIndices())

        # Select some items
        logView.selectedIndices.add(0)
        logView.selectedIndices.add(1)

        selected = logView.getSelectedCommits()
        self.assertEqual(2, len(selected))
        self.assertEqual(logView.getCommit(0), selected[0])
        self.assertEqual(logView.getCommit(1), selected[1])

        # Select all
        logView.selectedIndices.update(range(logView.getCount()))
        selected = logView.getSelectedCommits()
        self.assertEqual(logView.getCount(), len(selected))

    def testSelectionClearOnClear(self):
        """Test that selection is cleared when logView.clear() is called"""
        self.waitForLoaded()

        logView = self.window.ui.gitViewA.ui.logView
        self.assertGreater(logView.getCount(), 0)

        # Select some items
        logView.selectedIndices.add(0)
        logView.selectedIndices.add(1)
        self.assertEqual([0, 1], logView.getSelectedIndices())

        # Clear should reset selection
        logView.clear()
        self.assertEqual([], logView.getSelectedIndices())
        self.assertEqual(-1, logView.currentIndex())

    def testActiveVsSelected(self):
        """Test that active item (curIdx) is different from selected items"""
        self.waitForLoaded()

        logView = self.window.ui.gitViewA.ui.logView
        self.assertGreaterEqual(logView.getCount(), 3)

        # Set active item without selection
        logView.setCurrentIndex(1)
        self.assertEqual(1, logView.currentIndex())
        self.assertEqual([1], logView.getSelectedIndices())

        # Select different items (not including active)
        logView.selectedIndices.add(0)
        logView.selectedIndices.add(2)
        self.assertEqual([0, 1, 2], logView.getSelectedIndices())
        self.assertEqual(1, logView.currentIndex())

        # Navigate to another item - selection should not change
        logView.setCurrentIndex(2)
        self.assertEqual([2], logView.getSelectedIndices())
        self.assertEqual(2, logView.currentIndex())

        # Select the active item too
        logView.selectedIndices.add(2)
        self.assertEqual([2], logView.getSelectedIndices())
        self.assertEqual(2, logView.currentIndex())

    def _createMouseEvent(self, widget, line, modifiers=Qt.NoModifier, eventType=QEvent.Type.MouseButtonPress):
        """Helper to create a mouse event at a specific line"""

        # Calculate y position relative to viewport (account for scroll)
        scrollPos = widget.verticalScrollBar().value()
        viewportLine = line - scrollPos
        y = viewportLine * widget.lineHeight + widget.lineHeight // 2
        pos = QPointF(10, y)

        # Create event with modifiers using the new constructor signature
        event = QMouseEvent(
            eventType,
            pos,
            pos,
            Qt.LeftButton,
            Qt.LeftButton,
            modifiers
        )
        return event

    def _clickItem(self, widget, line, modifiers=Qt.NoModifier):
        """Helper to simulate a complete click (press + release) on a specific line"""
        pressEvent = self._createMouseEvent(
            widget, line, modifiers, QEvent.Type.MouseButtonPress)
        releaseEvent = self._createMouseEvent(
            widget, line, modifiers, QEvent.Type.MouseButtonRelease)
        widget.mousePressEvent(pressEvent)
        widget.mouseReleaseEvent(releaseEvent)


class TestLogWindowNormalMode(TestLogWindowBase):
    def createSubRepo(self):
        return False

    def testRefMap(self):
        self.waitForLoaded()

        self.assertIsNotNone(Git.REF_MAP)
        self.assertGreaterEqual(len(Git.REF_MAP), 1)
        self.assertIsNotNone(Git.REV_HEAD)


class TestLogWindowNormalMode2(TestLogWindowBase):
    def createSubRepo(self):
        return True

    def testRefMap(self):
        self.waitForLoaded()

        self.assertIsNotNone(Git.REF_MAP)
        self.assertGreaterEqual(len(Git.REF_MAP), 1)
        self.assertIsNotNone(Git.REV_HEAD)


class TestLogWindowCompositeMode(TestLogWindowBase):
    def afterAppSetup(self):
        self.app.settings().setCompositeMode(True)

    def createSubRepo(self):
        return False

    def testRefMap(self):
        self.waitForLoaded()

        # composite mode is not really enabled when there is no submodule
        self.assertIsNotNone(Git.REF_MAP)
        self.assertGreaterEqual(len(Git.REF_MAP), 1)
        self.assertIsNotNone(Git.REV_HEAD)


class TestLogWindowCompositeMode2(TestLogWindowBase):
    def afterAppSetup(self):
        self.app.settings().setCompositeMode(True)

    def createSubRepo(self):
        return True

    def testRefMap(self):
        self.waitForLoaded()

        self.assertTrue(not Git.REF_MAP)
        self.assertTrue(not Git.REV_HEAD)
