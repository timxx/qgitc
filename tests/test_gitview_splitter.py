# -*- coding: utf-8 -*-
from unittest.mock import patch

from PySide6.QtTest import QTest

from qgitc.applicationbase import ApplicationBase
from qgitc.gitview import GitView
from tests.base import TestBase


class TestGitViewSplitterBase(TestBase):
    """Base class for GitView splitter tests"""

    def setUp(self):
        super().setUp()
        self.gitView = None

    def tearDown(self):
        if self.gitView:
            self.gitView.queryClose()
            self.gitView.deleteLater()
            self.gitView = None
        super().tearDown()

    def createGitView(self):
        """Create and show GitView"""
        self.gitView = GitView()
        self.gitView.show()
        QTest.qWaitForWindowExposed(self.gitView)
        self.processEvents()
        return self.gitView

    def assertSplitterRatio(self, splitter, expectedRatios, tolerance=0.1):
        """
        Assert that splitter sizes match expected ratios.
        
        Args:
            splitter: The QSplitter widget
            expectedRatios: List of expected ratios (e.g., [0.25, 0.75])
            tolerance: Acceptable deviation from expected ratio
        """
        sizes = splitter.sizes()
        total = sum(sizes)

        if total == 0:
            self.fail(f"Splitter has zero total size: {sizes}")

        actualRatios = [size / total for size in sizes]

        self.assertEqual(len(actualRatios), len(expectedRatios),
                         f"Expected {len(expectedRatios)} panes, got {len(actualRatios)}")

        for i, (actual, expected) in enumerate(zip(actualRatios, expectedRatios)):
            self.assertAlmostEqual(
                actual, expected, delta=tolerance,
                msg=f"Pane {i}: expected ratio {expected}, got {actual} (sizes: {sizes})"
            )

    def assertGraphCollapsed(self, gitView):
        """Assert that the log graph widget is collapsed (size 0 or near 0)"""
        sizes = gitView.ui.logWidget.sizes()
        self.assertEqual(
            len(sizes), 2, f"Expected 2 panes in logWidget, got {len(sizes)}")

        # First pane (graph) should be 0 or very small
        # Second pane (log view) should have all the space
        total = sum(sizes)
        if total > 0:
            graphRatio = sizes[0] / total
            self.assertLess(graphRatio, 0.01,
                            f"Graph should be collapsed, but ratio is {graphRatio} (sizes: {sizes})")

    def assertGraphExpanded(self, gitView):
        """Assert that the log graph widget is expanded (has visible size)"""
        sizes = gitView.ui.logWidget.sizes()
        self.assertEqual(
            len(sizes), 2, f"Expected 2 panes in logWidget, got {len(sizes)}")

        # Both panes should have some size
        total = sum(sizes)
        self.assertGreater(total, 0, "Total size should be greater than 0")

        graphRatio = sizes[0] / total if total > 0 else 0
        self.assertGreater(graphRatio, 0.01,
                           f"Graph should be visible, but ratio is {graphRatio} (sizes: {sizes})")


class TestGitViewSplitterNormalMode(TestGitViewSplitterBase):
    """Test GitView splitter in normal mode (composite mode OFF)"""

    def setUp(self):
        super().setUp()
        # Ensure composite mode is OFF
        self.app.settings().setCompositeMode(False)

    def testMainSplitterInitialState(self):
        """Test that main splitter (logView/diffView) is initialized with 1/4 and 3/4 ratio"""
        gitView = self.createGitView()

        # Main splitter should be 1/4 for log view, 3/4 for diff view
        self.assertSplitterRatio(gitView.ui.splitter, [0.25, 0.75])

    def testLogWidgetSplitterNoSubmodules(self):
        """Test that log widget splitter in normal mode without submodules uses default sizes"""
        gitView = self.createGitView()

        # Without submodules, graph should be visible (not collapsed)
        # We can't assert exact ratio as it depends on UI layout, but graph should be expanded
        self.assertGraphExpanded(gitView)

    def testLogWidgetSplitterAfterSubmoduleAvailable(self):
        """Test that log widget splitter remains expanded in normal mode even with submodules"""
        gitView = self.createGitView()

        # Simulate submodules becoming available
        submodules = ["submodule1", "submodule2"]
        gitView._GitView__onSubmoduleAvailable(submodules, fromCache=False)
        self.processEvents()

        # In normal mode, graph should remain expanded even with submodules
        self.assertGraphExpanded(gitView)


