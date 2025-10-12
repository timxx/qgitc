
from PySide6.QtWidgets import QPlainTextEdit

from qgitc.markdownhighlighter import MarkdownHighlighter, isValidEmail
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

    def testTomlHighlighter(self):
        self.edit.setPlainText('```TOML\n[project]\nname = "qgitc"\n```')

    def testIsValidEmail(self):
        # Valid emails
        self.assertTrue(isValidEmail("test@example.com"))
        self.assertTrue(isValidEmail("user.name@domain.com"))
        self.assertTrue(isValidEmail("user-name@domain.co.uk"))

        # Invalid emails
        self.assertFalse(isValidEmail(""))
        self.assertFalse(isValidEmail("test"))
        self.assertFalse(isValidEmail("test@"))
        self.assertFalse(isValidEmail("@example.com"))
        self.assertFalse(isValidEmail("test@example"))
        self.assertFalse(isValidEmail("test..name@example.com"))
