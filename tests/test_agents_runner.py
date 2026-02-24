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
    SequentialAgent,
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

    def test_sequential_agent_auto_starts_first_subagent(self):
        """SequentialAgent should automatically start with its first sub-agent."""
        first = LlmAgent(name="FirstAgent", modelId="gpt-3.5")
        second = LlmAgent(name="SecondAgent", modelId="gpt-3.5")
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[first, second],
        )
        ctx = InvocationContext(agent=main_agent)

        self.runner.run(main_agent, ctx, userPrompt="Start")

        # Should have auto-started with first sub-agent
        self.assertEqual(self.runner._currentAgent.name, "FirstAgent")
        self.assertEqual(ctx.agent.name, "FirstAgent")
        # Flow should have been called once
        self.assertEqual(len(self.mock_flow.run_calls), 1)

    def test_agent_switched_on_transfer(self):
        """Agent should switch on transfer with SequentialAgent parent."""
        # Create sub-agents
        sub_agent = LlmAgent(name="SubAgent", modelId="gpt-3.5")
        # Use SequentialAgent as root - it will auto-start first sub-agent
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[
                LlmAgent(name="FirstAgent", modelId="gpt-3.5"), sub_agent],
        )
        ctx = InvocationContext(agent=main_agent)

        self.runner.run(main_agent, ctx, userPrompt="Start")

        # Should auto-start with first sub-agent (FirstAgent)
        self.assertEqual(self.runner._currentAgent.name, "FirstAgent")

        # Emit transfer event to SubAgent
        actions = EventActions()
        actions.setTransfer("SubAgent")
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={"message": "Transferring"},
            actions=actions,
        )

        self.mock_flow.eventEmitted.emit(event)

        # Current agent should switch to SubAgent
        self.assertEqual(self.runner._currentAgent.name, "SubAgent")
        # Context should be updated
        self.assertEqual(ctx.agent.name, "SubAgent")
        # Flow should be called twice (FirstAgent + SubAgent)
        self.assertEqual(len(self.mock_flow.run_calls), 2)

    def test_transfer_to_invalid_subagent(self):
        """Transfer to non-existent sub-agent should log warning and finish."""
        sub_agent = LlmAgent(name="ValidAgent", modelId="gpt-3.5")
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[sub_agent],
        )
        ctx = InvocationContext(agent=main_agent)

        self.runner.run(main_agent, ctx)

        # Should auto-start with ValidAgent
        self.assertEqual(self.runner._currentAgent.name, "ValidAgent")

        # Emit transfer to invalid agent
        actions = EventActions()
        actions.setTransfer("InvalidAgent")
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions,
        )

        self.mock_flow.eventEmitted.emit(event)

        # Should emit the transfer event anyway
        self.assertEqual(len(self.emitted_events), 1)
        # Runner should finish (failed transfer)
        self.assertTrue(self.run_finished)
        # Current agent should not change from ValidAgent
        self.assertEqual(self.runner._currentAgent.name, "ValidAgent")

    def test_multiple_transfers_in_sequence(self):
        """Test multiple transfers between sub-agents."""
        sub1 = LlmAgent(name="Agent1", modelId="gpt-3.5")
        sub2 = LlmAgent(name="Agent2", modelId="gpt-3.5")
        sub3 = LlmAgent(name="Agent3", modelId="gpt-3.5")
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[sub1, sub2, sub3],
        )
        ctx = InvocationContext(agent=main_agent)

        self.runner.run(main_agent, ctx)

        # Should start with Agent1
        self.assertEqual(self.runner._currentAgent.name, "Agent1")

        # Transfer to Agent2
        actions1 = EventActions()
        actions1.setTransfer("Agent2")
        event1 = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={"step": 1},
            actions=actions1,
        )
        self.mock_flow.eventEmitted.emit(event1)

        self.assertEqual(self.runner._currentAgent.name, "Agent2")

        # Transfer to Agent3
        actions2 = EventActions()
        actions2.setTransfer("Agent3")
        event2 = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={"step": 2},
            actions=actions2,
        )
        self.mock_flow.eventEmitted.emit(event2)

        self.assertEqual(self.runner._currentAgent.name, "Agent3")
        # Should have 2 transfer events
        self.assertEqual(len(self.emitted_events), 2)
        # Flow should be called 3 times (Agent1 + 2 transfers)
        self.assertEqual(len(self.mock_flow.run_calls), 3)

    def test_context_state_preserved_across_transfer(self):
        """Context state should be preserved and updated across transfers."""
        sub_agent = LlmAgent(name="SubAgent", modelId="gpt-3.5")
        first_agent = LlmAgent(name="FirstAgent", modelId="gpt-3.5")
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[first_agent, sub_agent],
        )
        ctx = InvocationContext(agent=main_agent)

        self.runner.run(main_agent, ctx)

        # Should start with FirstAgent
        self.assertEqual(self.runner._currentAgent.name, "FirstAgent")

        # Emit event with state_delta before transfer
        actions = EventActions()
        actions.state_delta = {"key": "value", "count": 42}
        actions.setTransfer("SubAgent")
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions,
        )

        self.mock_flow.eventEmitted.emit(event)

        # FirstAgent state should have been updated
        first_state = ctx.getAgentState("FirstAgent")
        self.assertEqual(first_state.get("key"), "value")
        self.assertEqual(first_state.get("count"), 42)

    def test_end_of_agent_marks_agent_finished(self):
        """end_of_agent flag should mark agent as finished in context."""
        agent = LlmAgent(name="MainAgent", modelId="gpt-3.5")
        ctx = InvocationContext(agent=agent)

        self.runner.run(agent, ctx)

        # Emit event with end_of_agent
        actions = EventActions()
        actions.end_of_agent = True
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={"final": "message"},
            actions=actions,
        )

        self.mock_flow.eventEmitted.emit(event)

        # Agent should be marked as finished
        self.assertTrue(ctx.isAgentFinished("MainAgent"))

    def test_end_of_agent_with_transfer(self):
        """end_of_agent + transfer should mark current agent finished and switch."""
        sub_agent = LlmAgent(name="SubAgent", modelId="gpt-3.5")
        first_agent = LlmAgent(name="FirstAgent", modelId="gpt-3.5")
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[first_agent, sub_agent],
        )
        ctx = InvocationContext(agent=main_agent)

        self.runner.run(main_agent, ctx)

        # Should start with FirstAgent
        self.assertEqual(self.runner._currentAgent.name, "FirstAgent")

        # Emit transfer with end_of_agent
        actions = EventActions()
        actions.end_of_agent = True
        actions.setTransfer("SubAgent")
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions,
        )

        self.mock_flow.eventEmitted.emit(event)

        # FirstAgent should be finished
        self.assertTrue(ctx.isAgentFinished("FirstAgent"))
        # Should transfer to SubAgent
        self.assertEqual(self.runner._currentAgent.name, "SubAgent")

    def test_transfer_with_system_prompt_override(self):
        """Transfer with sys_prompt in state_delta should pass it to next agent."""
        sub_agent = LlmAgent(name="SubAgent", modelId="gpt-3.5")
        first_agent = LlmAgent(name="FirstAgent", modelId="gpt-3.5")
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[first_agent, sub_agent],
        )
        ctx = InvocationContext(agent=main_agent)

        self.runner.run(main_agent, ctx)

        # Should start with FirstAgent
        self.assertEqual(self.runner._currentAgent.name, "FirstAgent")

        # Transfer with system prompt override
        actions = EventActions()
        actions.state_delta = {"sys_prompt": "You are a code reviewer"}
        actions.setTransfer("SubAgent")
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions,
        )

        self.mock_flow.eventEmitted.emit(event)

        # SubAgent should be called with the system prompt
        self.assertEqual(len(self.mock_flow.run_calls), 2)
        sub_agent_call = self.mock_flow.run_calls[1]
        self.assertEqual(
            sub_agent_call["sysPrompt"], "You are a code reviewer")
        # No user prompt on transfer
        self.assertEqual(sub_agent_call["userPrompt"], "")

    # ========================================================================
    # Model Override Tests
    # ========================================================================

    def test_subagent_with_different_model(self):
        """Sub-agent can specify different model than parent."""
        first_agent = LlmAgent(name="FirstAgent", modelId="gpt-3.5-turbo")
        sub_agent = LlmAgent(name="SubAgent", modelId="gpt-4-turbo")
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[first_agent, sub_agent],
        )
        ctx = InvocationContext(agent=main_agent)

        self.runner.run(main_agent, ctx)

        # FirstAgent should use gpt-3.5-turbo
        first_call = self.mock_flow.run_calls[0]
        self.assertEqual(first_call["ctx"].agent.modelId, "gpt-3.5-turbo")

        # Transfer to SubAgent
        actions = EventActions()
        actions.setTransfer("SubAgent")
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions,
        )
        self.mock_flow.eventEmitted.emit(event)

        # SubAgent should use gpt-4-turbo
        second_call = self.mock_flow.run_calls[1]
        self.assertEqual(second_call["ctx"].agent.modelId, "gpt-4-turbo")

    def test_model_inheritance_through_parent_context(self):
        """Sub-agent without explicit modelId inherits from parent context."""
        first_agent = LlmAgent(name="FirstAgent", modelId="claude-3")
        sub_agent = LlmAgent(name="SubAgent")  # No explicit modelId
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[first_agent, sub_agent],
        )
        # Set parent model in context
        ctx = InvocationContext(agent=main_agent, parentModelId="gpt-3.5")

        self.runner.run(main_agent, ctx)

        # FirstAgent should use explicit model
        first_call = self.mock_flow.run_calls[0]
        self.assertEqual(first_call["ctx"].agent.modelId, "claude-3")

        # Transfer to SubAgent (no explicit model)
        actions = EventActions()
        actions.setTransfer("SubAgent")
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions,
        )
        self.mock_flow.eventEmitted.emit(event)

        # SubAgent has no explicit model, context still has parentModelId
        second_call = self.mock_flow.run_calls[1]
        self.assertIsNone(second_call["ctx"].agent.modelId)
        self.assertEqual(second_call["ctx"].parentModelId, "gpt-3.5")

    def test_model_override_chain_with_transfer(self):
        """Model overrides work correctly through multiple transfers."""
        agent1 = LlmAgent(name="Agent1", modelId="gpt-3.5")
        agent2 = LlmAgent(name="Agent2", modelId="gpt-4")
        agent3 = LlmAgent(name="Agent3")  # Inherits from parent
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[agent1, agent2, agent3],
        )
        ctx = InvocationContext(agent=main_agent, parentModelId="claude-3")

        self.runner.run(main_agent, ctx)

        # Agent1 uses gpt-3.5
        self.assertEqual(
            self.mock_flow.run_calls[0]["ctx"].agent.modelId, "gpt-3.5")

        # Transfer to Agent2
        actions1 = EventActions()
        actions1.setTransfer("Agent2")
        self.mock_flow.eventEmitted.emit(AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions1,
        ))

        # Agent2 uses gpt-4
        self.assertEqual(
            self.mock_flow.run_calls[1]["ctx"].agent.modelId, "gpt-4")

        # Transfer to Agent3
        actions2 = EventActions()
        actions2.setTransfer("Agent3")
        self.mock_flow.eventEmitted.emit(AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions2,
        ))

        # Agent3 has no explicit model, inherits from parent context (claude-3)
        self.assertIsNone(self.mock_flow.run_calls[2]["ctx"].agent.modelId)
        self.assertEqual(
            self.mock_flow.run_calls[2]["ctx"].parentModelId, "claude-3")

    def test_all_agents_inherit_parent_model(self):
        """Multiple agents without explicit modelId all inherit from parent."""
        agent1 = LlmAgent(name="Agent1")
        agent2 = LlmAgent(name="Agent2")
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[agent1, agent2],
        )
        ctx = InvocationContext(agent=main_agent, parentModelId="gpt-4o")

        self.runner.run(main_agent, ctx)

        # Agent1 inherits
        self.assertIsNone(self.mock_flow.run_calls[0]["ctx"].agent.modelId)
        self.assertEqual(
            self.mock_flow.run_calls[0]["ctx"].parentModelId, "gpt-4o")

        # Transfer to Agent2
        actions = EventActions()
        actions.setTransfer("Agent2")
        self.mock_flow.eventEmitted.emit(AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions,
        ))

        # Agent2 also inherits
        self.assertIsNone(self.mock_flow.run_calls[1]["ctx"].agent.modelId)
        self.assertEqual(
            self.mock_flow.run_calls[1]["ctx"].parentModelId, "gpt-4o")

    def test_model_override_independent_of_other_state(self):
        """Model override works independently of other state changes."""
        first_agent = LlmAgent(name="FirstAgent", modelId="gpt-3.5")
        sub_agent = LlmAgent(name="SubAgent", modelId="claude-3")
        main_agent = SequentialAgent(
            name="MainAgent",
            sub_agents=[first_agent, sub_agent],
        )
        ctx = InvocationContext(agent=main_agent)

        self.runner.run(main_agent, ctx)

        # Transfer with state_delta and system prompt
        actions = EventActions()
        actions.state_delta = {
            "custom_key": "custom_value",
            "sys_prompt": "Special instructions"
        }
        actions.setTransfer("SubAgent")
        event = AgentEvent(
            invocationId=ctx.invocationId,
            author="assistant",
            content={},
            actions=actions,
        )
        self.mock_flow.eventEmitted.emit(event)

        # SubAgent should still use its own model despite state changes
        second_call = self.mock_flow.run_calls[1]
        self.assertEqual(second_call["ctx"].agent.modelId, "claude-3")
        # State should be preserved
        first_state = ctx.getAgentState("FirstAgent")
        self.assertEqual(first_state.get("custom_key"), "custom_value")


if __name__ == "__main__":
    unittest.main()
