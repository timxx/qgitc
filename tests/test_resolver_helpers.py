# -*- coding: utf-8 -*-

from unittest.mock import patch

from qgitc.mergetool import MergeTool
from qgitc.resolver.handlers.mergetool import GitMergetoolHandler
from qgitc.resolver.helpers import buildResolveHandlers
from tests.base import TestBase


class TestResolverHelpers(TestBase):

    def doCreateRepo(self):
        pass

    def _patchApp(self, mergeToolName="", mergeToolList=None):
        patcher = patch("qgitc.resolver.helpers.ApplicationBase.instance")
        mockApp = patcher.start()
        self.addCleanup(patcher.stop)
        settings = mockApp.return_value.settings.return_value
        settings.mergeToolName.return_value = mergeToolName
        settings.mergeToolList.return_value = list(mergeToolList or [])
        return settings

    def test_git_configured_tool_is_passed_explicitly(self):
        self._patchApp()
        with patch("qgitc.resolver.helpers.Git.getConfigValue", return_value="kdiff3") as probe:
            handlers, mergeToolName, hasGitTool = buildResolveHandlers(
                parent=None,
                path="api/jsceservice/kjscefclient.cpp",
                repoDir="/repo/api",
                aiEnabled=False,
                chatWidget=None,
            )

        probe.assert_called_once_with("merge.tool", False, repoDir="/repo/api")
        self.assertEqual("kdiff3", mergeToolName)
        self.assertTrue(hasGitTool)
        self.assertEqual(1, len(handlers))
        self.assertIsInstance(handlers[0], GitMergetoolHandler)

    def test_no_tool_configured_builds_no_mergetool_handler(self):
        self._patchApp()
        with patch("qgitc.resolver.helpers.Git.getConfigValue", return_value=""):
            handlers, mergeToolName, hasGitTool = buildResolveHandlers(
                parent=None,
                path="a.cpp",
                repoDir="/repo",
                aiEnabled=False,
                chatWidget=None,
            )

        self.assertEqual([], handlers)
        self.assertIsNone(mergeToolName)
        self.assertFalse(hasGitTool)

    def test_preferences_tool_wins_over_git_tool(self):
        self._patchApp(
            mergeToolName="bc",
            mergeToolList=[MergeTool(MergeTool.Both, ".cpp", "bc")],
        )
        with patch("qgitc.resolver.helpers.Git.getConfigValue", return_value="kdiff3"):
            handlers, mergeToolName, hasGitTool = buildResolveHandlers(
                parent=None,
                path="a.cpp",
                repoDir="/repo",
                aiEnabled=False,
                chatWidget=None,
            )

        self.assertEqual("bc", mergeToolName)
        self.assertTrue(hasGitTool)
        self.assertEqual(1, len(handlers))
        self.assertIsInstance(handlers[0], GitMergetoolHandler)

    def test_git_probe_failure_is_treated_as_unconfigured(self):
        self._patchApp()
        with patch(
            "qgitc.resolver.helpers.Git.getConfigValue",
            side_effect=OSError("git is gone"),
        ):
            handlers, mergeToolName, hasGitTool = buildResolveHandlers(
                parent=None,
                path="a.cpp",
                repoDir="/repo",
                aiEnabled=False,
                chatWidget=None,
            )

        self.assertEqual([], handlers)
        self.assertIsNone(mergeToolName)
        self.assertFalse(hasGitTool)