class TestGitViewSplitterCompositeMode(TestGitViewSplitterBase):
    """Test GitView splitter in composite mode (composite mode ON)"""

    def setUp(self):
        super().setUp()
        # Ensure composite mode is ON
        self.app.settings().setCompositeMode(True)

    def testMainSplitterInitialState(self):
        """Test that main splitter is initialized correctly in composite mode"""
        gitView = self.createGitView()

        # Main splitter should still be 1/4 and 3/4
        self.assertSplitterRatio(gitView.ui.splitter, [0.25, 0.75])

    def testLogWidgetCollapsedWithSubmodulesFromCache(self):
        """Test that log widget splitter collapses graph when submodules available from cache"""
        gitView = self.createGitView()

        # Simulate submodules available from cache
        submodules = ["submodule1", "submodule2"]
        gitView._GitView__onSubmoduleAvailable(submodules, fromCache=True)
        self.processEvents()

        # In composite mode with submodules, graph should be collapsed
        self.assertGraphCollapsed(gitView)

    def testLogWidgetCollapsedWithSubmodulesNotFromCache(self):
        """Test that log widget splitter collapses graph when submodules available not from cache"""
        gitView = self.createGitView()

        # Simulate submodules available (not from cache)
        submodules = ["submodule1", "submodule2"]
        gitView._GitView__onSubmoduleAvailable(submodules, fromCache=False)
        self.processEvents()

        # In composite mode with submodules, graph should be collapsed
        self.assertGraphCollapsed(gitView)

    def testLogWidgetExpandedWithoutSubmodules(self):
        """Test that log widget splitter keeps graph expanded without submodules in composite mode"""
        gitView = self.createGitView()

        # Without submodules, even in composite mode, graph should be expanded
        self.assertGraphExpanded(gitView)


class TestGitViewSplitterModeTransitions(TestGitViewSplitterBase):
    """Test GitView splitter behavior during mode transitions"""

    def testTransitionFromNormalToCompositeWithSubmodules(self):
        """Test transition from normal mode to composite mode with submodules present"""
        # Start in normal mode
        self.app.settings().setCompositeMode(False)
        gitView = self.createGitView()

        # Make submodules available
        with patch.object(ApplicationBase, 'instance', return_value=self.app):
            self.app._submodules = ["submodule1"]
            gitView._GitView__onSubmoduleAvailable(
                ["submodule1"], fromCache=True)
            self.processEvents()

        # Graph should be expanded in normal mode
        self.assertGraphExpanded(gitView)

        # Save the sizes before transition
        sizesBefore = gitView.ui.logWidget.sizes().copy()

        # Switch to composite mode
        with patch.object(ApplicationBase, 'instance', return_value=self.app):
            self.app._submodules = ["submodule1"]
            self.app.settings().setCompositeMode(True)
            self.processEvents()

        # Graph should now be collapsed
        self.assertGraphCollapsed(gitView)

        # Verify that sizes were saved
        self.assertIsNotNone(gitView._logWidgetSizes)
        self.assertGreater(len(gitView._logWidgetSizes), 0)

    def testTransitionFromCompositeToNormalRestoresSizes(self):
        """Test transition from composite mode to normal mode restores previous sizes"""
        # Start in composite mode
        self.app.settings().setCompositeMode(True)
        gitView = self.createGitView()

        # Make submodules available
        with patch.object(ApplicationBase, 'instance', return_value=self.app):
            self.app._submodules = ["submodule1"]
            gitView._GitView__onSubmoduleAvailable(
                ["submodule1"], fromCache=True)
            self.processEvents()

        # Graph should be collapsed
        self.assertGraphCollapsed(gitView)

        # The saved sizes should exist
        self.assertIsNotNone(gitView._logWidgetSizes)
        savedSizes = gitView._logWidgetSizes.copy()

        # Switch to normal mode
        with patch.object(ApplicationBase, 'instance', return_value=self.app):
            self.app._submodules = ["submodule1"]
            self.app.settings().setCompositeMode(False)
            self.processEvents()

        # Graph should be expanded again
        self.assertGraphExpanded(gitView)

        # Sizes should be restored
        currentSizes = gitView.ui.logWidget.sizes()
        self.assertEqual(currentSizes, savedSizes)

    def testTransitionWithoutSubmodules(self):
        """Test that mode transitions without submodules don't affect splitter"""
        # Start in normal mode without submodules
        self.app.settings().setCompositeMode(False)
        gitView = self.createGitView()

        with patch.object(ApplicationBase, 'instance', return_value=self.app):
            self.app._submodules = None

            # Graph should be expanded
            self.assertGraphExpanded(gitView)
            sizesBefore = gitView.ui.logWidget.sizes().copy()

            # Switch to composite mode (but no submodules)
            self.app.settings().setCompositeMode(True)
            self.processEvents()

            # Graph should still be expanded (no submodules to trigger collapse)
            self.assertGraphExpanded(gitView)

            # Switch back to normal mode
            self.app.settings().setCompositeMode(False)
            self.processEvents()

            # Should still be expanded
            self.assertGraphExpanded(gitView)


