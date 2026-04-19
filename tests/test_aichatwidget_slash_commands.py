# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.types import TextBlock, UserMessage
from qgitc.aichatwidget import AiChatWidget
from tests.base import TestBase


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

    def test_history_has_same_context_in_messages_matches_existing_context(self):
        context_text = "repo: .\nfiles_changed:\n- qgitc/aichatwidget.py"
        full_prompt = (
            f"<context>\n{context_text}\n</context>\n\n"
            "Please review these changes"
        )
        messages = [UserMessage(content=[TextBlock(text=full_prompt)])]

        self.assertTrue(
            AiChatWidget._historyHasSameContextInMessages(messages, context_text)
        )

    def test_history_has_same_context_in_messages_returns_false_for_different_context(self):
        messages = [
            UserMessage(content=[TextBlock(text="<context>\na\n</context>\n\nPrompt")])
        ]

        self.assertFalse(
            AiChatWidget._historyHasSameContextInMessages(messages, "b")
        )


class TestAiChatWidgetSlashInit(TestBase):

    def doCreateRepo(self):
        pass

    def test_constructor_initializes_slash_registry_before_panel_setup(self):
        widget = None
        try:
            widget = AiChatWidget()
            self.assertIsNotNone(widget)
        except:
            self.fail("Constructor raised an exception")
        finally:
            if widget:
                widget.close()


if __name__ == "__main__":
    unittest.main()
