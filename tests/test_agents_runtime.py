# -*- coding: utf-8 -*-
"""
Unit tests for agent runtime types.

Tests cover:
- Data structure initialization and validation
- Event actions and transfers
- Invocation context state management
- Agent creation and nesting
- Model ID resolution
"""

import unittest

from qgitc.agents.agentruntime import (
    AgentEvent,
    BaseAgent,
    EventActions,
    InvocationContext,
    LlmAgent,
    SequentialAgent,
    resolveModelId,
)


class TestEventActions(unittest.TestCase):
    """Tests for EventActions dataclass."""

    def test_default_construction(self):
        """EventActions should construct with sensible defaults."""
        actions = EventActions()
        self.assertEqual(actions.state_delta, {})
        self.assertIsNone(actions.transfer_to_agent)
        self.assertFalse(actions.end_of_agent)

    def test_set_transfer(self):
        """setTransfer should set transfer_to_agent."""
        actions = EventActions()
        actions.setTransfer("SubAgent")
        self.assertEqual(actions.transfer_to_agent, "SubAgent")

    def test_set_end_of_agent(self):
        """setEndOfAgent should set end_of_agent flag."""
        actions = EventActions()
        self.assertFalse(actions.end_of_agent)
        actions.setEndOfAgent(True)
        self.assertTrue(actions.end_of_agent)
        actions.setEndOfAgent(False)
        self.assertFalse(actions.end_of_agent)

    def test_state_delta(self):
        """state_delta should be mutable dict."""
        actions = EventActions()
        actions.state_delta["current_step"] = 1
        self.assertEqual(actions.state_delta["current_step"], 1)


class TestAgentEvent(unittest.TestCase):
    """Tests for AgentEvent dataclass."""

    def test_default_construction(self):
        """AgentEvent should auto-generate id and invocationId."""
        event1 = AgentEvent(author="assistant", content={"message": "hello"})
        event2 = AgentEvent(author="assistant", content={"message": "hello"})

        # Each should have unique id and invocationId
        self.assertNotEqual(event1.id, event2.id)
        self.assertNotEqual(event1.invocationId, event2.invocationId)
        self.assertIsNotNone(event1.timestamp)

    def test_set_invocation_id(self):
        """Can set invocationId explicitly."""
        inv_id = "inv-123"
        event = AgentEvent(invocationId=inv_id, author="user")
        self.assertEqual(event.invocationId, inv_id)

    def test_content_and_actions(self):
        """Event can carry content and actions."""
        content = {"message": "test"}
        actions = EventActions()
        actions.setTransfer("SubAgent")

        event = AgentEvent(
            author="assistant",
            content=content,
            actions=actions
        )
        self.assertEqual(event.content, content)
        self.assertEqual(event.actions.transfer_to_agent, "SubAgent")


class TestInvocationContext(unittest.TestCase):
    """Tests for InvocationContext dataclass."""

    def test_default_construction(self):
        """Context should auto-generate invocationId."""
        ctx1 = InvocationContext()
        ctx2 = InvocationContext()
        self.assertNotEqual(ctx1.invocationId, ctx2.invocationId)
        self.assertEqual(ctx1.agentStates, {})
        self.assertEqual(ctx1.endOfAgents, {})

    def test_agent_state_management(self):
        """Can set and get agent state."""
        ctx = InvocationContext()
        state = {"step": 1, "data": "test"}

        ctx.setAgentState("Agent1", state)
        retrieved = ctx.getAgentState("Agent1")
        self.assertEqual(retrieved, state)

    def test_agent_state_missing(self):
        """getAgentState returns empty dict for missing agent."""
        ctx = InvocationContext()
        retrieved = ctx.getAgentState("NonExistent")
        self.assertEqual(retrieved, {})

    def test_agent_finished_tracking(self):
        """Can mark and track agent finish state."""
        ctx = InvocationContext()
        self.assertFalse(ctx.isAgentFinished("Agent1"))

        ctx.markAgentFinished("Agent1")
        self.assertTrue(ctx.isAgentFinished("Agent1"))
        self.assertFalse(ctx.isAgentFinished("Agent2"))

    def test_context_clone(self):
        """clone() should create child context with shared state."""
        parent_agent = LlmAgent(name="Parent")
        child_agent = LlmAgent(name="Child")

        ctx = InvocationContext(
            session="session-123",
            agent=parent_agent,
            parentModelId="gpt-4"
        )
        ctx.setAgentState("Agent1", {"step": 1})

        cloned = ctx.clone(newAgent=child_agent)

        # Invocation and session should be shared
        self.assertEqual(cloned.invocationId, ctx.invocationId)
        self.assertEqual(cloned.session, ctx.session)
        self.assertEqual(cloned.parentModelId, ctx.parentModelId)

        # Agent should be updated
        self.assertEqual(cloned.agent.name, "Child")

        # agentStates should be shared reference (same dict instance)
        self.assertIs(cloned.agentStates, ctx.agentStates)
        self.assertEqual(cloned.getAgentState("Agent1"), {"step": 1})


