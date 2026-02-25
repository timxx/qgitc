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
from typing import Dict
from unittest.mock import Mock

from PySide6.QtCore import QObject, Signal

from qgitc.agentmachine import AgentToolMachine
from qgitc.agents.agentruntime import InvocationContext, LlmAgent
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
        # Create real AgentToolMachine for signals (but mock methods)
        self.tool_machine = AgentToolMachine()
        # Mock out the process methods
        self.tool_machine.processToolCalls = Mock()
        self.tool_machine.onToolFinished = Mock()

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


class MockToolExecutor(QObject):
    """Mock tool executor for testing."""

    toolFinished = Signal(object)  # AgentToolResult

    def __init__(self):
        super().__init__()
        self.execute_calls = []

    def execute(self, toolCallId: str, toolName: str, params: Dict):
        """Record execute calls."""
        self.execute_calls.append({
            "toolCallId": toolCallId,
            "toolName": toolName,
            "params": params,
        })


class TestLlmFlowToolExecution(unittest.TestCase):
    """Tests for tool execution handling in LlmFlow."""

    def setUp(self):
        """Set up test fixtures."""
        # Create real AgentToolMachine for signals
        self.tool_machine = AgentToolMachine()
        self.tool_machine.processToolCalls = Mock()
        self.tool_machine.onToolFinished = Mock()

        self.model_lookup_fn = Mock()
        self.mock_model = MockModel()
        self.model_lookup_fn.return_value = self.mock_model

        self.tool_executor = MockToolExecutor()

        self.flow = LlmFlow(
            toolMachine=self.tool_machine,
            modelLookupFn=self.model_lookup_fn,
            toolExecutor=self.tool_executor,
        )

        self.emitted_events = []
        self.flow.eventEmitted.connect(self._onEventEmitted)
        self.flow_finished = False
        self.flow.flowFinished.connect(self._onFlowFinished)

    def _onEventEmitted(self, event):
        self.emitted_events.append(event)

    def _onFlowFinished(self):
        self.flow_finished = True

    def test_tool_execution_requested_signal(self):
        """Tool machine toolExecutionRequested signal triggers tool execution."""
        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Test")

        # Simulate tool execution request from tool machine
        self.flow._onToolExecutionRequested("tc_123", "git_log", {"limit": 10})

        # Verify executor was called
        self.assertEqual(len(self.tool_executor.execute_calls), 1)
        self.assertEqual(
            self.tool_executor.execute_calls[0]["toolCallId"], "tc_123")
        self.assertEqual(
            self.tool_executor.execute_calls[0]["toolName"], "git_log")
        self.assertEqual(
            self.tool_executor.execute_calls[0]["params"], {"limit": 10})

    def test_tool_result_event_emission(self):
        """Tool result triggers event emission."""
        from qgitc.agenttools import AgentToolResult

        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Test")

        # Simulate tool result
        result = AgentToolResult(
            toolCallId="tc_123",
            toolName="git_log",
            ok=True,
            output="commit abc123\\ncommit def456",
        )

        self.flow._onToolFinished(result)

        # Verify event was emitted
        tool_events = [e for e in self.emitted_events if e.author == "tool"]
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(tool_events[0].content["tool_name"], "git_log")
        self.assertEqual(tool_events[0].content["tool_call_id"], "tc_123")
        self.assertEqual(tool_events[0].content["ok"], True)
        self.assertIn("commit abc123", tool_events[0].content["output"])

    def test_tool_machine_notified_of_completion(self):
        """Tool machine onToolFinished is called after tool completes."""
        from qgitc.agenttools import AgentToolResult

        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Test")

        result = AgentToolResult(
            toolCallId="tc_123",
            toolName="git_log",
            ok=True,
            output="commit abc123",
        )

        self.flow._onToolFinished(result)

        # Verify tool machine was notified
        self.tool_machine.onToolFinished.assert_called_once_with(result)

    def test_tool_result_with_error(self):
        """Failed tool execution emits error event."""
        from qgitc.agenttools import AgentToolResult

        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Test")

        result = AgentToolResult(
            toolCallId="tc_456",
            toolName="git_commit",
            ok=False,
            output="Error: No changes to commit",
        )

        self.flow._onToolFinished(result)

        # Verify error event was emitted
        tool_events = [e for e in self.emitted_events if e.author == "tool"]
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(tool_events[0].content["ok"], False)
        self.assertIn("Error", tool_events[0].content["output"])

    def test_multiple_tools_in_sequence(self):
        """Multiple tools are executed and emit events in sequence."""
        from qgitc.agenttools import AgentToolResult

        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Test")

        # Request multiple tools
        self.flow._onToolExecutionRequested("tc_1", "git_status", {})
        self.flow._onToolExecutionRequested("tc_2", "git_log", {"limit": 5})
        self.flow._onToolExecutionRequested("tc_3", "git_diff", {})

        # Verify all were submitted to executor
        self.assertEqual(len(self.tool_executor.execute_calls), 3)

        # Simulate results arriving out of order
        result2 = AgentToolResult(
            toolCallId="tc_2", toolName="git_log", ok=True, output="log")
        result1 = AgentToolResult(
            toolCallId="tc_1", toolName="git_status", ok=True, output="status")
        result3 = AgentToolResult(
            toolCallId="tc_3", toolName="git_diff", ok=True, output="diff")

        self.flow._onToolFinished(result2)
        self.flow._onToolFinished(result1)
        self.flow._onToolFinished(result3)

        # Verify all tool events were emitted
        tool_events = [e for e in self.emitted_events if e.author == "tool"]
        self.assertEqual(len(tool_events), 3)

        # Verify tool machine was notified for each
        self.assertEqual(self.tool_machine.onToolFinished.call_count, 3)

    def test_tool_execution_without_executor(self):
        """Tool execution without executor emits error event."""
        from qgitc.agenttools import AgentToolResult

        # Create flow without executor
        flow = LlmFlow(
            toolMachine=self.tool_machine,
            modelLookupFn=self.model_lookup_fn,
            toolExecutor=None,
        )

        emitted_events = []
        flow.eventEmitted.connect(lambda e: emitted_events.append(e))

        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        flow.run(ctx, userPrompt="Test")

        # Simulate tool request (should fail gracefully)
        flow._onToolExecutionRequested("tc_123", "git_log", {})

        # Verify error result event was emitted
        tool_events = [e for e in emitted_events if e.author == "tool"]
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(tool_events[0].content["ok"], False)
        self.assertIn("not configured", tool_events[0].content["output"])

        # Verify tool machine was still notified (with failure)
        self.tool_machine.onToolFinished.assert_called_once()
        called_result = self.tool_machine.onToolFinished.call_args[0][0]
        self.assertEqual(called_result.ok, False)

    def test_tool_call_description_formatting(self):
        """Tool result event includes formatted description."""
        from qgitc.agenttools import AgentToolResult

        agent = LlmAgent(name="TestAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.flow.run(ctx, userPrompt="Test")

        # Success result
        result_ok = AgentToolResult(
            toolCallId="tc_1",
            toolName="git_status",
            ok=True,
            output="clean",
        )
        self.flow._onToolFinished(result_ok)

        tool_event = [e for e in self.emitted_events if e.author == "tool"][0]
        self.assertIn("✓", tool_event.content["description"])
        self.assertIn("git_status", tool_event.content["description"])

        # Failure result
        result_fail = AgentToolResult(
            toolCallId="tc_2",
            toolName="git_commit",
            ok=False,
            output="error",
        )
        self.flow._onToolFinished(result_fail)

        tool_events = [e for e in self.emitted_events if e.author == "tool"]
        self.assertEqual(len(tool_events), 2)
        self.assertIn("✗", tool_events[1].content["description"])
        self.assertIn("git_commit", tool_events[1].content["description"])
