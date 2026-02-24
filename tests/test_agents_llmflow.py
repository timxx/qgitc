# -*- coding: utf-8 -*-
"""
Unit tests for LLM Flow.

Tests cover:
- Single LLM response (no tools)
- LLM response with tool calls
- Tool machine integration
- Model override resolution
- Tool results accumulation and continuation
"""

import unittest
from unittest.mock import MagicMock, Mock, call, patch

from PySide6.QtCore import QObject, Signal

from qgitc.agentmachine import AgentToolMachine
from qgitc.agents.agentruntime import AgentEvent, InvocationContext, LlmAgent
from qgitc.agents.llmflow import LlmFlow
from qgitc.llm import AiResponse, AiRole


class MockModel(QObject):
    """Mock AI model for testing."""

    responseAvailable = Signal(object)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.last_params = None
        self.is_running = False

    def queryAsync(self, params):
        """Record params and mark as running."""
        self.last_params = params
        self.is_running = True

    def isRunning(self):
        return self.is_running


class TestLlmFlow(unittest.TestCase):
    """Tests for LlmFlow."""

    def setUp(self):
        """Set up test fixtures."""
        self.tool_machine = Mock(spec=AgentToolMachine)
        self.tool_machine.processToolCalls = Mock()
        self.tool_machine.agentContinuationReady = Signal()

        # Create a default mock model that will be returned by lookup
        self.mock_model = MockModel()
        self.model_lookup_fn = Mock(return_value=self.mock_model)

        self.flow = LlmFlow(
            toolMachine=self.tool_machine,
            modelLookupFn=self.model_lookup_fn,
        )

        # Collect emitted events
        self.emitted_events = []
        self.flow.eventEmitted.connect(self._onEventEmitted)
        self.flow_finished = False
        self.flow.flowFinished.connect(self._onFlowFinished)

    def _onEventEmitted(self, event):
        """Collect emitted events."""
        self.emitted_events.append(event)

    def _onFlowFinished(self):
        """Mark flow as finished."""
        self.flow_finished = True

    def test_run_with_simple_response(self):
        """Test running flow with a simple LLM response (no tool calls)."""
        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        # Start the flow
        self.flow.run(ctx, userPrompt="What is 2+2?")

        # Verify model was looked up and queried
        self.model_lookup_fn.assert_called_once()
        self.assertIsNotNone(self.flow._currentModel)
        self.assertIsNotNone(self.flow._currentModel.last_params)

        # Simulate model response
        response = AiResponse(
            role=AiRole.Assistant,
            message="The answer is 4.",
        )
        self.flow._currentModel.responseAvailable.emit(response)
        self.flow._currentModel.finished.emit()

        # Verify event was emitted
        self.assertEqual(len(self.emitted_events), 1)
        self.assertEqual(self.emitted_events[0].author, "assistant")
        self.assertEqual(
            self.emitted_events[0].content["message"], "The answer is 4.")

        # Verify flow finished
        self.assertTrue(self.flow_finished)

    def test_run_with_tool_calls(self):
        """Test flow with tool calls."""
        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Show me the git log")

        # Simulate response with tool calls
        tool_calls = [
            {
                "id": "tc-1",
                "type": "function",
                "function": {"name": "git_log", "arguments": "{}"},
            }
        ]
        response = AiResponse(
            role=AiRole.Assistant,
            message="I'll fetch the git log for you.",
            tool_calls=tool_calls,
        )
        self.flow._currentModel.responseAvailable.emit(response)

        # Verify tool machine was called
        self.tool_machine.processToolCalls.assert_called_once_with(tool_calls)

        # Verify events were emitted
        self.assertEqual(len(self.emitted_events), 2)  # message + tool request
        self.assertEqual(self.emitted_events[0].author, "assistant")
        self.assertEqual(self.emitted_events[1].author, "tool_request")
        self.assertEqual(
            self.emitted_events[1].content["tool_name"], "git_log")

    def test_model_override(self):
        """Test model override from agent."""
        agent = LlmAgent(name="TestAgent", modelId="gpt-4-turbo")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Test")

        # Verify gpt-4-turbo was looked up
        self.model_lookup_fn.assert_called_once_with("gpt-4-turbo")

    def test_inherit_parent_model(self):
        """Test model inheritance from parent context."""
        agent = LlmAgent(name="TestAgent")  # No modelId
        ctx = InvocationContext(agent=agent, parentModelId="claude-3")

        self.flow.run(ctx, userPrompt="Test")

        # Verify parent model was looked up
        self.model_lookup_fn.assert_called_once_with("claude-3")

    def test_system_prompt_from_agent(self):
        """Test system prompt from agent override."""
        sys_prompt = "You are a helpful assistant."
        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5",
                         systemPrompt=sys_prompt)
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Hello")

        # Verify system prompt was used
        params = self.flow._currentModel.last_params
        self.assertEqual(params.sys_prompt, sys_prompt)

    def test_continue_after_tools(self):
        """Test continuation after tool execution."""
        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Get git log")

        # Clear the mock to verify continuation call
        self.flow._currentModel.last_params = None

        # Simulate tool completion and continuation
        self.flow.continueAfterTools()

        # Verify continue_only=True was sent
        params = self.flow._currentModel.last_params
        self.assertIsNotNone(params)
        self.assertTrue(params.continue_only)

    def test_tool_loop_state(self):
        """Test tool loop state tracking."""
        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Test")

        # Initially not in tool loop
        self.assertFalse(self.flow._inToolLoop)

        # After tool calls, should be in loop
        tool_calls = [
            {
                "id": "tc-1",
                "type": "function",
                "function": {"name": "git_status", "arguments": "{}"},
            }
        ]
        response = AiResponse(
            role=AiRole.Assistant, message="Running git status", tool_calls=tool_calls)
        self.flow._currentModel.responseAvailable.emit(response)

        self.assertTrue(self.flow._inToolLoop)

    def test_multiple_tool_calls(self):
        """Test multiple tool calls in one response."""
        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Gather information")

        # Simulate response with multiple tool calls
        tool_calls = [
            {
                "id": "tc-1",
                "type": "function",
                "function": {"name": "git_log", "arguments": "{}"},
            },
            {
                "id": "tc-2",
                "type": "function",
                "function": {"name": "git_status", "arguments": "{}"},
            },
        ]
        response = AiResponse(
            role=AiRole.Assistant,
            message="I'll gather information",
            tool_calls=tool_calls,
        )
        self.flow._currentModel.responseAvailable.emit(response)

        # Tool machine should receive all calls
        self.tool_machine.processToolCalls.assert_called_once_with(tool_calls)

        # Should have message + 2 tool requests
        self.assertEqual(len(self.emitted_events), 3)

    def test_reasoning_in_response(self):
        """Test handling reasoning in response."""
        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Complex question")

        response = AiResponse(
            role=AiRole.Assistant,
            message="The answer is...",
            reasoning="Let me think about this...",
        )
        self.flow._currentModel.responseAvailable.emit(response)
        self.flow._currentModel.finished.emit()

        # Should have event with both message and reasoning
        self.assertEqual(len(self.emitted_events), 1)
        self.assertEqual(
            self.emitted_events[0].content["message"], "The answer is...")
        self.assertEqual(
            self.emitted_events[0].content["reasoning"], "Let me think about this...")

    def test_no_model_found(self):
        """Test handling when model lookup fails."""
        # Override lookup to return None for this test
        self.model_lookup_fn.return_value = None

        agent = LlmAgent(name="TestAgent", modelId="unknown-model")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Test")

        # Should emit error event
        self.assertTrue(any(e.author == "system" for e in self.emitted_events))

        # Flow should finish
        self.assertTrue(self.flow_finished)

    def test_build_model_params_basic(self):
        """Test parameter building."""
        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        params = self.flow._buildModelParams(
            ctx, userPrompt="Hello", sysPrompt="Be helpful")

        self.assertEqual(params.prompt, "Hello")
        self.assertEqual(params.sys_prompt, "Be helpful")
        self.assertFalse(params.continue_only)
        self.assertEqual(params.temperature, 0.7)

    def test_build_model_params_continue_only(self):
        """Test parameter building for continuation."""
        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        params = self.flow._buildModelParams(ctx, continue_only=True)

        self.assertEqual(params.prompt, "")
        self.assertTrue(params.continue_only)
        self.assertEqual(params.temperature, 0.1)  # Lower for continuation


if __name__ == "__main__":
    unittest.main()
