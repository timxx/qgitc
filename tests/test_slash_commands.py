# -*- coding: utf-8 -*-

import unittest

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtTest import QSignalSpy

from qgitc.agent.slash_commands import CommandRegistry
from qgitc.slash_command_popup import SlashCommandPopup
from tests.base import TestBase


class _DummyCommand:

    def __init__(self, name, aliases=None, description="", argument_hint=None):
        self.name = name
        self.aliases = aliases or []
        self.description = description
        self.argument_hint = argument_hint


class TestCommandRegistry(unittest.TestCase):

    def test_register_command(self):
        registry = CommandRegistry()
        cmd = _DummyCommand("review")

        registry.register(cmd)

        cmds = registry.list_commands()
        self.assertEqual(len(cmds), 1)
        self.assertIs(cmds[0], cmd)

    def test_find_by_name(self):
        registry = CommandRegistry()
        cmd = _DummyCommand("review")
        registry.register(cmd)

        found = registry.find("review")

        self.assertIs(found, cmd)

    def test_find_by_alias(self):
        registry = CommandRegistry()
        cmd = _DummyCommand("review", aliases=["r"])
        registry.register(cmd)

        found = registry.find("r")

        self.assertIs(found, cmd)

    def test_has(self):
        registry = CommandRegistry()
        cmd = _DummyCommand("review")
        registry.register(cmd)

        self.assertTrue(registry.has("review"))
        self.assertFalse(registry.has("missing"))

    def test_register_multiple_aliases(self):
        registry = CommandRegistry()
        cmd = _DummyCommand("review", aliases=["r", "rv"])
        registry.register(cmd)

        self.assertIs(registry.find("r"), cmd)
        self.assertIs(registry.find("rv"), cmd)


class TestSlashCommandPopup(TestBase):

    def doCreateRepo(self):
        pass

    def test_popup_set_commands(self):
        popup = SlashCommandPopup()
        popup.setCommands([
            _DummyCommand("review", description="Review changes"),
            _DummyCommand("plan", description="Plan tasks"),
        ])

        self.assertEqual(popup.commandCount(), 2)
        self.assertEqual(popup.currentCommand().name, "review")

    def test_popup_select_next_and_previous(self):
        popup = SlashCommandPopup()
        popup.setCommands([
            _DummyCommand("review"),
            _DummyCommand("plan"),
            _DummyCommand("tests"),
        ])

        popup.selectNext()
        self.assertEqual(popup.currentCommand().name, "plan")

        popup.selectNext()
        self.assertEqual(popup.currentCommand().name, "tests")

        popup.selectPrevious()
        self.assertEqual(popup.currentCommand().name, "plan")

    def test_popup_activate_current_emits_selected(self):
        popup = SlashCommandPopup()
        popup.setCommands([_DummyCommand("review")])
        spy = QSignalSpy(popup.commandSelected)

        popup.activateCurrent()

        self.assertEqual(spy.count(), 1)
        self.assertEqual(spy.at(0)[0].name, "review")

    def test_compute_popup_pos_flips_above_when_no_space_below(self):
        anchor = QPoint(200, 585)
        popupSize = QSize(120, 80)
        bounds = QRect(0, 0, 800, 600)

        pos = SlashCommandPopup.computePopupPos(anchor, popupSize, bounds)

        self.assertLess(pos.y(), anchor.y())

    def test_compute_popup_pos_clamps_to_screen_left(self):
        anchor = QPoint(-10, 50)
        popupSize = QSize(120, 80)
        bounds = QRect(0, 0, 800, 600)

        pos = SlashCommandPopup.computePopupPos(anchor, popupSize, bounds)

        self.assertEqual(pos.x(), bounds.left())


if __name__ == "__main__":
    unittest.main()
