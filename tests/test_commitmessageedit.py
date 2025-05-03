# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from qgitc.commitmessageedit import CommitMessageEdit
from tests.base import TestBase


class TestCommitMessageEdit(TestBase):

    def setUp(self):
        super().setUp()
        self.edit = CommitMessageEdit()
        self.edit.show()

    def tearDown(self):
        self.edit.close()
        super().tearDown()

    def getForegroundColor(self, cursor: QTextCursor):
        block = cursor.block()
        for fr in block.layout().formats():
            start = fr.start
            end = fr.start + fr.length
            if start <= cursor.selectionStart() and cursor.selectionEnd() <= end:
                return fr.format.foreground()

        return cursor.blockFormat().foreground()

    def testBacktick(self):
        params = [
            {"text": "Hello, `world`",
             "normalRanges": [(0, 7)],
             "backticks": [(7, 14)],
             },
            {
                "text": "Hello, ``world``",
                "normalRanges": [(0, 7)],
                "backticks": [(7, 16)]
            },
            {
                "text": "```Hello```",
                "normalRanges": [],
                "backticks": [(0, 11)]
            },
            {
                "text": "H`el`l`o`",
                "normalRanges": [(0, 1), (5, 6)],
                "backticks": [(1, 5), (6, 9)]
            }
        ]

        for param in params:
            with self.subTest(param=param):
                text = param["text"]
                self.edit.setPlainText(text)
                cursor = self.edit.textCursor()

                inlineSpanColor = self.app.colorSchema().InlineCode

                normalRanges = param["normalRanges"]
                for start, end in normalRanges:
                    cursor.setPosition(start)
                    cursor.setPosition(end, QTextCursor.KeepAnchor)

                    self.assertEqual(cursor.selectedText(), text[start:end])

                    fg = self.getForegroundColor(cursor).color()
                    self.assertNotEqual(fg, inlineSpanColor)

                backticks = param["backticks"]
                for start, end in backticks:
                    cursor.setPosition(start)
                    cursor.setPosition(end, QTextCursor.KeepAnchor)
                    self.assertEqual(cursor.selectedText(), text[start:end])

                    fg = self.getForegroundColor(cursor).color()
                    self.assertEqual(fg, inlineSpanColor)

    def testTabGroups(self):
        # we enable by default
        self.assertTrue(self.app.settings().tabToNextGroup())
        groupChars = [groupChar.strip() for groupChar in self.app.settings(
        ).groupChars().split(" ") if len(groupChar.strip()) == 2]
        self.assertEqual(2, len(groupChars))
        self.assertEqual(groupChars[0], "【】")
        self.assertEqual(groupChars[1], "[]")

        # do nothing for empty document
        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertTrue(self.edit.document().isEmpty())

        self.edit.setPlainText("No groups")

        # should not hangs
        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 9)

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 9)

        QTest.keyClick(self.edit, Qt.Key_Backtab)
        self.assertEqual(self.edit.textCursor().position(), 0)

        self.edit.setPlainText("Line1\n\nLine2")
        cursor = self.edit.textCursor()
        cursor.setPosition(6)
        self.edit.setTextCursor(cursor)

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 12)

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 12)

        QTest.keyClick(self.edit, Qt.Key_Backtab)
        self.assertEqual(self.edit.textCursor().position(), 0)

        self.edit.setPlainText("【hello")

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 6)

        QTest.keyClick(self.edit, Qt.Key_Backtab)
        self.assertEqual(self.edit.textCursor().position(), 0)

        self.edit.setPlainText("【hello】")

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 6)

        QTest.keyClick(self.edit, Qt.Key_Backtab)
        self.assertEqual(self.edit.textCursor().position(), 0)

        self.edit.setPlainText("[hello]\n[world]")

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 6)

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 14)

        # next round
        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 6)

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 14)

        QTest.keyClick(self.edit, Qt.Key_Backtab)
        self.assertEqual(self.edit.textCursor().position(), 6)

        QTest.keyClick(self.edit, Qt.Key_Backtab)
        self.assertEqual(self.edit.textCursor().position(), 14)

        # break lines
        self.edit.setPlainText("[hello\n]")

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 7)

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 7)

        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.edit.setTextCursor(cursor)

        QTest.keyClick(self.edit, Qt.Key_Backtab)
        self.assertEqual(self.edit.textCursor().position(), 0)

        QTest.keyClick(self.edit, Qt.Key_Backtab)
        self.assertEqual(self.edit.textCursor().position(), 0)

        # we enable by default
        self.assertTrue(self.app.settings().ignoreCommentLine())

        self.edit.setPlainText("# [hello]")

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual(self.edit.textCursor().position(), 9)

        QTest.keyClick(self.edit, Qt.Key_Backtab)
        self.assertEqual(self.edit.textCursor().position(), 0)

    def testNoGroups(self):
        settings = self.app.settings()
        groupChars = settings.groupChars()
        settings.setGroupChars("")

        self.edit.setPlainText("[hello]")
        QTest.keyClick(self.edit, Qt.Key_Tab)

        self.assertEqual(0, self.edit.textCursor().position())

        settings.setGroupChars(groupChars)

    def testDisableTabGroups(self):
        settings = self.app.settings()
        oldValue = settings.tabToNextGroup()

        settings.setTabToNextGroup(False)

        QTest.keyClick(self.edit, Qt.Key_Tab)
        self.assertEqual("\t", self.edit.toPlainText())

        settings.setTabToNextGroup(oldValue)

    def testNormalKey(self):
        QTest.keyClick(self.edit, Qt.Key_0)
        self.assertEqual("0", self.edit.toPlainText())

    def testLinks(self):
        settings = self.app.settings()
        patterns = [("(#([0-9]+))", "https://github.com/foo/bar/issues/")]
        settings.setBugPatterns(self.app.repoName(), patterns)

        self.edit.setPlainText("Fix #1234")
        cursor = self.edit.textCursor()
        cursor.setPosition(4)
        cursor.setPosition(9, QTextCursor.KeepAnchor)
        self.assertEqual(cursor.selectedText(), "#1234")

        fg = self.getForegroundColor(cursor).color()
        self.assertEqual(fg, self.edit.palette().link().color())
