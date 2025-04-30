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
        self.edit.setPlainText("Hello, `world`")
        cursor = self.edit.textCursor()

        cursor.setPosition(0)
        cursor.setPosition(7, QTextCursor.KeepAnchor)

        self.assertEqual(cursor.selectedText(), "Hello, ")

        inlineSpanColor = self.app.colorSchema().InlineCode
        fg = self.getForegroundColor(cursor).color()
        self.assertNotEqual(fg, inlineSpanColor)

        cursor.setPosition(7)
        cursor.setPosition(14, QTextCursor.KeepAnchor)
        self.assertEqual(cursor.selectedText(), "`world`")

        fg = self.getForegroundColor(cursor).color()
        self.assertEqual(fg, inlineSpanColor)

        self.edit.setPlainText("Hello, ``world``")

        cursor.setPosition(7)
        cursor.setPosition(16, QTextCursor.KeepAnchor)
        self.assertEqual(cursor.selectedText(), "``world``")

        fg = self.getForegroundColor(cursor).color()
        self.assertEqual(fg, inlineSpanColor)
