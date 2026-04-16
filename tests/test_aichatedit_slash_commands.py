# -*- coding: utf-8 -*-

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from qgitc.agent.slash_commands import CommandRegistry
from qgitc.aichatedit import AiChatEdit
from tests.base import TestBase


class _DummyCommand:

    def __init__(self, name, aliases=None, description="", argument_hint=None):
        self.name = name
        self.aliases = aliases or []
        self.description = description
        self.argument_hint = argument_hint


class TestAiChatEditSlashCommands(TestBase):

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.widget = AiChatEdit()
        self.widget.show()
        self.processEvents()

        self.registry = CommandRegistry()
        self.registry.register(_DummyCommand("review"))
        self.registry.register(_DummyCommand("plan"))
        self.registry.register(_DummyCommand("retry"))
        self.widget.setCommandRegistry(self.registry)

    def tearDown(self):
        self.widget.close()
        super().tearDown()

    def test_typing_slash_shows_popup(self):
        self.widget.edit.setPlainText("/")
        self.processEvents()

        self.assertIsNotNone(self.widget._slashCommandPopup)
        self.assertTrue(self.widget._slashCommandPopup.isVisible())
        self.assertEqual(self.widget._slashCommandPopup.commandCount(), 3)

    def test_space_hides_popup(self):
        self.widget.edit.setPlainText("/review arg")
        self.processEvents()

        if self.widget._slashCommandPopup is not None:
            self.assertFalse(self.widget._slashCommandPopup.isVisible())

    def test_fuzzy_filtering(self):
        self.widget.edit.setPlainText("/rv")
        self.processEvents()

        self.assertIsNotNone(self.widget._slashCommandPopup)
        self.assertEqual(self.widget._slashCommandPopup.commandCount(), 1)
        self.assertEqual(self.widget._slashCommandPopup.currentCommand().name, "review")

    def test_select_command_updates_input(self):
        self.widget.edit.setPlainText("/rv")
        self.processEvents()

        self.widget._slashCommandPopup.activateCurrent()
        self.processEvents()

        self.assertEqual(self.widget.toPlainText(), "/review ")

    def test_popup_allows_typing_when_visible(self):
        self.widget.edit.setPlainText("/")
        cursor = self.widget.edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.widget.edit.setTextCursor(cursor)
        self.processEvents()

        self.assertTrue(self.widget._slashCommandPopup.isVisible())

        QTest.keyClick(self.widget._slashCommandPopup, Qt.Key_R)
        self.processEvents()

        self.assertEqual(self.widget.toPlainText(), "/r")
