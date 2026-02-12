# -*- coding: utf-8 -*-

"""Unit tests for AgentToolMachine orchestrator.

Tests cover:
- Strategy pattern behavior
- Parallel execution
- Tool grouping and batch completion
- Out-of-order completion handling
- Edge cases

Note: No Qt Application required - tests use headless QObject.
"""

import unittest
from typing import Dict
from unittest.mock import Mock, patch

from qgitc.agentmachine import (
    AgentToolMachine,
    AggressiveStrategy,
    CustomStrategy,
    DefaultStrategy,
    SafeStrategy,
    ToolRequest,
    parseToolArguments,
)
from qgitc.agenttoolexecutor import AgentToolResult
from qgitc.agenttools import AgentTool, ToolType
from tests.base import TestBase

# ============================================================================
# Test Fixtures
# ============================================================================


def createMockTool(
    name: str,
    toolType: int = ToolType.READ_ONLY,
    description: str = "Test tool"
) -> AgentTool:
    """Create a mock AgentTool for testing."""
    return AgentTool(
        name=name,
        description=description,
        toolType=toolType,
        parameters={}
    )


def createToolCall(
    toolName: str,
    toolCallId: str = "call_1",
    arguments: str = "{}"
) -> Dict:
    """Create a mock OpenAI-format tool call."""
    return {
        "id": toolCallId,
        "type": "function",
        "function": {
            "name": toolName,
            "arguments": arguments
        }
    }


# ============================================================================
# Helper Functions Tests
# ============================================================================

