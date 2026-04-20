# -*- coding: utf-8 -*-

from PySide6.QtGui import QColor

from qgitc.terminaloutputwidget import TerminalOutputWidget
from tests.base import TestBase


class TestTerminalOutputWidget(TestBase):
    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.widget = TerminalOutputWidget()

    def testAppendsPlainOutputToNamedBlock(self):
        self.widget.ensureBlock("stdout", "STDOUT")
        self.widget.appendOutput("stdout", b"hello\nworld\n", False)

        text = self.widget.toPlainText()
        self.assertIn("STDOUT", text)
        self.assertIn("hello", text)
        self.assertIn("world", text)

    def testOverwritesCurrentLineOnCarriageReturn(self):
        self.widget.ensureBlock("stdout", "STDOUT")
        self.widget.appendOutput("stdout", b"progress 10%\rprogress 100%\n", False)

        text = self.widget.toPlainText()
        self.assertNotIn("progress 10%", text)
        self.assertIn("progress 100%", text)

    def testSeparatesOverwriteStatePerBlock(self):
        self.widget.ensureBlock("stdout", "STDOUT")
        self.widget.ensureBlock("stderr", "STDERR")

        self.widget.appendOutput("stdout", b"loading\r", False)
        self.widget.appendOutput("stderr", b"err\n", True)
        self.widget.appendOutput("stdout", b"done\n", False)

        text = self.widget.toPlainText()
        self.assertIn("STDOUT", text)
        self.assertIn("STDERR", text)
        self.assertNotIn("loadingdone", text)
        self.assertIn("done", text)
        self.assertIn("err", text)

    def testParsesAnsiColor(self):
        self.widget.ensureBlock("stderr", "STDERR")
        self.widget.appendOutput("stderr", b"\x1b[31mRED\x1b[0m plain\n", True)

        redCursor = self.widget.document().find("RED")
        plainCursor = self.widget.document().find("plain")

        self.assertFalse(redCursor.isNull())
        self.assertFalse(plainCursor.isNull())

        redColor = redCursor.charFormat().foreground().color()
        plainColor = plainCursor.charFormat().foreground().color()

        self.assertEqual(redColor.name(), QColor("red").name())
        self.assertNotEqual(plainColor.name(), QColor("red").name())

    def testKeepsLineContentWhenUsingCrlf(self):
        self.widget.ensureBlock("stdout", "STDOUT")
        self.widget.appendOutput("stdout", b"hello\r\n", False)

        text = self.widget.toPlainText()
        self.assertIn("hello", text)

    def testParsesSplitAnsiSequenceAcrossAppends(self):
        self.widget.ensureBlock("stdout", "STDOUT")
        self.widget.appendOutput("stdout", b"\x1b[3", False)
        self.widget.appendOutput("stdout", b"1mRED\x1b[0m\n", False)

        text = self.widget.toPlainText()
        self.assertNotIn("\x1b[31m", text)
        self.assertNotIn("\x1b[3", text)

        redCursor = self.widget.document().find("RED")
        self.assertFalse(redCursor.isNull())

        redColor = redCursor.charFormat().foreground().color()
        self.assertEqual(redColor.name(), QColor("red").name())
