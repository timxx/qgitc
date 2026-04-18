# -*- coding: utf-8 -*-

from unittest.mock import MagicMock, patch

from PySide6.QtTest import QTest

from qgitc.agent.agent_loop import QueryParams
from qgitc.agent.aimodel_adapter import AiModelBaseAdapter
from qgitc.agent.tool_registration import register_builtin_tools
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import TextBlock, UserMessage
from qgitc.aichatwidget import ResolveConflictJob
from qgitc.aichatwindow import AiChatWidget
from qgitc.llm import AiChatMode, AiModelBase, AiResponse, AiRole
from qgitc.models.prompts import RESOLVE_SYS_PROMPT
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestAgentMode(TestBase):
    def setUp(self):
        super().setUp()

        # Avoid instantiating real LLM models (which may trigger network/model discovery)
        # during AI window/widget creation.
        self._mockChatModel = MagicMock(spec=AiModelBase)
        self._mockChatModel.name = "Test AI Model"
        self._mockChatModel.modelId = "test-model"
        self._mockChatModel.history = []
        self._mockChatModel.isLocal.return_value = True
        self._mockChatModel.isRunning.return_value = False
        self._mockChatModel.queryAsync = MagicMock()
        self._mockChatModel.models.return_value = [
            ("test-model", "Test Model")]
        self._mockChatModel.supportsToolCalls.return_value = True
        self._mockChatModel.modelKey = "GithubCopilot"

        self._modelCreatePatcher = patch(
            'qgitc.llmprovider.AiModelProvider.createSpecificModel',
            return_value=self._mockChatModel,
        )
        self._modelCreatePatcher.start()
        self.addCleanup(self._modelCreatePatcher.stop)

        self.window = self.app.getWindow(WindowType.AiAssistant)
        self.chatWidget: AiChatWidget = self.window.centralWidget()
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)
        # Wait for creating new conversation
        self.wait(
            200, lambda: self.chatWidget._historyPanel.currentHistory() is None)

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def test_agent_loop_created_on_request(self):
        """Test that _ensureAgentLoop creates an AgentLoop."""
        self.assertIsNone(self.chatWidget._agentLoop)
        loop = self.chatWidget._ensureAgentLoop()
        self.assertIsNotNone(loop)
        self.assertIsNotNone(self.chatWidget._toolRegistry)

    def test_agent_loop_reset(self):
        """Test that _resetAgentLoop clears the loop."""
        self.chatWidget._ensureAgentLoop()
        self.assertIsNotNone(self.chatWidget._agentLoop)
        self.chatWidget._resetAgentLoop()
        self.assertIsNone(self.chatWidget._agentLoop)
        self.assertIsNone(self.chatWidget._toolRegistry)

    def test_query_close_interrupts_model_before_waiting_for_agent_loop(self):
        events = []

        class _Sig(object):
            def connect(self, _slot):
                pass

            def disconnect(self, _slot):
                pass

        class _FakeLoop(object):
            def __init__(self):
                self.textDelta = _Sig()
                self.reasoningDelta = _Sig()
                self.toolCallStart = _Sig()
                self.toolCallResult = _Sig()
                self.turnComplete = _Sig()
                self.agentFinished = _Sig()
                self.permissionRequired = _Sig()
                self.errorOccurred = _Sig()

            def abort(self):
                events.append("loop.abort")

            def wait(self, _ms):
                events.append("loop.wait")
                return True

        fakeLoop = _FakeLoop()
        self.chatWidget._agentLoop = fakeLoop
        self.chatWidget._toolRegistry = MagicMock()

        model = self.chatWidget.currentChatModel()
        model.isRunning.return_value = True
        model.requestInterruption.side_effect = lambda: events.append(
            "model.requestInterruption")
        model.cleanup.side_effect = lambda: events.append("model.cleanup")

        self.chatWidget.queryClose()

        self.assertEqual(
            events,
            [
                "model.requestInterruption",
                "loop.abort",
                "loop.wait",
                "model.cleanup",
            ],
        )

    def test_tool_registry_includes_builtin_tools(self):
        """Registry built by the widget should include builtin tools."""
        registry = self.chatWidget._buildToolRegistry()
        # git_status is a builtin tool
        tool = registry.get("git_status")
        self.assertIsNotNone(tool)

    def test_agent_tools_include_current_branch(self):
        # Sanity check the registry includes the dedicated current-branch tool,
        # so the LLM can fetch it without listing all branches.
        registry = ToolRegistry()
        register_builtin_tools(registry)
        names = [t.name for t in registry.list_tools()]
        self.assertIn("git_current_branch", names)

    def test_model_change_does_not_reset_existing_loop(self):
        loop = MagicMock()
        self.chatWidget._agentLoop = loop
        self.chatWidget._ensureModelInstantiatedAt = MagicMock(
            return_value=self.chatWidget.currentChatModel())
        self.chatWidget._loadMessagesFromHistory = MagicMock()

        self.chatWidget._onModelChanged(self.chatWidget._contextPanel.cbBots.currentIndex())

        self.assertIs(self.chatWidget._agentLoop, loop)

    def test_build_query_params_threads_temperature_and_chat_mode(self):
        settings = self.app.settings()
        settings.setLlmTemperature(0.42)

        caps = MagicMock()
        caps.context_window = 77777
        caps.max_output_tokens = 2222

        with patch.object(self.chatWidget, "_getModelCapabilities", return_value=caps):
            params = self.chatWidget._buildQueryParams(AiChatMode.Agent)

        self.assertEqual(params.context_window, 77777)
        self.assertEqual(params.max_output_tokens, 2222)
        self.assertIsInstance(params.provider, AiModelBaseAdapter)
        self.assertAlmostEqual(params.provider._temperature, 0.42, places=2)
        self.assertEqual(params.provider._chat_mode, AiChatMode.Agent)
        self.assertEqual(params.provider._max_tokens, 2222)

    def test_ensure_agent_loop_uses_new_constructor(self):
        class _Sig(object):
            def connect(self, _slot):
                pass

            def disconnect(self, _slot):
                pass

        class _FakeLoop(object):
            def __init__(self):
                self.textDelta = _Sig()
                self.reasoningDelta = _Sig()
                self.toolCallStart = _Sig()
                self.toolCallResult = _Sig()
                self.turnComplete = _Sig()
                self.agentFinished = _Sig()
                self.permissionRequired = _Sig()
                self.errorOccurred = _Sig()

            def abort(self):
                pass

            def wait(self, _ms):
                return True

        fakeLoop = _FakeLoop()
        with patch("qgitc.aichatwidget.AgentLoop", return_value=fakeLoop) as cls:
            loop = self.chatWidget._ensureAgentLoop()

        self.assertIs(loop, fakeLoop)
        self.assertIs(self.chatWidget._agentLoop, fakeLoop)
        self.assertIn("tool_registry", cls.call_args.kwargs)
        self.assertIn("permission_engine", cls.call_args.kwargs)
        self.assertIn("parent", cls.call_args.kwargs)
        self.assertNotIn("provider", cls.call_args.kwargs)

    def test_get_model_capabilities_handles_none_model(self):
        caps = self.chatWidget._getModelCapabilities(None)
        self.assertEqual(caps.context_window, 100000)
        self.assertEqual(caps.max_output_tokens, 4096)

    def test_get_model_capabilities_delegates_to_model(self):
        caps = MagicMock()
        caps.context_window = 55555
        caps.max_output_tokens = 1234
        self._mockChatModel.getModelCapabilities = MagicMock(return_value=caps)

        result = self.chatWidget._getModelCapabilities(self._mockChatModel)

        self.assertIs(result, caps)
        self._mockChatModel.getModelCapabilities.assert_called_once()

    def test_do_request_renders_system_prompt_once_per_conversation(self):
        fakeLoop = MagicMock()
        fakeLoop.messages.side_effect = [[], [UserMessage(content=[TextBlock(text="prior")])]]
        fakeLoop.submit = MagicMock()

        self.chatWidget._ensureAgentLoop = MagicMock(return_value=fakeLoop)
        self.chatWidget._setGenerating = MagicMock()
        self.chatWidget._updateChatHistoryModel = MagicMock()
        self.chatWidget._setEmbeddedRecentListVisible = MagicMock()
        self.chatWidget._chatBot.appendResponse = MagicMock()

        self.chatWidget._doRequest("first", AiChatMode.Agent, collapsed=True)
        self.chatWidget._doRequest("second", AiChatMode.Agent, collapsed=True)

        systemCount = 0
        for call in self.chatWidget._chatBot.appendResponse.call_args_list:
            if call.args and isinstance(call.args[0], AiResponse):
                if call.args[0].role == AiRole.System:
                    systemCount += 1

        self.assertEqual(systemCount, 1)

    def test_resolve_conflict_job_submits_query_params(self):
        settings = self.app.settings()
        settings.setLlmTemperature(0.37)

        caps = MagicMock()
        caps.context_window = 24680
        caps.max_output_tokens = 1357

        class _Sig(object):
            def connect(self, _slot):
                pass

        class _FakeLoop(object):
            def __init__(self):
                self.textDelta = _Sig()
                self.reasoningDelta = _Sig()
                self.toolCallStart = _Sig()
                self.toolCallResult = _Sig()
                self.agentFinished = _Sig()
                self.errorOccurred = _Sig()
                self.submit = MagicMock()

            def abort(self):
                pass

            def wait(self, _ms):
                return True

        fakeLoop = _FakeLoop()
        with patch.object(self.chatWidget, "_getModelCapabilities", return_value=caps):
            with patch("qgitc.aichatwidget.AgentLoop", return_value=fakeLoop):
                job = ResolveConflictJob(
                    widget=self.chatWidget,
                    repoDir=self.gitDir.name,
                    sha1=None,
                    path="README.md",
                    conflictText="<<<<<<< ours\nfoo\n=======\nbar\n>>>>>>> theirs",
                )
                job.start()

        fakeLoop.submit.assert_called_once()
        submittedPrompt, submittedParams = fakeLoop.submit.call_args.args
        self.assertIn("<<<<<<< ours", submittedPrompt)
        self.assertIsInstance(submittedParams, QueryParams)
        self.assertEqual(submittedParams.context_window, 24680)
        self.assertEqual(submittedParams.max_output_tokens, 1357)
        self.assertIsInstance(submittedParams.provider, AiModelBaseAdapter)
        self.assertEqual(submittedParams.provider._chat_mode, AiChatMode.Agent)
        self.assertAlmostEqual(submittedParams.provider._temperature, 0.37, places=2)
        self.assertEqual(submittedParams.provider._max_tokens, 1357)

    def test_do_request_submits_prompt_with_query_params(self):
        fakeLoop = MagicMock()
        fakeLoop.messages.return_value = []
        fakeLoop.submit = MagicMock()

        params = QueryParams(provider=MagicMock())

        self.chatWidget._ensureAgentLoop = MagicMock(return_value=fakeLoop)
        self.chatWidget._buildQueryParams = MagicMock(return_value=params)
        self.chatWidget._setGenerating = MagicMock()
        self.chatWidget._updateChatHistoryModel = MagicMock()
        self.chatWidget._setEmbeddedRecentListVisible = MagicMock()
        self.chatWidget._chatBot.appendResponse = MagicMock()

        self.chatWidget._doRequest("hello", AiChatMode.Agent, collapsed=True)

        fakeLoop.submit.assert_called_once_with("hello", params)

    def test_build_system_prompt_injects_skills_reminder_for_agent_mode(self):
        from qgitc.agent.skills.registry import SkillRegistry
        from qgitc.agent.skills.types import SkillDefinition

        skill_registry = SkillRegistry()
        skill_registry.register(SkillDefinition(
            name="review",
            description="Review code changes",
            content="Body",
        ))
        self.chatWidget._skillRegistry = skill_registry

        sp = self.chatWidget._buildSystemPrompt()
        self.assertIn("Available skills:", sp)
        self.assertIn("review", sp)
