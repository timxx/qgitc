# -*- coding: utf-8 -*-

import unittest

from qgitc.aichatwidget import AiChatWidget


class TestAiChatWidgetSlashHelpers(unittest.TestCase):

    def test_parse_slash_command_name_only(self):
        command, args = AiChatWidget._parseSlashCommand("/review")
        self.assertEqual(command, "review")
        self.assertEqual(args, "")

    def test_parse_slash_command_with_args(self):
        command, args = AiChatWidget._parseSlashCommand("/review staged files")
        self.assertEqual(command, "review")
        self.assertEqual(args, "staged files")

    def test_parse_non_slash_text(self):
        command, args = AiChatWidget._parseSlashCommand("hello")
        self.assertEqual(command, "")
        self.assertEqual(args, "")

    def test_expand_skill_arguments_replaces_placeholder(self):
        expanded = AiChatWidget._expandSkillArguments(
            "Please do: $ARGUMENTS",
            "check this diff",
        )
        self.assertEqual(expanded, "Please do: check this diff")

    def test_expand_skill_arguments_appends_when_no_placeholder(self):
        expanded = AiChatWidget._expandSkillArguments(
            "Do the task",
            "with details",
        )
        self.assertEqual(expanded, "Do the task\n\nARGUMENTS: with details")


if __name__ == "__main__":
    unittest.main()
