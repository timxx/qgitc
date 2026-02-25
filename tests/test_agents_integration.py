# -*- coding: utf-8 -*-
"""
Integration tests for Agent Framework.

Tests cover:
- Component integration and composition
- Agent structure validation
- Model override mechanism
- Signal and dependency wiring
"""

import unittest
from unittest.mock import Mock

from qgitc.agentmachine import AgentToolMachine
from qgitc.agents.agentrunner import SequentialAgentRunner
from qgitc.agents.agentruntime import InvocationContext, LlmAgent, SequentialAgent
from qgitc.agenttoolexecutor import AgentToolExecutor


class TestAgentFrameworkIntegration(unittest.TestCase):
    """Integration tests for complete agent framework."""

    def setUp(self):
        """Set up test fixtures."""
        # Real tool machine for signal coordination
        self.tool_machine = AgentToolMachine()

        # Mock tool executor
        self.tool_executor = Mock(spec=AgentToolExecutor)

        # Mock model lookup function
        self.mock_model = Mock()
        self.model_lookup_fn = Mock(return_value=self.mock_model)

        # Create runner
        self.runner = SequentialAgentRunner(
            toolMachine=self.tool_machine,
            modelLookupFn=self.model_lookup_fn,
            toolExecutor=self.tool_executor,
        )

        # Event accumulator
        self.events = []
        self.runner.eventEmitted.connect(lambda evt: self.events.append(evt))

        # Completion tracking
        self.finished = False
        self.runner.runFinished.connect(
            lambda: setattr(self, "finished", True))

    def test_runner_initialization(self):
        """Test that runner initializes with all dependencies."""
        self.assertIsNotNone(self.runner)
        self.assertEqual(self.runner._toolMachine, self.tool_machine)
        self.assertEqual(self.runner._modelLookupFn, self.model_lookup_fn)

    def test_single_llm_agent_structure(self):
        """Test creating a single LLM agent within sequential wrapper."""
        main_agent = LlmAgent(
            name="main",
            modelId="gpt-4",
            systemPrompt="You are a helpful assistant.",
        )

        sequential = SequentialAgent(
            name="SingleAgentTest",
            sub_agents=[main_agent],
        )

        # Verify structure
        self.assertEqual(len(sequential.sub_agents), 1)
        self.assertEqual(sequential.sub_agents[0].name, "main")
        self.assertEqual(sequential.sub_agents[0].modelId, "gpt-4")

    def test_multi_agent_structure(self):
        """Test creating multiple agents in sequence."""
        main_agent = LlmAgent(
            name="main",
            modelId="gpt-4",
            systemPrompt="You are a coordinator.",
        )

        review_agent = LlmAgent(
            name="reviewer",
            modelId="gpt-3.5-turbo",
            systemPrompt="You are a code reviewer.",
        )

        sequential = SequentialAgent(
            name="MultiAgentTest",
            sub_agents=[main_agent, review_agent],
        )

        # Verify structure
        self.assertEqual(len(sequential.sub_agents), 2)
        self.assertEqual(sequential.sub_agents[0].modelId, "gpt-4")
        self.assertEqual(sequential.sub_agents[1].modelId, "gpt-3.5-turbo")

    def test_model_override_in_agent(self):
        """Test that agents can override model settings."""
        agent = LlmAgent(
            name="custom",
            modelId="claude-3",
            systemPrompt="Custom prompt",
        )

        self.assertEqual(agent.modelId, "claude-3")
        self.assertEqual(agent.systemPrompt, "Custom prompt")

    def test_context_initialization(self):
        """Test invocation context creation."""
        ctx = InvocationContext()

        self.assertIsNotNone(ctx.invocationId)
        self.assertFalse(ctx.end_invocation)

    def test_tool_machine_signals_exist(self):
        """Test that tool machine has required signals."""
        self.assertTrue(hasattr(self.tool_machine, 'toolExecutionRequested'))
        self.assertTrue(hasattr(self.tool_machine, 'agentContinuationReady'))

    def test_runner_has_required_signals(self):
        """Test that runner exposes required signals."""
        self.assertTrue(hasattr(self.runner, 'eventEmitted'))
        self.assertTrue(hasattr(self.runner, 'runFinished'))

    def test_agent_with_system_prompt_override(self):
        """Test agent with custom system prompt."""
        agent = LlmAgent(
            name="test",
            systemPrompt="You are a specialized assistant."
        )

        self.assertEqual(agent.systemPrompt,
                         "You are a specialized assistant.")

    def test_agent_without_model_override(self):
        """Test agent without explicit model override."""
        agent = LlmAgent(name="test")

        self.assertIsNone(agent.modelId)

    def test_sequential_agent_sub_agent_lookup(self):
        """Test resolving sub-agents by name."""
        sub1 = LlmAgent(name="sub1")
        sub2 = LlmAgent(name="sub2")

        sequential = SequentialAgent(
            name="parent",
            sub_agents=[sub1, sub2],
        )

        found = sequential.resolveSubAgent("sub2")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "sub2")

    def test_sequential_agent_invalid_sub_agent_lookup(self):
        """Test looking up non-existent sub-agent."""
        sub1 = LlmAgent(name="sub1")

        sequential = SequentialAgent(
            name="parent",
            sub_agents=[sub1],
        )

        found = sequential.resolveSubAgent("nonexistent")
        self.assertIsNone(found)

    def test_runner_accepts_tool_executor(self):
        """Test that runner can be created with tool executor."""
        executor = Mock(spec=AgentToolExecutor)
        runner = SequentialAgentRunner(
            toolMachine=self.tool_machine,
            modelLookupFn=self.model_lookup_fn,
            toolExecutor=executor,
        )

        self.assertIsNotNone(runner)

    def test_runner_works_without_tool_executor(self):
        """Test that runner can work without tool executor."""
        runner = SequentialAgentRunner(
            toolMachine=self.tool_machine,
            modelLookupFn=self.model_lookup_fn,
        )

        self.assertIsNotNone(runner)


if __name__ == "__main__":
    unittest.main()