class TestParseToolArguments(unittest.TestCase):
    """Test parseToolArguments helper function."""

    def test_valid_json(self):
        """Parse valid JSON string."""
        result = parseToolArguments('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_empty_string(self):
        """Empty string returns empty dict."""
        result = parseToolArguments("")
        self.assertEqual(result, {})

    def test_none(self):
        """None returns empty dict."""
        result = parseToolArguments(None)
        self.assertEqual(result, {})

    def test_invalid_json(self):
        """Invalid JSON returns empty dict (no crash)."""
        result = parseToolArguments('not json')
        self.assertEqual(result, {})

    def test_non_dict_json(self):
        """JSON array returns empty dict."""
        result = parseToolArguments('[1, 2, 3]')
        self.assertEqual(result, {})


# ============================================================================
# Strategy Tests
# ============================================================================

class TestDefaultStrategy(unittest.TestCase):
    """Test DefaultStrategy: auto-run READ_ONLY only."""

    def setUp(self):
        self.strategy = DefaultStrategy()

    def test_auto_run_readonly(self):
        """READ_ONLY tools auto-run."""
        result = self.strategy.shouldAutoRun(
            "git_status", ToolType.READ_ONLY, {})
        self.assertTrue(result)

    def test_manual_approval_write(self):
        """WRITE tools require approval."""
        result = self.strategy.shouldAutoRun("git_commit", ToolType.WRITE, {})
        self.assertFalse(result)

    def test_manual_approval_dangerous(self):
        """DANGEROUS tools require approval."""
        result = self.strategy.shouldAutoRun(
            "git_reset", ToolType.DANGEROUS, {})
        self.assertFalse(result)


class TestAggressiveStrategy(unittest.TestCase):
    """Test AggressiveStrategy: auto-run READ_ONLY + WRITE."""

    def setUp(self):
        self.strategy = AggressiveStrategy()

    def test_auto_run_readonly(self):
        """READ_ONLY tools auto-run."""
        result = self.strategy.shouldAutoRun(
            "git_status", ToolType.READ_ONLY, {})
        self.assertTrue(result)

    def test_auto_run_write(self):
        """WRITE tools auto-run (differs from Default)."""
        result = self.strategy.shouldAutoRun("git_commit", ToolType.WRITE, {})
        self.assertTrue(result)

    def test_manual_approval_dangerous(self):
        """DANGEROUS tools still require approval."""
        result = self.strategy.shouldAutoRun(
            "git_reset", ToolType.DANGEROUS, {})
        self.assertFalse(result)


class TestSafeStrategy(unittest.TestCase):
    """Test SafeStrategy: require approval for all."""

    def setUp(self):
        self.strategy = SafeStrategy()

    def test_manual_readonly(self):
        """Even READ_ONLY requires approval."""
        result = self.strategy.shouldAutoRun(
            "git_status", ToolType.READ_ONLY, {})
        self.assertFalse(result)

    def test_manual_write(self):
        """WRITE requires approval."""
        result = self.strategy.shouldAutoRun("git_commit", ToolType.WRITE, {})
        self.assertFalse(result)

    def test_manual_dangerous(self):
        """DANGEROUS requires approval."""
        result = self.strategy.shouldAutoRun(
            "git_reset", ToolType.DANGEROUS, {})
        self.assertFalse(result)


class TestCustomStrategy(unittest.TestCase):
    """Test CustomStrategy: whitelist-based."""

    def test_whitelisted_auto_runs(self):
        """Tools in whitelist auto-run."""
        strategy = CustomStrategy(["git_status", "git_log"])
        self.assertTrue(strategy.shouldAutoRun(
            "git_status", ToolType.WRITE, {}))

    def test_non_whitelisted_requires_approval(self):
        """Tools not in whitelist require approval."""
        strategy = CustomStrategy(["git_status"])
        self.assertFalse(strategy.shouldAutoRun(
            "git_commit", ToolType.READ_ONLY, {}))

    def test_add_remove_tools(self):
        """Can add/remove tools at runtime."""
        strategy = CustomStrategy()

        # Initially not whitelisted
        self.assertFalse(strategy.shouldAutoRun(
            "git_status", ToolType.READ_ONLY, {}))

        # Add to whitelist
        strategy.addAutoRunTool("git_status")
        self.assertTrue(strategy.shouldAutoRun(
            "git_status", ToolType.READ_ONLY, {}))

        # Remove from whitelist
        strategy.removeAutoRunTool("git_status")
        self.assertFalse(strategy.shouldAutoRun(
            "git_status", ToolType.READ_ONLY, {}))


# ============================================================================
# AgentToolMachine Tests
# ============================================================================

class TestAgentToolMachineBasics(unittest.TestCase):
    """Test basic AgentToolMachine functionality."""

    def setUp(self):
        self.machine = AgentToolMachine(strategy=DefaultStrategy())

    def test_initialization(self):
        """Machine initializes with correct defaults."""
        self.assertIsNotNone(self.machine._strategy)
        self.assertEqual(self.machine._maxConcurrent, 4)
        self.assertTrue(self.machine.readyToContinue())
        self.assertFalse(self.machine.hasPendingResults())

    def test_set_strategy(self):
        """Can change strategy at runtime."""
        self.machine.setStrategy(AggressiveStrategy())
        self.assertIsInstance(self.machine._strategy, AggressiveStrategy)

    def test_set_max_concurrent(self):
        """Can change maxConcurrent at runtime."""
        self.machine.setMaxConcurrent(8)
        self.assertEqual(self.machine._maxConcurrent, 8)

    def test_set_max_concurrent_minimum(self):
        """maxConcurrent must be at least 1."""
        self.machine.setMaxConcurrent(0)
        self.assertEqual(self.machine._maxConcurrent, 1)

    def test_reset(self):
        """Reset clears all state."""
        self.machine._awaitingToolResults.add("call_1")
        self.machine._toolQueue.append(Mock())

        self.machine.reset()

        self.assertEqual(len(self.machine._awaitingToolResults), 0)
        self.assertEqual(len(self.machine._toolQueue), 0)
        self.assertEqual(self.machine._nextAutoGroupId, 1)


class TestAgentToolMachineProcessing(unittest.TestCase):
    """Test tool call processing."""

    def setUp(self):
        self.machine = AgentToolMachine(strategy=DefaultStrategy())

        # Mock the tool registry
        self.patcher = patch('qgitc.agentmachine.AgentToolRegistry')
        self.mock_registry = self.patcher.start()
        self.mock_registry.tool_by_name.return_value = None

    def tearDown(self):
        self.patcher.stop()

    def test_empty_tool_calls(self):
        """Empty tool calls list is handled gracefully."""
        self.machine.processToolCalls([])
        self.assertTrue(self.machine.readyToContinue())

    def test_none_tool_calls(self):
        """None tool calls is handled gracefully."""
        self.machine.processToolCalls(None)
        self.assertTrue(self.machine.readyToContinue())

    def test_auto_run_tool_queued(self):
        """Auto-run tools are queued for execution."""
        toolCall = createToolCall("git_status", "call_1")

        # Mock tool as READ_ONLY
        tool = createMockTool("git_status", ToolType.READ_ONLY)
        self.mock_registry.tool_by_name.return_value = tool

        self.machine.processToolCalls([toolCall])

        self.assertEqual(len(self.machine._toolQueue), 1)
        self.assertTrue(self.machine.hasPendingResults())

    def test_confirmation_tool_signal(self):
        """Non-auto tools emit userConfirmationNeeded signal."""
        toolCall = createToolCall("git_commit", "call_1")

        # Mock tool as WRITE
        tool = createMockTool("git_commit", ToolType.WRITE)
        self.mock_registry.tool_by_name.return_value = tool

        signal_emitted = []
        self.machine.userConfirmationNeeded.connect(
            lambda *args: signal_emitted.append(args)
        )

        self.machine.processToolCalls([toolCall])

        self.assertEqual(len(signal_emitted), 1)
        self.assertEqual(signal_emitted[0][0], "git_commit")  # toolName


class TestAgentToolMachineApproval(unittest.TestCase):
    """Test tool approval/rejection."""

    def setUp(self):
        self.machine = AgentToolMachine()

        self.patcher = patch('qgitc.agentmachine.AgentToolRegistry')
        self.mock_registry = self.patcher.start()
        self.mock_registry.tool_by_name.return_value = None

    def tearDown(self):
        self.patcher.stop()

    def test_approve_queues_tool(self):
        """approveToolExecution queues the tool."""
        self.machine.approveToolExecution("git_commit", {}, "call_1")

        self.assertEqual(len(self.machine._toolQueue), 1)
        self.assertTrue(self.machine.hasPendingResults())

    def test_reject_ignores_tool(self):
        """rejectToolExecution ignores the tool."""
        self.machine._awaitingToolResults.add("call_1")

        self.machine.rejectToolExecution("git_commit", "call_1")

        self.assertTrue("call_1" in self.machine._ignoredToolCallIds)
        self.assertFalse("call_1" in self.machine._awaitingToolResults)


class TestAgentToolMachineExecution(TestBase):
    """Test tool execution flow."""

    def doCreateRepo(self):
        pass

    def setUp(self):
        super().setUp()
        self.machine = AgentToolMachine(maxConcurrent=2)

        self.patcher = patch('qgitc.agentmachine.AgentToolRegistry')
        self.mock_registry = self.patcher.start()
        self.mock_registry.tool_by_name.return_value = createMockTool(
            "git_status")

    def tearDown(self):
        self.patcher.stop()
        super().tearDown()

    def test_tool_execution_requested_signal(self):
        """toolExecutionRequested emitted for each executing tool."""
        toolCall = createToolCall("git_status", "call_1")

        signal_emitted = []
        self.machine.toolExecutionRequested.connect(
            lambda *args: signal_emitted.append(args)
        )

        self.machine.processToolCalls([toolCall])
        self.processEvents()

        self.assertEqual(len(signal_emitted), 1)
        self.assertEqual(signal_emitted[0][0], "git_status")
        self.assertEqual(signal_emitted[0][2], "call_1")

    def test_parallel_execution(self):
        """Multiple tools execute up to maxConcurrent limit."""
        self.machine.setMaxConcurrent(2)

        toolCalls = [
            createToolCall("git_status", "call_1"),
            createToolCall("git_log", "call_2"),
            createToolCall("git_diff", "call_3"),
        ]

        signal_emitted = []
        self.machine.toolExecutionRequested.connect(
            lambda *args: signal_emitted.append(args[2])  # toolCallId
        )

        self.machine.processToolCalls(toolCalls)
        self.processEvents()

        # Should execute 2 immediately, 1 queued
        self.assertEqual(len(self.machine._inProgress), 2)
        self.assertEqual(len(self.machine._toolQueue), 1)

    def test_max_concurrent_respected(self):
        """_drainQueue respects maxConcurrent limit."""
        self.machine.setMaxConcurrent(1)

        # Add 3 tools to queue
        for i in range(3):
            self.machine._toolQueue.append(
                ToolRequest(
                    toolName=f"tool_{i}",
                    params={},
                    toolCallId=f"call_{i}",
                    groupId=1,
                    source='auto',
                    toolType=ToolType.READ_ONLY,
                    description="test"
                )
            )

        self.machine._drainQueue()

        # Should only execute 1
        self.assertEqual(len(self.machine._inProgress), 1)
        self.assertEqual(len(self.machine._toolQueue), 2)


class TestAgentToolMachineCompletion(TestBase):
    """Test tool completion handling."""

    def setUp(self):
        super().setUp()
        self.machine = AgentToolMachine(strategy=DefaultStrategy())

        self.patcher = patch('qgitc.agentmachine.AgentToolRegistry')
        self.mock_registry = self.patcher.start()
        self.mock_registry.tool_by_name.return_value = createMockTool(
            "git_status")

    def tearDown(self):
        self.patcher.stop()
        super().tearDown()

    def test_on_tool_finished_basic(self):
        """onToolFinished updates state correctly."""
        # Setup a pending tool
        toolCall = createToolCall("git_status", "call_1")
        self.machine.processToolCalls([toolCall])
        self.processEvents()

        # Simulate tool completion
        result = AgentToolResult(
            "git_status", True, "output", toolCallId="call_1")
        self.machine.onToolFinished(result)

        self.assertFalse(self.machine.hasPendingResults())
        self.assertTrue(self.machine.readyToContinue())

    def test_on_tool_finished_out_of_order(self):
        """Out-of-order completion handled correctly."""
        toolCalls = [
            createToolCall("tool_1", "call_1"),
            createToolCall("tool_2", "call_2"),
            createToolCall("tool_3", "call_3"),
        ]

        self.machine.processToolCalls(toolCalls)
        self.processEvents()

        # Complete in reverse order
        for toolId in ["call_3", "call_1", "call_2"]:
            result = AgentToolResult("tool", True, "output", toolCallId=toolId)
            self.machine.onToolFinished(result)

        # Should be ready after all complete
        self.assertTrue(self.machine.readyToContinue())

    def test_continuation_ready_signal(self):
        """agentContinuationReady emitted when all tools done."""
        toolCall = createToolCall("git_status", "call_1")
        self.machine.processToolCalls([toolCall])
        self.processEvents()

        signal_emitted = []
        self.machine.agentContinuationReady.connect(
            lambda: signal_emitted.append(True))

        result = AgentToolResult(
            "git_status", True, "output", toolCallId="call_1")
        self.machine.onToolFinished(result)

        self.assertEqual(len(signal_emitted), 1)


class TestAgentToolMachineBatching(TestBase):
    """Test tool grouping and batch completion."""

    def setUp(self):
        super().setUp()
        self.machine = AgentToolMachine(strategy=DefaultStrategy())

        self.patcher = patch('qgitc.agentmachine.AgentToolRegistry')
        self.mock_registry = self.patcher.start()
        self.mock_registry.tool_by_name.side_effect = lambda name: (
            createMockTool(name, ToolType.READ_ONLY)
            if name.startswith("git_")
            else createMockTool(name, ToolType.WRITE)
        )

    def tearDown(self):
        self.patcher.stop()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_batch_grouping(self):
        """Auto-tools are grouped in same batch."""
        toolCalls = [
            createToolCall("git_status", "call_1"),
            createToolCall("git_log", "call_2"),
        ]

        self.machine.processToolCalls(toolCalls)
        self.processEvents()

        # Both should be in group 1
        self.assertIn("call_1", self.machine._inProgress)
        self.assertIn("call_2", self.machine._inProgress)
        self.assertEqual(
            self.machine._inProgress["call_1"].groupId,
            self.machine._inProgress["call_2"].groupId
        )

    def test_batch_completion_tracking(self):
        """Batch tracks remaining count correctly."""
        toolCalls = [
            createToolCall("git_status", "call_1"),
            createToolCall("git_log", "call_2"),
        ]

        self.machine.processToolCalls(toolCalls)
        self.processEvents()

        groupId = self.machine._inProgress["call_1"].groupId
        group = self.machine._autoToolGroups[groupId]
        self.assertEqual(group["remaining"], 2)

    def test_batch_continues_when_complete(self):
        """Batch emits continuation when complete and no confirmations."""
        toolCalls = [
            createToolCall("git_status", "call_1"),
            createToolCall("git_log", "call_2"),
        ]

        signal_emitted = []
        self.machine.agentContinuationReady.connect(
            lambda: signal_emitted.append(True))

        self.machine.processToolCalls(toolCalls)
        self.processEvents()

        # Complete first tool
        result1 = AgentToolResult(
            "git_status", True, "output", toolCallId="call_1")
        self.machine.onToolFinished(result1)

        self.assertEqual(len(signal_emitted), 0)  # Not ready yet

        # Complete second tool
        result2 = AgentToolResult(
            "git_log", True, "output", toolCallId="call_2")
        self.machine.onToolFinished(result2)

        self.assertEqual(len(signal_emitted), 1)  # Ready now!


class TestAgentToolMachineIntrospection(TestBase):
    """Test debugging/introspection methods."""

    def setUp(self):
        super().setUp()
        self.machine = AgentToolMachine()

        self.patcher = patch('qgitc.agentmachine.AgentToolRegistry')
        self.mock_registry = self.patcher.start()
        self.mock_registry.tool_by_name.return_value = createMockTool(
            "git_status")

    def tearDown(self):
        self.patcher.stop()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_get_in_progress_tools(self):
        """getInProgressTools lists executing tools."""
        toolCall = createToolCall("git_status", "call_1")
        self.machine.processToolCalls([toolCall])
        self.processEvents()

        tools = self.machine.getInProgressTools()
        self.assertIn("git_status", tools)

    def test_get_awaiting_count(self):
        """getAwaitingCount returns pending tool count."""
        toolCall = createToolCall("git_status", "call_1")
        self.machine.processToolCalls([toolCall])
        self.processEvents()

        count = self.machine.getAwaitingCount()
        self.assertEqual(count, 1)


class TestAgentToolMachineEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        self.machine = AgentToolMachine()

        self.patcher = patch('qgitc.agentmachine.AgentToolRegistry')
        self.mock_registry = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_missing_tool_in_registry(self):
        """Missing tool in registry is handled gracefully."""
        self.mock_registry.tool_by_name.return_value = None

        toolCall = createToolCall("unknown_tool", "call_1")

        # Should not crash
        self.machine.processToolCalls([toolCall])

        # Tool should require confirmation (defaults to WRITE)
        self.assertEqual(len(self.machine._toolQueue), 0)

    def test_missing_tool_call_id(self):
        """Missing toolCallId is handled."""
        toolCall = {
            "id": None,
            "type": "function",
            "function": {"name": "git_status", "arguments": "{}"}
        }

        self.mock_registry.tool_by_name.return_value = createMockTool(
            "git_status", ToolType.READ_ONLY
        )

        # Should not crash
        self.machine.processToolCalls([toolCall])

    def test_custom_tool_lookup_function(self):
        """Tool lookup function is called when provided."""
        custom_tool = createMockTool("custom_ui_tool", ToolType.READ_ONLY)

        def custom_lookup(toolName):
            if toolName == "custom_ui_tool":
                return custom_tool
            return None

        machine = AgentToolMachine(toolLookupFn=custom_lookup)

        result = machine._toolByName("custom_ui_tool")
        self.assertEqual(result.name, "custom_ui_tool")

    def test_custom_tool_lookup_fallback(self):
        """Falls back to registry if custom lookup returns None."""
        def custom_lookup(toolName):
            return None  # Doesn't find anything

        self.mock_registry.tool_by_name.return_value = createMockTool(
            "git_status")

        machine = AgentToolMachine(toolLookupFn=custom_lookup)
        result = machine._toolByName("git_status")

        self.assertEqual(result.name, "git_status")


# ============================================================================
# Integration Tests
# ============================================================================

class TestAgentToolMachineIntegration(TestBase):
    """Integration tests for complete workflows."""

    def setUp(self):
        super().setUp()
        self.machine = AgentToolMachine(
            strategy=DefaultStrategy(),
            maxConcurrent=2
        )

        self.patcher = patch('qgitc.agentmachine.AgentToolRegistry')
        self.mock_registry = self.patcher.start()
        self.mock_registry.tool_by_name.side_effect = lambda name: (
            createMockTool(name, ToolType.READ_ONLY)
            if name != "git_commit"
            else createMockTool(name, ToolType.WRITE)
        )

    def tearDown(self):
        self.patcher.stop()
        super().tearDown()

    def doCreateRepo(self):
        pass

    def test_mixed_auto_and_confirmed_tools(self):
        """Workflow: some auto, some need confirmation."""
        continuation_signals = []
        self.machine.agentContinuationReady.connect(
            lambda: continuation_signals.append(True)
        )

        # Scenario: 2 auto-run READ_ONLY + 1 WRITE needing confirmation
        toolCalls = [
            createToolCall("git_status", "call_1"),   # Auto
            createToolCall("git_log", "call_2"),       # Auto
            createToolCall("git_commit", "call_3"),    # Needs approval
        ]

        self.machine.processToolCalls(toolCalls)
        self.processEvents()

        # Auto tools should be queued
        self.assertEqual(len(self.machine._toolQueue), 0)  # Executing

        # Complete the auto tools
        self.machine.onToolFinished(
            AgentToolResult("git_status", True, "output", toolCallId="call_1")
        )
        self.machine.onToolFinished(
            AgentToolResult("git_log", True, "output", toolCallId="call_2")
        )

        # Should NOT continue yet (call_3 pending)
        self.assertEqual(len(continuation_signals), 0)

        # Approve and complete call_3
        self.machine.approveToolExecution("git_commit", {}, "call_3")
        self.processEvents()

        self.machine.onToolFinished(
            AgentToolResult("git_commit", True, "output", toolCallId="call_3")
        )
        self.processEvents()

        # NOW should continue
        self.assertEqual(len(continuation_signals), 1)

    def test_rejection_workflow(self):
        """Workflow: tool rejection stops execution."""
        toolCalls = [
            createToolCall("git_status", "call_1"),   # Auto
            createToolCall("git_commit", "call_2"),    # Needs approval
        ]

        self.machine.processToolCalls(toolCalls)
        self.processEvents()

        # User rejects the confirmation
        self.machine.rejectToolExecution("git_commit", "call_2")

        # Complete auto tool
        self.machine.onToolFinished(
            AgentToolResult("git_status", True, "output", toolCallId="call_1")
        )

        # Should be ready (call_2 was rejected)
        self.assertTrue(self.machine.readyToContinue())
