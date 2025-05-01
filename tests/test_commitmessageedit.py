# -*- coding: utf-8 -*-
from PySide6.QtGui import QTextCursor
from qgitc.commitmessageedit import CommitMessageEdit
from tests.base import TestBase


class TestCommitMessageEdit(TestBase):

    def setUp(self):
        self.edit = CommitMessageEdit()
        self.edit.show()

    def tearDown(self):
        self.edit.close()

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
