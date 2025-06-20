
from PySide6.QtWidgets import QPlainTextEdit

from qgitc.markdownhighlighter import MarkdownHighlighter
from tests.base import TestBase


class TestMarkdownHighlighter(TestBase):
    def setUp(self):
        super().setUp()
        self.edit = QPlainTextEdit()
        self.highlighter = MarkdownHighlighter(self.edit.document())

    def doCreateRepo(self):
        pass

    def testSqlHighlighter(self):
        try:
            self.highlighter.sqlHighlighter("-")
        except IndexError as e:
            self.fail(f"Index out of range: {e}")
