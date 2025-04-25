# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from qgitc.textline import SourceTextLineBase, TextLine
from qgitc.textviewer import TextViewer
from tests.base import TestBase


class TestTextViewer(TestBase):
    def setUp(self):
        self.viewer = TextViewer()

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