class TestGitViewSplitterSubmoduleScenarios(TestGitViewSplitterBase):
    """Test various submodule availability scenarios"""

    def testSubmodulesAvailableAfterViewCreation(self):
        """Test submodules becoming available after GitView is created"""
        self.app.settings().setCompositeMode(True)
        gitView = self.createGitView()

        # Initially no submodules
        with patch.object(ApplicationBase, 'instance', return_value=self.app):
            self.app._submodules = None
            self.assertGraphExpanded(gitView)

            # Submodules become available from cache
            self.app._submodules = ["submodule1", "submodule2"]
            gitView._GitView__onSubmoduleAvailable(
                ["submodule1", "submodule2"], fromCache=True)
            self.processEvents()

            # Graph should now be collapsed
            self.assertGraphCollapsed(gitView)

    def testMultipleSubmoduleUpdates(self):
        """Test multiple submodule availability updates"""
        self.app.settings().setCompositeMode(True)
        gitView = self.createGitView()

        with patch.object(ApplicationBase, 'instance', return_value=self.app):
            # First batch of submodules
            self.app._submodules = ["submodule1"]
            gitView._GitView__onSubmoduleAvailable(
                ["submodule1"], fromCache=True)
            self.processEvents()
            self.assertGraphCollapsed(gitView)

            sizes1 = gitView.ui.logWidget.sizes().copy()

            # Second batch of submodules (should maintain collapsed state)
            self.app._submodules = ["submodule1", "submodule2"]
            gitView._GitView__onSubmoduleAvailable(
                ["submodule1", "submodule2"], fromCache=False)
            self.processEvents()
            self.assertGraphCollapsed(gitView)

            # Should still be collapsed
            sizes2 = gitView.ui.logWidget.sizes()
            # Verify both are in collapsed state (first element near 0)
            self.assertEqual(sizes1[0], 0)
            self.assertEqual(sizes2[0], 0)

    def testEmptySubmoduleList(self):
        """Test behavior with empty submodule list"""
        self.app.settings().setCompositeMode(True)
        gitView = self.createGitView()

        with patch.object(ApplicationBase, 'instance', return_value=self.app):
            # Empty submodule list
            self.app._submodules = []
            gitView._GitView__onSubmoduleAvailable([], fromCache=True)
            self.processEvents()

            # __onSubmoduleAvailable always collapses in composite mode,
            # regardless of submodule list content
            self.assertGraphCollapsed(gitView)


class TestGitViewSplitterWithRealSubmodules(TestBase):
    """Test GitView splitter with actual submodules in repository"""

    def createSubmodule(self):
        """Enable submodule creation for this test class"""
        return True

    def testInitialStateWithSubmodulesInCompositeMode(self):
        """Test initial state when repository has submodules and composite mode is on"""
        self.app.settings().setCompositeMode(True)

        # Wait for submodule detection
        if self.app._findSubmoduleThread and self.app._findSubmoduleThread.isRunning():
            self.app._findSubmoduleThread.wait(5000)
        self.processEvents()

        gitView = GitView()
        gitView.show()
        QTest.qWaitForWindowExposed(gitView)
        self.processEvents()

        try:
            # If submodules were detected, graph should be collapsed
            if self.app.submodules:
                sizes = gitView.ui.logWidget.sizes()
                total = sum(sizes)
                if total > 0:
                    graphRatio = sizes[0] / total
                    self.assertLess(graphRatio, 0.01,
                                    f"Graph should be collapsed with submodules in composite mode")
        finally:
            gitView.queryClose()
            gitView.deleteLater()
            self.processEvents()

    def testInitialStateWithSubmodulesInNormalMode(self):
        """Test initial state when repository has submodules and composite mode is off"""
        self.app.settings().setCompositeMode(False)

        # Wait for submodule detection
        if self.app._findSubmoduleThread and self.app._findSubmoduleThread.isRunning():
            self.app._findSubmoduleThread.wait(5000)
        self.processEvents()

        gitView = GitView()
        gitView.show()
        QTest.qWaitForWindowExposed(gitView)
        self.processEvents()

        try:
            # In normal mode, graph should be expanded even with submodules
            sizes = gitView.ui.logWidget.sizes()
            total = sum(sizes)
            if total > 0:
                graphRatio = sizes[0] / total
                self.assertGreater(graphRatio, 0.01,
                                   f"Graph should be expanded in normal mode regardless of submodules")
        finally:
            gitView.queryClose()
            gitView.deleteLater()
            self.processEvents()
