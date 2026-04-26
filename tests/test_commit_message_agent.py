# -*- coding: utf-8 -*-

import unittest

from tests.base import TestBase


class TestCommitMessageSettings(TestBase):

    def doCreateRepo(self):
        pass

    def test_useSkillForCommitMessage_default_is_false(self):
        settings = self.app.settings()
        self.assertFalse(settings.useSkillForCommitMessage())

    def test_useSkillForCommitMessage_roundtrip(self):
        settings = self.app.settings()
        settings.setUseSkillForCommitMessage(True)
        self.assertTrue(settings.useSkillForCommitMessage())
        settings.setUseSkillForCommitMessage(False)
        self.assertFalse(settings.useSkillForCommitMessage())
