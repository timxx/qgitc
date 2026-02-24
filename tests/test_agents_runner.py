# -*- coding: utf-8 -*-
"""
Unit tests for Agent Runner.

Tests cover:
- Single LLM agent execution
- Event accumulation and emission
- Agent state tracking
- Transfer between agents (when applicable)
- Flow integration
"""

import unittest
from unittest.mock import MagicMock, Mock

from PySide6.QtCore import QObject, Signal

from qgitc.agentmachine import AgentToolMachine
from qgitc.agents.agentrunner import AgentRunner, SequentialAgentRunner
from qgitc.agents.agentruntime import (
    AgentEvent,
    EventActions,
    InvocationContext,
    LlmAgent,
)


class MockLlmFlow(QObject):
    """Mock LLM flow for testing."""

    eventEmitted = Signal(object)  # AgentEvent
    flowFinished = Signal()

    def __init__(self):
        super().__init__()
        self.run_calls = []

    def run(self, ctx, userPrompt="", sysPrompt=None):
        """Record run parameters."""
        self.run_calls.append({
            "ctx": ctx,
            "userPrompt": userPrompt,
            "sysPrompt": sysPrompt,
        })


class TestSequentialAgentRunner(unittest.TestCase):
    """Tests for SequentialAgentRunner."""

    def setUp(self):
        """Set up test fixtures."""
        self.tool_machine = Mock(spec=AgentToolMachine)
        self.model_lookup_fn = Mock()

        # Create a mock flow factory
        self.mock_flow = MockLlmFlow()
        self.flow_factory = lambda: self.mock_flow

        self.runner = SequentialAgentRunner(
            toolMachine=self.tool_machine,
            modelLookupFn=self.model_lookup_fn,
            flowFactory=self.flow_factory,
        )

        # Collect emitted events
        self.emitted_events = []
        self.runner.eventEmitted.connect(self._onEventEmitted)
        self.run_finished = False
        self.runner.runFinished.connect(self._onRunFinished)

    def _onEventEmitted(self, event):
        """Collect emitted events."""
        self.emitted_events.append(event)

    def _onRunFinished(self):
        """Mark run as finished."""
        self.run_finished = True

    def test_create_with_default_params(self):
        """SequentialAgentRunner should create with required parameters."""
        runner = SequentialAgentRunner(toolMachine=self.tool_machine)
        self.assertIsNotNone(runner)

    def test_run_single_llm_agent(self):
        """Test running a single LLM agent."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.runner.run(agent, ctx, userPrompt="Hello")

        # Verify flow was created and run was called
        self.assertIsNotNone(self.runner._flow)
        self.assertIsNotNone(self.runner._currentAgent)
        self.assertEqual(self.runner._currentAgent.name, "MainAgent")

    def test_emit_normal_event(self):
        """Test emitting a normal event (no transfer)."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.runner.run(agent, ctx, userPrompt="Test")

        # Emit a normal event from the flow
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={"message": "Hello"},
        )
        self.mock_flow.eventEmitted.emit(event)

        # Verify event was forwarded
        self.assertEqual(len(self.emitted_events), 1)
        self.assertEqual(self.emitted_events[0].author, "assistant")

    def test_context_agent_updated(self):
        """Context.agent should be updated to current agent."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext()

        self.runner.run(agent, ctx, userPrompt="Test")

        # Agent should be updated in context
        self.assertEqual(ctx.agent.name, "MainAgent")

    def test_flow_signals_connected(self):
        """Flow signals should be connected properly."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.runner.run(agent, ctx)

        # Emit flow finished
        self.assertFalse(self.run_finished)
        self.mock_flow.flowFinished.emit()
        self.assertTrue(self.run_finished)

    def test_user_prompt_forwarded(self):
        """User prompt should be forwarded to flow."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        user_prompt = "What time is it?"
        self.runner.run(agent, ctx, userPrompt=user_prompt)

        # Check flow run was called with correct prompt
        self.assertEqual(len(self.runner._flow.run_calls), 1)
        self.assertEqual(
            self.runner._flow.run_calls[0]["userPrompt"], user_prompt)

    def test_system_prompt_forwarded(self):
        """System prompt override should be forwarded to flow."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        sys_prompt = "You are helpful."
        self.runner.run(agent, ctx, sysPrompt=sys_prompt)

        # Check flow run was called with correct system prompt
        self.assertEqual(
            self.runner._flow.run_calls[0]["sysPrompt"], sys_prompt)

    def test_agent_state_in_context(self):
        """Agent state should be tracked in context."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.runner.run(agent, ctx)

        # Current agent should be in context
        self.assertEqual(ctx.agent, agent)

    def test_multiple_events_accumulated(self):
        """Multiple events should be accumulated."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.runner.run(agent, ctx)

        # Emit multiple events
        for i in range(3):
            event = AgentEvent(
                invocationId=ctx.invocationId,
                author="assistant",
                content={"message": f"Message {i}"},
            )
            self.mock_flow.eventEmitted.emit(event)

        self.assertEqual(len(self.emitted_events), 3)

    def test_transfer_action_handled(self):
        """Transfer action should be processed."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.runner.run(agent, ctx)

        # Emit event with transfer action
        actions = EventActions()
        actions.setTransfer("SubAgent")
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions,
        )

        self.mock_flow.eventEmitted.emit(event)

        # Transfer event should be emitted
        self.assertEqual(len(self.emitted_events), 1)
        self.assertEqual(
            self.emitted_events[0].actions.transfer_to_agent, "SubAgent")

    def test_multiple_events_then_finish(self):
        """Multiple events followed by finish."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.runner.run(agent, ctx)

        # Emit events
        event1 = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={"message": "Part 1"},
        )
        event2 = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={"message": "Part 2"},
        )

        self.mock_flow.eventEmitted.emit(event1)
        self.mock_flow.eventEmitted.emit(event2)

        self.assertFalse(self.run_finished)
        self.mock_flow.flowFinished.emit()

        # Should have events and then finish
        self.assertEqual(len(self.emitted_events), 2)
        self.assertTrue(self.run_finished)

    def test_agent_switched_on_transfer(self):
        """Agent should switch on transfer (with SequentialAgent parent)."""
        # This would be more complex - test is prepared for Step 4
        pass


if __name__ == "__main__":
    unittest.main()
