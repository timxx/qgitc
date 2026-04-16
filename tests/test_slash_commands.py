# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.slash_commands import CommandRegistry


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


if __name__ == "__main__":
    unittest.main()