class TestLlmAgent(unittest.TestCase):
    """Tests for LlmAgent."""

    def test_creation_with_required_fields(self):
        """LlmAgent requires a name."""
        agent = LlmAgent(name="MainAgent")
        self.assertEqual(agent.name, "MainAgent")
        self.assertIsNone(agent.modelId)
        self.assertIsNone(agent.toolNames)
        self.assertIsNone(agent.systemPrompt)

    def test_creation_missing_name(self):
        """LlmAgent without name should raise."""
        with self.assertRaises(ValueError):
            LlmAgent()

    def test_with_optional_overrides(self):
        """LlmAgent can set optional modelId, toolNames, systemPrompt."""
        agent = LlmAgent(
            name="ReviewAgent",
            modelId="gpt-4-turbo",
            toolNames=["code_review", "git_log"],
            systemPrompt="You are a code reviewer."
        )
        self.assertEqual(agent.name, "ReviewAgent")
        self.assertEqual(agent.modelId, "gpt-4-turbo")
        self.assertEqual(agent.toolNames, ["code_review", "git_log"])
        self.assertEqual(agent.systemPrompt, "You are a code reviewer.")

    def test_with_sub_agents(self):
        """LlmAgent can have sub-agents."""
        sub1 = LlmAgent(name="Sub1")
        sub2 = LlmAgent(name="Sub2")
        agent = LlmAgent(name="Main", sub_agents=[sub1, sub2])

        self.assertEqual(len(agent.sub_agents), 2)
        self.assertEqual(agent.sub_agents[0].name, "Sub1")


class TestSequentialAgent(unittest.TestCase):
    """Tests for SequentialAgent."""

    def test_creation_with_sub_agents(self):
        """SequentialAgent requires sub_agents."""
        sub1 = LlmAgent(name="Step1")
        sub2 = LlmAgent(name="Step2")
        agent = SequentialAgent(name="Orchestrator", sub_agents=[sub1, sub2])

        self.assertEqual(agent.name, "Orchestrator")
        self.assertEqual(len(agent.sub_agents), 2)

    def test_creation_empty_sub_agents(self):
        """SequentialAgent with empty sub_agents should raise."""
        with self.assertRaises(ValueError):
            SequentialAgent(name="Empty")

    def test_creation_missing_name(self):
        """SequentialAgent without name should raise."""
        sub = LlmAgent(name="Sub")
        with self.assertRaises(ValueError):
            SequentialAgent(sub_agents=[sub])

    def test_resolve_sub_agent(self):
        """resolveSubAgent should find sub-agent by name."""
        sub1 = LlmAgent(name="First")
        sub2 = LlmAgent(name="Second")
        agent = SequentialAgent(name="Seq", sub_agents=[sub1, sub2])

        found = agent.resolveSubAgent("First")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "First")

        not_found = agent.resolveSubAgent("NonExistent")
        self.assertIsNone(not_found)


class TestResolveModelId(unittest.TestCase):
    """Tests for resolveModelId helper function."""

    def test_explicit_model_on_agent(self):
        """Explicit modelId on LlmAgent takes priority."""
        agent = LlmAgent(name="Test", modelId="gpt-4")
        ctx = InvocationContext(parentModelId="gpt-3.5")

        resolved = resolveModelId(agent, ctx)
        self.assertEqual(resolved, "gpt-4")

    def test_inherit_from_context(self):
        """Inherit parentModelId from context if agent has none."""
        agent = LlmAgent(name="Test")  # No explicit modelId
        ctx = InvocationContext(parentModelId="gpt-3.5")

        resolved = resolveModelId(agent, ctx)
        self.assertEqual(resolved, "gpt-3.5")

    def test_none_when_nothing_set(self):
        """Return None if neither agent nor context has modelId."""
        agent = LlmAgent(name="Test")
        ctx = InvocationContext()  # No parentModelId

        resolved = resolveModelId(agent, ctx)
        self.assertIsNone(resolved)

    def test_none_agent(self):
        """Handle None agent gracefully."""
        ctx = InvocationContext(parentModelId="gpt-4")

        resolved = resolveModelId(None, ctx)
        self.assertEqual(resolved, "gpt-4")

    def test_none_context(self):
        """Handle None context gracefully."""
        agent = LlmAgent(name="Test", modelId="claude-3")

        resolved = resolveModelId(agent, None)
        self.assertEqual(resolved, "claude-3")

    def test_none_context_and_agent(self):
        """Both None should return None."""
        resolved = resolveModelId(None, None)
        self.assertIsNone(resolved)


class TestAgentHierarchy(unittest.TestCase):
    """Tests for agent nesting and parent relationships."""

    def test_agent_hierarchy(self):
        """Can build hierarchy of agents."""
        main = LlmAgent(name="Main")
        sub1 = LlmAgent(name="Sub1", parent_agent=main)
        sub2 = LlmAgent(name="Sub2", parent_agent=main)
        seq = SequentialAgent(name="Orchestrator", sub_agents=[
                              sub1, sub2], parent_agent=main)

        self.assertEqual(sub1.parent_agent.name, "Main")
        self.assertEqual(seq.parent_agent.name, "Main")
        self.assertEqual(len(seq.sub_agents), 2)

    def test_base_agent_repr(self):
        """BaseAgent subclasses have informative repr."""
        agent = LlmAgent(name="TestAgent")
        repr_str = repr(agent)
        self.assertIn("LlmAgent", repr_str)
        self.assertIn("TestAgent", repr_str)


if __name__ == "__main__":
    unittest.main()
