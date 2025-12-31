# -*- coding: utf-8 -*-
import time

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QSignalSpy, QTest

from qgitc.findconstants import FindFlags, FindPart
from qgitc.textline import SourceTextLineBase, TextLine
from qgitc.textviewer import TextViewer
from tests.base import TestBase


class TestTextViewer(TestBase):
    def setUp(self):
        super().setUp()
        self.viewer = TextViewer()

    def doCreateRepo(self):
        pass

    def testAppend(self):
        self.viewer.appendLine("First line")
        self.assertEqual(self.viewer.textLineCount(), 1)
        self.assertIsInstance((self.viewer.textLineAt(0)), TextLine)

        sourceLine = SourceTextLineBase("2nd line", self.viewer.font(), None)
        self.viewer.appendTextLine(sourceLine)
        self.assertEqual(self.viewer.textLineCount(), 2)
        self.assertIsInstance((self.viewer.textLineAt(1)), SourceTextLineBase)

    def testClick(self):
        self.viewer.appendLines(["Line 1", "Line 2", "Line 3"])
        self.assertEqual(self.viewer.textLineCount(), 3)

        spyClicked = QSignalSpy(self.viewer.textLineClicked)
        pos = self.viewer.textLineAt(0).boundingRect().center()
        QTest.mouseClick(self.viewer.viewport(),
                         Qt.LeftButton, pos=pos.toPoint())
        self.assertEqual(spyClicked.count(), 1)
        self.assertEqual(spyClicked.at(0)[0].lineNo(), 0)
        self.assertEqual(spyClicked.at(0)[0].text(), "Line 1")

    def testDoubleClick(self):
        self.viewer.appendLines(["Line1"])
        self.assertEqual(self.viewer.textLineCount(), 1)

        cursor = self.viewer.textCursor
        self.assertFalse(cursor.hasSelection())
        pos = self.viewer.textLineAt(0).boundingRect().center()
        QTest.mouseDClick(self.viewer.viewport(),
                          Qt.LeftButton, pos=pos.toPoint())

        self.assertTrue(cursor.hasSelection())
        self.assertEqual(cursor.selectedText(), "Line1")

    def testDoubleClickOnEmoji(self):
        self.viewer.appendLine("Hello 🤩 world")
        self.assertEqual(self.viewer.textLineCount(), 1)

        textLine = self.viewer.textLineAt(0)
        br = textLine.boundingRect()

        x1 = textLine.offsetToX(6)
        x2 = textLine.offsetToX(7)

        pos = QPointF(x1 + (x2 - x1) / 3, br.top() + br.height() / 2)
        QTest.mouseDClick(self.viewer.viewport(),
                          Qt.LeftButton, pos=pos.toPoint())

        cursor = self.viewer.textCursor
        self.assertTrue(cursor.hasSelection())
        self.assertEqual(cursor.selectedText(), "🤩")

        self.assertEqual(cursor.beginLine(), 0)
        self.assertEqual(cursor.endLine(), 0)
        self.assertEqual(cursor.beginPos(), 6)
        self.assertEqual(cursor.endPos(), 7)

        x = textLine.offsetToX(9)
        pos = QPointF(x, br.top() + br.height() / 2)
        QTest.mouseDClick(self.viewer.viewport(),
                          Qt.LeftButton, pos=pos.toPoint())

        self.assertTrue(cursor.hasSelection())
        self.assertEqual(cursor.selectedText(), "world")

        self.assertEqual(cursor.beginPos(), 8)
        self.assertEqual(cursor.endPos(), 13)

    def testMouseMove(self):
        self.viewer.appendLine("Hello world")
        self.assertEqual(self.viewer.textLineCount(), 1)

        br = self.viewer.textLineAt(0).boundingRect()
        pos = br.topLeft()
        pos.setY(pos.y() + br.height() / 2)
        QTest.mousePress(self.viewer.viewport(),
                         Qt.LeftButton, pos=pos.toPoint())
        pos = br.bottomRight()
        pos.setY(pos.y() + br.height() / 2)
        QTest.mouseMove(self.viewer.viewport(), pos=pos.toPoint())
        QTest.mouseRelease(self.viewer.viewport(),
                           Qt.LeftButton, pos=pos.toPoint())
        cursor = self.viewer.textCursor
        self.assertTrue(cursor.hasSelection())
        self.assertEqual(cursor.selectedText(), "Hello world")

    def testFindWidget(self):
        self.viewer.show()
        self.viewer.appendLines(["Line1", "Line2", "Line3"])
        self.assertEqual(self.viewer.textLineCount(), 3)

        self.viewer.executeFind()
        findWidget = self.viewer._findWidget
        QTest.qWaitForWindowExposed(findWidget)

        QTest.keyClick(findWidget._leFind, 'l')
        QTest.keyClick(findWidget._leFind, 'i')
        QTest.keyClick(findWidget._leFind, 'n')
        QTest.keyClick(findWidget._leFind, 'e')

        spyFind = QSignalSpy(findWidget.find)
        findWidget.findStarted()
        self.wait(250)
        findWidget.findFinished()

        self.assertEqual(1, spyFind.count())

        self.assertEqual("line", spyFind.at(0)[0])
        self.assertEqual(len(findWidget._findResult), 3)

        cursor = self.viewer.textCursor
        self.assertTrue(cursor.hasSelection())
        self.assertEqual(cursor.selectedText(), "Line")
        self.assertEqual(cursor.beginLine(), 0)
        self.assertEqual(cursor.endLine(), 0)
        self.assertEqual(cursor.beginPos(), 0)
        self.assertEqual(cursor.endPos(), 4)

        self.assertTrue(self.viewer.canFindNext())
        self.assertTrue(self.viewer.canFindPrevious())

        self.assertTrue(findWidget._tbNext.isEnabled())
        self.assertTrue(findWidget._tbPrev.isEnabled())

        QTest.mouseClick(findWidget._tbNext, Qt.LeftButton)
        self.assertEqual(cursor.beginLine(), 1)

        findWidget.findNext()
        self.assertEqual(cursor.beginLine(), 2)

        self.viewer.findNext()
        self.assertEqual(cursor.beginLine(), 0)

        QTest.mouseClick(findWidget._tbPrev, Qt.LeftButton)
        self.assertEqual(cursor.beginLine(), 2)

        findWidget.findPrevious()
        self.assertEqual(cursor.beginLine(), 1)

        self.viewer.findPrevious()
        self.assertEqual(cursor.beginLine(), 0)

        QTest.mouseClick(findWidget._leFind.matchCaseSwitch, Qt.LeftButton)
        self.assertEqual(len(findWidget._findResult), 0)

        findWidget.findPrevious()
        findWidget.findNext()

        findWidget.setText("Line")
        self.assertEqual(findWidget.text, "Line")

        self.wait(250)
        self.assertEqual(len(findWidget._findResult), 3)

        QTest.mouseClick(
            findWidget._leFind.matchWholeWordSwitch, Qt.LeftButton)
        self.assertEqual(len(findWidget._findResult), 0)

        QTest.mouseClick(findWidget._leFind.matchRegexSwitch, Qt.LeftButton)
        self.assertEqual(len(findWidget._findResult), 0)

        findWidget._leFind.setText("L.*1")
        self.wait(250)
        self.assertEqual(len(findWidget._findResult), 1)
        self.assertEqual(cursor.beginLine(), 0)

        # invalid regex
        findWidget.setText("(L.*1")
        self.wait(250)

        # TODO: now the result is last find
        self.assertEqual(len(findWidget._findResult), 1)

        self.viewer.closeFindWidget()

    def testFindAll(self):
        self.viewer.appendLine("hello, world")

        result = self.viewer.findAll("l")
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].beginLine(), 0)
        self.assertEqual(result[0].beginPos(), 2)
        self.assertEqual(result[1].beginLine(), 0)
        self.assertEqual(result[1].beginPos(), 3)
        self.assertEqual(result[2].beginLine(), 0)
        self.assertEqual(result[2].beginPos(), 10)

        result2 = self.viewer.findAll("l", flags=FindFlags.CaseSenitively)
        self.assertEqual(result, result2)

        result2 = self.viewer.findAll(
            "l", flags=FindFlags.CaseSenitively | FindFlags.UseRegExp)
        self.assertEqual(result, result2)

        result2 = self.viewer.findAll("L")
        self.assertEqual(result, result2)

        result2 = self.viewer.findAll("L", flags=FindFlags.CaseSenitively)
        self.assertEqual(len(result2), 0)

        result = self.viewer.findAll("l", flags=FindFlags.WholeWords)
        self.assertEqual(len(result), 0)

        result = self.viewer.findAll("hel.o")
        self.assertEqual(len(result), 0)

        result = self.viewer.findAll("hel.o", flags=FindFlags.WholeWords)
        self.assertEqual(len(result), 0)

        result = self.viewer.findAll("hel.o", flags=FindFlags.UseRegExp)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].beginLine(), 0)
        self.assertEqual(result[0].beginPos(), 0)
        self.assertEqual(result[0].endPos(), 5)

        result = self.viewer.findAll("wOrlD")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].beginLine(), 0)
        self.assertEqual(result[0].beginPos(), 7)
        self.assertEqual(result[0].endPos(), 12)

        result2 = self.viewer.findAll("wOrlD", flags=FindFlags.WholeWords)
        self.assertEqual(result, result2)

        result2 = self.viewer.findAll("wOrlD", flags=FindFlags.CaseSenitively)
        self.assertEqual(len(result2), 0)

        result2 = self.viewer.findAll(
            "w.*d", flags=FindFlags.UseRegExp | FindFlags.CaseSenitively | FindFlags.WholeWords)
        self.assertEqual(result2, result)

    def testFindResultAvailableSignalConnection(self):
        """Test that findResultAvailable signal is connected to _onFindResultAvailable.

        This is a regression test for the bug where findResultAvailable signal
        was not connected in the base TextViewer class, causing find results
        to be missing when text line count > 3000.
        """
        # Create a test spy to verify the signal can be received
        spyFindResult = QSignalSpy(self.viewer.findResultAvailable)

        # Create test data with search term
        self.viewer.appendLines(
            ["Line 1 with test", "Line 2 without", "Line 3 with test"])

        # Initialize the find widget so _onFindResultAvailable can complete successfully
        self.viewer.show()
        self.viewer.executeFind()
        findWidget = self.viewer._findWidget
        QTest.qWaitForWindowExposed(findWidget)

        # Manually trigger the signal as if findAllAsync emitted it
        results = self.viewer.findAll("test", 0)

        # Emit the signal manually to verify it's properly connected
        self.viewer.findResultAvailable.emit(results, FindPart.All)

        # Verify signal was received
        self.assertEqual(spyFindResult.count(), 1,
                         "findResultAvailable signal should be emitted")

        # Verify that _onFindResultAvailable was called by checking side effects
        # The method should highlight find results
        self.assertEqual(len(self.viewer._highlightFind), 2,
                         "Should have 2 highlighted find results after _onFindResultAvailable processes them")

        # Verify find widget received the results
        self.assertEqual(len(findWidget._findResult), 2,
                         "Find widget should have 2 results after signal processing")

        # Verify a result is selected
        cursor = self.viewer.textCursor
        self.assertTrue(cursor.hasSelection(),
                        "A find result should be selected")
        self.assertIn("test", cursor.selectedText(),
                      "Selected text should contain search term")

    def testFindAsyncWithManyLines(self):
        """Test async find functionality with more than 3000 lines.
        
        This verifies the fix for missing find results when text line count > 3000.
        When there are more than 3000 lines, findAllAsync is used which emits
        the findResultAvailable signal. This signal must be properly connected
        to _onFindResultAvailable to handle the results.
        """
        self.viewer.show()

        # Create more than 3000 lines with some lines containing "test"
        lines = []
        for i in range(3500):
            if i % 100 == 0:
                lines.append(f"Line {i} with test pattern")
            else:
                lines.append(f"Line {i} without pattern")

        self.viewer.appendLines(lines)
        self.assertEqual(self.viewer.textLineCount(), 3500)

        # Execute find operation
        self.viewer.executeFind()
        findWidget = self.viewer._findWidget
        QTest.qWaitForWindowExposed(findWidget)

        # Type search text
        findWidget._leFind.setText("test")

        # Create a spy to track findResultAvailable signal
        spyFindResult = QSignalSpy(self.viewer.findResultAvailable)
        spyFindFinished = QSignalSpy(self.viewer.findFinished)

        # Start the find operation
        findWidget.findStarted()

        self.wait(1000, lambda: spyFindFinished.count() == 0)

        # Verify that findResultAvailable signal was emitted
        self.assertGreater(
            spyFindResult.count(),
            0,
            "findResultAvailable signal should be emitted during async find"
        )

        # Verify that find results are available
        self.assertGreater(
            len(findWidget._findResult),
            0,
            "Find results should be available after async find completes"
        )

        # Verify the number of matches (35 lines with "test")
        self.assertEqual(
            len(findWidget._findResult),
            35,
            "Should find 35 occurrences of 'test'"
        )

        # Verify that a result is selected
        cursor = self.viewer.textCursor
        self.assertTrue(
            cursor.hasSelection(),
            "A find result should be selected"
        )
        self.assertIn(
            "test",
            cursor.selectedText().lower(),
            "Selected text should contain the search term"
        )

    def testFindAsyncCurrentPageEmitsSignal(self):
        """Test that findAllAsync emits findResultAvailable for current page results.
        
        This ensures the signal connection works for the immediate current page
        search results before the async search continues to other pages.
        """
        # Create enough lines to trigger async find (> 3000)
        lines = [f"Line {i} match" if i %
                 10 == 0 else f"Line {i}" for i in range(3100)]
        self.viewer.appendLines(lines)

        # Create a spy before starting the find
        spyFindResult = QSignalSpy(self.viewer.findResultAvailable)

        # Start async find
        started = self.viewer.findAllAsync("match", 0)

        # Should return True indicating async operation started
        self.assertTrue(
            started, "findAllAsync should return True for > 3000 lines")

        # Signal should be emitted at least once for current page results
        self.assertGreaterEqual(
            spyFindResult.count(),
            1,
            "findResultAvailable should be emitted at least once for current page"
        )

        # Clean up the async operation
        self.viewer.cancelFind()

    def testFindSyncWithFewerLinesDirect(self):
        """Test that synchronous find (< 3000 lines) works correctly.
        
        When line count is less than 3000, findAll is called directly and
        results are passed to _onFindResultAvailable. This should work
        regardless of the signal connection.
        """
        # Create fewer than 3000 lines
        lines = [f"Line {i} search" if i %
                 5 == 0 else f"Line {i}" for i in range(100)]
        self.viewer.appendLines(lines)

        # Use findAll directly (synchronous)
        results = self.viewer.findAll("search", 0)

        # Verify results
        self.assertEqual(len(results), 20, "Should find 20 occurrences")

        # Each result should be a valid TextCursor with selection
        for result in results:
            self.assertTrue(result.hasSelection(),
                            "Result should have a selection")
            self.assertEqual(result.beginLine(), result.endLine(),
                             "Single-line selection expected")
            # Verify the selection is in the expected position
            line_no = result.beginLine()
            self.assertEqual(line_no % 5, 0,
                             f"Match should be on lines divisible by 5, found on line {line_no}")
