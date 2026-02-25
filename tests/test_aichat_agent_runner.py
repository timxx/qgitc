# -*- coding: utf-8 -*-
"""Test that Agent mode uses the new agent runner framework."""
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest

from qgitc.aichatwindow import AiChatWidget
from qgitc.llm import AiChatMode
from qgitc.windowtype import WindowType
from tests.base import TestBase


class TestAiChatAgentRunner(TestBase):
    def setUp(self):
        super().setUp()
        self.window = self.app.getWindow(WindowType.AiAssistant)
        self.chatWidget: AiChatWidget = self.window.centralWidget()
        # Switch to Agent mode
        self.chatWidget.contextPanel.cbMode.setCurrentIndex(0)
        self.assertEqual(
            self.chatWidget.contextPanel.currentMode(), AiChatMode.Agent)
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)
        # wait for initialization
        self.wait(
            200, lambda: self.chatWidget._historyPanel.currentHistory() is None)

    def tearDown(self):
        self.window.close()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_agent_runner_is_created_for_agent_mode(self):
        """Verify that Agent mode creates and uses SequentialAgentRunner."""
        self.assertIsNotNone(self.chatWidget._historyPanel.currentHistory())

        # Enter a simple prompt
        self.chatWidget._contextPanel.edit.edit.setPlainText("What is git status?")

        # Mock the runner's run method to avoid actual LLM call
        with patch.object(self.chatWidget, '_startAgentRun') as mock_start:
            QTest.mouseClick(
                self.chatWidget._contextPanel.btnSend, Qt.LeftButton)
            
            # Wait a bit for the click to process
            self.wait(100)
            
            # Verify _startAgentRun was called
            mock_start.assert_called_once()
            
            # Verify it was called with proper parameters
            args = mock_start.call_args[0]
            self.assertEqual(len(args), 2)  # params, sysPrompt
            params = args[0]
            self.assertIsNotNone(params.tools)
            self.assertEqual(params.tool_choice, "auto")

    def test_agent_runner_creates_multi_agent_structure(self):
        """Verify that _startAgentRun creates root + code_review agents."""
        from qgitc.agents.agentrunner import SequentialAgentRunner

        # Setup a mock model
        model = self.chatWidget.currentChatModel()
        
        # Create mock parameters  
        from qgitc.llm import AiParameters
        params = AiParameters()
        params.prompt = "test prompt"
        params.model = model.modelId or model.name
        params.tools = []
        params.tool_choice = "auto"
        params.reasoning = False
        
        # Mock the runner and its methods
        with patch.object(SequentialAgentRunner, 'run') as mock_run:
            self.chatWidget._startAgentRun(params, "test system prompt")
            
            # Verify runner was created and run() was called
            mock_run.assert_called_once()
            
            # Check the agent structure passed to run()
            args = mock_run.call_args[0]
            root_agent = args[0]  # First arg is the agent
            
            # Should be a SequentialAgent with sub_agents
            from qgitc.agents.agentruntime import SequentialAgent
            self.assertIsInstance(root_agent, SequentialAgent)
            self.assertEqual(root_agent.name, "chat")
            self.assertEqual(len(root_agent.sub_agents), 2)
            
            # Verify sub-agent names
            self.assertEqual(root_agent.sub_agents[0].name, "root")
            self.assertEqual(root_agent.sub_agents[1].name, "code_review")

    def test_agent_event_emitted_handler(self):
        """Verify agent events are properly handled."""
        from qgitc.agents.agentruntime import AgentEvent
        
        model = self.chatWidget.currentChatModel()
        self.chatWidget._agentActiveModel = model
        
        # Test assistant message event
        event = AgentEvent(
            author="assistant",
            content={"message": "Hello from agent"},
        )
        
        # Count initial blocks in chatbot
        chatbot = self.chatWidget.messages
        initial_blocks = chatbot.document().blockCount()
        
        # Handle the event
        self.chatWidget._onAgentEventEmitted(event)
        
        # Verify message was added to chat UI
        self.wait(100)
        self.processEvents()
        
        # The chatbot should have more blocks now
        self.assertGreater(chatbot.document().blockCount(), initial_blocks)
