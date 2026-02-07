# -*- coding: utf-8 -*-

from qgitc.resolver.enums import ResolveOutcomeStatus
from qgitc.resolver.models import ResolveOutcome
from qgitc.resolver.resolvepanel import ResolvePanel
from tests.base import TestBase


class TestResolvePanel(TestBase):

    def doCreateRepo(self):
        pass

    def test_failed_file_updates_status_text(self):
        p = ResolvePanel()
        # simulate internal state: as if a file was being resolved
        p._currentPath = "a.txt"
        p._fileStates = {"a.txt": 0}

        # behave as if the manager just completed with a failure
        p._onFileCompleted(
            "a.txt",
            ResolveOutcome(
                status=ResolveOutcomeStatus.FAILED,
                message="no merge tool configured",
            ),
        )

        self.assertIn("Failed to resolve", p._label.text())
        self.assertIn("a.txt", p._label.text())
        self.assertIn("no merge tool configured", p._label.text())
