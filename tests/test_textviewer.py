# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest

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

        QTest.mouseClick(findWidget._matchCaseSwitch, Qt.LeftButton)
        self.assertEqual(len(findWidget._findResult), 0)

        findWidget.findPrevious()
        findWidget.findNext()

        findWidget.setText("Line")
        self.assertEqual(findWidget.text, "Line")

        self.wait(250)
        self.assertEqual(len(findWidget._findResult), 3)

        QTest.mouseClick(findWidget._matchWholeWordSwitch, Qt.LeftButton)
        self.assertEqual(len(findWidget._findResult), 0)

        QTest.mouseClick(findWidget._matchRegexSwitch, Qt.LeftButton)
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
