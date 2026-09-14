# -*- coding: utf-8 -*-

from PySide6.QtTest import QSignalSpy

from qgitc.aicommitmessage import AiCommitMessage
from qgitc.llm import AiResponse
from tests.base import TestBase


class TestAiCommitMessage(TestBase):

    def setUp(self):
        super().setUp()
        self.commitMessage = AiCommitMessage()

    def tearDown(self):
        self.commitMessage.cancel()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def parseMessage(self, content: str) -> str:
        """ Feed the raw AI content and return the extracted commit message. """
        self.commitMessage._message = ""
        spy = QSignalSpy(self.commitMessage.messageAvailable)
        self.commitMessage._onAiResponseAvailable(AiResponse(message=content))
        self.commitMessage._onAiResponseFinished()
        self.assertEqual(1, spy.count())
        return spy.at(0)[0]

    def testPlainFence(self):
        self.assertEqual("feat: add test", self.parseMessage(
            "```text\nfeat: add test\n```"))

    def testPlainMessage(self):
        self.assertEqual("feat: add test", self.parseMessage("feat: add test"))

    def testThinkBlock(self):
        self.assertEqual("feat: add test", self.parseMessage(
            "<think>\nsome reasoning\n</think>\n```text\nfeat: add test\n```"))

    def testTrailingReasoningLeak(self):
        """ Some providers leak `</think>` into the content after the fence. """
        self.assertEqual("feat: add test", self.parseMessage(
            "```text\nfeat: add test\n```\n</think>"))

    def testSurroundingReasoningLeak(self):
        """ The content can hold leaked reasoning without the `<think>` tag. """
        self.assertEqual("feat: add test", self.parseMessage(
            "I should write a commit message.\n</think>\n"
            "```text\nfeat: add test\n```\n</think>"))

    def testLastFenceWins(self):
        """ If the leaked reasoning contains a fenced block, use the last one. """
        self.assertEqual("feat: add test", self.parseMessage(
            "Draft:\n```text\nfeat: draft\n```\n</think>\n"
            "```text\nfeat: add test\n```"))

    def testProseMentioningFence(self):
        """ Prose that mentions the marker must not be treated as the fence. """
        self.assertEqual("feat: add test", self.parseMessage(
            "```text\nfeat: add test\n```\n\n"
            "Note: the ```text block above holds the message."))

    def testInlineMentionBeforeFence(self):
        """ An inline mention before the real fence must be ignored too. """
        self.assertEqual("feat: add test", self.parseMessage(
            "I will wrap the message in a ```text block:\n\n"
            "```text\nfeat: add test\n```"))

    def testCrlfFence(self):
        """ Windows line endings must not break the fence detection. """
        self.assertEqual("feat: add test", self.parseMessage(
            "```text\r\nfeat: add test\r\n```"))

    def testNestedFencePreserved(self):
        """ A fenced block inside the commit message body is kept. """
        self.assertEqual("feat: add parser\n\n```py\nx = 1\n```",
                         self.parseMessage(
                             "```text\nfeat: add parser\n\n```py\nx = 1\n```\n```"))

    def testUnclosedFence(self):
        """ A missing closing fence must not drop the message. """
        self.assertEqual("feat: add test", self.parseMessage(
            "```text\nfeat: add test"))
