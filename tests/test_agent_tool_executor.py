# -*- coding: utf-8 -*-

import unittest
from threading import Lock, current_thread
from time import sleep
from typing import Any, Dict

from qgitc.agent.permissions import (
    PermissionAllow,
    PermissionAsk,
    PermissionDeny,
    PermissionEngine,
)
from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tool_executor import (
    TOOL_SKIPPED_MESSAGE,
    _partition_tool_calls,
    execute_tool_blocks,
)
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import ToolUseBlock


class ReadOnlyTool(Tool):
    name = "read_tool"
    description = "Read-only test tool"

    def is_read_only(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="ok")

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class WriteTool(Tool):
    name = "write_tool"
    description = "Write test tool"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="ok")

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class SleepyReadTool(Tool):
    name = "sleepy_read"
    description = "Read-only test tool with delay"

    def is_read_only(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        sleep(input_data.get("delay", 0))
        return ToolResult(content=input_data.get("label", ""))

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class SleepyWriteTool(Tool):
    name = "sleepy_write"
    description = "Write tool with delay"

    def __init__(self) -> None:
        self._lock = Lock()
        self.active = 0
        self.max_active = 0

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        sleep(input_data.get("delay", 0))
        with self._lock:
            self.active -= 1
        return ToolResult(content=input_data.get("label", ""))

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class ContextIdReadTool(Tool):
    name = "context_id_read"
    description = "Read-only tool that returns current context object id"

    def is_read_only(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content=str(id(context)))

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class SkillTool(Tool):
    name = "Skill"
    description = "Skill tool"

    def is_read_only(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content="skill")

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class SetExtraTool(Tool):
    name = "set_extra"
    description = "Mutates shared context.extra"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        context.extra[input_data["key"]] = input_data["value"]
        return ToolResult(content="set")

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class ReadExtraTool(Tool):
    name = "read_extra"
    description = "Reads from shared context.extra"

    def is_read_only(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(content=str(context.extra.get(input_data["key"])))

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class MutateExtraReadTool(Tool):
    name = "mutate_extra_read"
    description = "Read-only tool that mutates context.extra"

    def is_read_only(self) -> bool:
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        context.extra[input_data["key"]] = input_data["value"]
        return ToolResult(content=input_data["key"])

    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}


class TestPartitionToolCalls(unittest.TestCase):

    def test_partitions_consecutive_read_only_groups(self):
        registry = ToolRegistry()
        registry.register(ReadOnlyTool())
        registry.register(WriteTool())

        blocks = [
            ToolUseBlock(id="1", name="read_tool", input={}),
            ToolUseBlock(id="2", name="read_tool", input={}),
            ToolUseBlock(id="3", name="write_tool", input={}),
            ToolUseBlock(id="4", name="read_tool", input={}),
        ]

        batches = _partition_tool_calls(blocks, registry)

        self.assertEqual(len(batches), 3)
        self.assertTrue(batches[0].is_parallel)
        self.assertEqual([block.id for block in batches[0].blocks], ["1", "2"])
        self.assertFalse(batches[1].is_parallel)
        self.assertEqual([block.id for block in batches[1].blocks], ["3"])
        self.assertTrue(batches[2].is_parallel)
        self.assertEqual([block.id for block in batches[2].blocks], ["4"])

    def test_does_not_merge_consecutive_non_parallel_blocks(self):
        registry = ToolRegistry()
        registry.register(WriteTool())

        blocks = [
            ToolUseBlock(id="1", name="write_tool", input={}),
            ToolUseBlock(id="2", name="write_tool", input={}),
        ]

        batches = _partition_tool_calls(blocks, registry)

        self.assertEqual(len(batches), 2)
        self.assertFalse(batches[0].is_parallel)
        self.assertEqual([block.id for block in batches[0].blocks], ["1"])
        self.assertFalse(batches[1].is_parallel)
        self.assertEqual([block.id for block in batches[1].blocks], ["2"])

    def test_skill_tool_breaks_parallel_read_only_group(self):
        registry = ToolRegistry()
        registry.register(ReadOnlyTool())
        registry.register(SkillTool())

        blocks = [
            ToolUseBlock(id="1", name="read_tool", input={}),
            ToolUseBlock(id="2", name="Skill", input={}),
            ToolUseBlock(id="3", name="read_tool", input={}),
        ]

        batches = _partition_tool_calls(blocks, registry)

        self.assertEqual(len(batches), 3)
        self.assertTrue(batches[0].is_parallel)
        self.assertEqual([block.id for block in batches[0].blocks], ["1"])
        self.assertFalse(batches[1].is_parallel)
        self.assertEqual([block.id for block in batches[1].blocks], ["2"])
        self.assertTrue(batches[2].is_parallel)
        self.assertEqual([block.id for block in batches[2].blocks], ["3"])


class TestExecuteToolBlocks(unittest.TestCase):

    def test_parallel_batch_preserves_original_order(self):
        registry = ToolRegistry()
        registry.register(SleepyReadTool())

        blocks = [
            ToolUseBlock(
                id="a",
                name="sleepy_read",
                input={"label": "A", "delay": 0.15},
            ),
            ToolUseBlock(
                id="b",
                name="sleepy_read",
                input={"label": "B", "delay": 0.01},
            ),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={},
        )

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=PermissionEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, tool, tool_input: True,
            on_tool_start=lambda tool_id, tool_name, tool_input: None,
            on_tool_result=lambda tool_id, tool_name, content, is_error: None,
            max_workers=4,
        )

        self.assertEqual([result.tool_use_id for result in results], ["a", "b"])
        self.assertEqual([result.content for result in results], ["A", "B"])

    def test_sequential_batches_execute_one_by_one(self):
        registry = ToolRegistry()
        tool = SleepyWriteTool()
        registry.register(tool)

        blocks = [
            ToolUseBlock(
                id="a",
                name="sleepy_write",
                input={"label": "A", "delay": 0.05},
            ),
            ToolUseBlock(
                id="b",
                name="sleepy_write",
                input={"label": "B", "delay": 0.05},
            ),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={},
        )

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=PermissionEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, ask_tool, tool_input: True,
            on_tool_start=lambda tool_id, tool_name, tool_input: None,
            on_tool_result=lambda tool_id, tool_name, content, is_error: None,
            max_workers=4,
        )

        self.assertEqual([result.tool_use_id for result in results], ["a", "b"])
        self.assertEqual(tool.max_active, 1)

    def test_enforces_context_tool_allowlist(self):
        registry = ToolRegistry()
        registry.register(ReadOnlyTool())

        blocks = [
            ToolUseBlock(id="a", name="read_tool", input={}),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={"tool_allowed_tools": ["some_other_tool"]},
        )

        start_calls = []
        result_calls = []

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=PermissionEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, tool, tool_input: True,
            on_tool_start=lambda tool_id, tool_name, tool_input: start_calls.append(tool_id),
            on_tool_result=lambda tool_id, tool_name, content, is_error: result_calls.append((tool_id, content, is_error)),
            max_workers=4,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_use_id, "a")
        self.assertEqual(results[0].content, "Tool 'read_tool' is not allowed by active skill")
        self.assertTrue(results[0].is_error)
        self.assertEqual(start_calls, [])
        self.assertEqual(result_calls, [("a", "Tool 'read_tool' is not allowed by active skill", True)])

    def test_unknown_tool_returns_agentloop_compatible_error(self):
        registry = ToolRegistry()

        blocks = [
            ToolUseBlock(id="a", name="missing_tool", input={}),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={},
        )

        result_calls = []

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=PermissionEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, tool, tool_input: True,
            on_tool_start=lambda tool_id, tool_name, tool_input: None,
            on_tool_result=lambda tool_id, tool_name, content, is_error: result_calls.append((tool_id, content, is_error)),
            max_workers=4,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_use_id, "a")
        self.assertEqual(results[0].content, "Unknown tool: missing_tool")
        self.assertTrue(results[0].is_error)
        self.assertEqual(result_calls, [("a", "Unknown tool: missing_tool", True)])

    def test_permission_deny_returns_permission_message(self):
        class DenyEngine:
            def check(self, tool, input_data):
                return PermissionDeny(message="Denied by test")

        registry = ToolRegistry()
        registry.register(WriteTool())

        blocks = [
            ToolUseBlock(id="a", name="write_tool", input={}),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={},
        )

        permission_requests = []
        start_calls = []
        result_calls = []

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=DenyEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, tool, tool_input: permission_requests.append(tool_id) or True,
            on_tool_start=lambda tool_id, tool_name, tool_input: start_calls.append(tool_id),
            on_tool_result=lambda tool_id, tool_name, content, is_error: result_calls.append((tool_id, content, is_error)),
            max_workers=4,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_use_id, "a")
        self.assertEqual(results[0].content, "Denied by test")
        self.assertTrue(results[0].is_error)
        self.assertEqual(permission_requests, [])
        self.assertEqual(start_calls, [])
        self.assertEqual(result_calls, [("a", "Denied by test", True)])

    def test_permission_ask_user_denied_maps_to_expected_message(self):
        class AskEngine:
            def check(self, tool, input_data):
                return PermissionAsk(message="Need approval")

        registry = ToolRegistry()
        registry.register(WriteTool())

        blocks = [
            ToolUseBlock(id="a", name="write_tool", input={}),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={},
        )

        start_calls = []
        result_calls = []

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=AskEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, tool, tool_input: False,
            on_tool_start=lambda tool_id, tool_name, tool_input: start_calls.append(tool_id),
            on_tool_result=lambda tool_id, tool_name, content, is_error: result_calls.append((tool_id, content, is_error)),
            max_workers=4,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_use_id, "a")
        self.assertEqual(results[0].content, TOOL_SKIPPED_MESSAGE)
        self.assertTrue(results[0].is_error)
        self.assertEqual(start_calls, [])
        self.assertEqual(result_calls, [("a", TOOL_SKIPPED_MESSAGE, True)])

    def test_permission_ask_user_approved_executes_tool(self):
        class AskEngine:
            def check(self, tool, input_data):
                return PermissionAsk(message="Need approval")

        registry = ToolRegistry()
        registry.register(WriteTool())

        blocks = [
            ToolUseBlock(id="a", name="write_tool", input={}),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={},
        )

        start_calls = []
        result_calls = []

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=AskEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, tool, tool_input: True,
            on_tool_start=lambda tool_id, tool_name, tool_input: start_calls.append((tool_id, tool_name)),
            on_tool_result=lambda tool_id, tool_name, content, is_error: result_calls.append((tool_id, content, is_error)),
            max_workers=4,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].tool_use_id, "a")
        self.assertEqual(results[0].content, "ok")
        self.assertFalse(results[0].is_error)
        self.assertEqual(start_calls, [("a", "write_tool")])
        self.assertEqual(result_calls, [("a", "ok", False)])

    def test_parallel_batch_uses_distinct_context_instances(self):
        registry = ToolRegistry()
        registry.register(ContextIdReadTool())

        blocks = [
            ToolUseBlock(id="a", name="context_id_read", input={}),
            ToolUseBlock(id="b", name="context_id_read", input={}),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={"k": "v"},
        )

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=PermissionEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, tool, tool_input: True,
            on_tool_start=lambda tool_id, tool_name, tool_input: None,
            on_tool_result=lambda tool_id, tool_name, content, is_error: None,
            max_workers=4,
        )

        self.assertEqual(len(results), 2)
        self.assertNotEqual(results[0].content, results[1].content)

    def test_context_extra_mutation_is_visible_to_subsequent_tools(self):
        registry = ToolRegistry()
        registry.register(SetExtraTool())
        registry.register(ReadExtraTool())

        blocks = [
            ToolUseBlock(
                id="a",
                name="set_extra",
                input={"key": "tool_allowed_tools", "value": ["read_extra"]},
            ),
            ToolUseBlock(id="b", name="read_extra", input={"key": "tool_allowed_tools"}),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={},
        )

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=PermissionEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, tool, tool_input: True,
            on_tool_start=lambda tool_id, tool_name, tool_input: None,
            on_tool_result=lambda tool_id, tool_name, content, is_error: None,
            max_workers=4,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].content, "set")
        self.assertEqual(results[1].content, "['read_extra']")

    def test_parallel_batch_does_not_mutate_shared_extra(self):
        registry = ToolRegistry()
        registry.register(MutateExtraReadTool())

        blocks = [
            ToolUseBlock(
                id="a",
                name="mutate_extra_read",
                input={"key": "parallel_a", "value": 1},
            ),
            ToolUseBlock(
                id="b",
                name="mutate_extra_read",
                input={"key": "parallel_b", "value": 2},
            ),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={"seed": "x"},
        )

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=PermissionEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, tool, tool_input: True,
            on_tool_start=lambda tool_id, tool_name, tool_input: None,
            on_tool_result=lambda tool_id, tool_name, content, is_error: None,
            max_workers=4,
        )

        self.assertEqual([result.content for result in results], ["parallel_a", "parallel_b"])
        self.assertEqual(context.extra, {"seed": "x"})

    def test_parallel_batch_callbacks_run_on_executor_thread(self):
        registry = ToolRegistry()
        registry.register(SleepyReadTool())

        blocks = [
            ToolUseBlock(
                id="a",
                name="sleepy_read",
                input={"label": "A", "delay": 0.01},
            ),
            ToolUseBlock(
                id="b",
                name="sleepy_read",
                input={"label": "B", "delay": 0.01},
            ),
        ]

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={},
        )

        caller_thread_id = current_thread().ident
        start_calls = []
        result_calls = []

        execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=PermissionEngine(),
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda tool_id, tool, tool_input: True,
            on_tool_start=lambda tool_id, tool_name, tool_input: start_calls.append(
                (tool_id, tool_name, current_thread().ident)
            ),
            on_tool_result=lambda tool_id, tool_name, content, is_error: result_calls.append(
                (tool_id, content, is_error, current_thread().ident)
            ),
            max_workers=4,
        )

        self.assertEqual([call[:2] for call in start_calls], [("a", "sleepy_read"), ("b", "sleepy_read")])
        self.assertEqual([call[:3] for call in result_calls], [("a", "A", False), ("b", "B", False)])
        self.assertTrue(all(call[2] == caller_thread_id for call in start_calls))
        self.assertTrue(all(call[3] == caller_thread_id for call in result_calls))


if __name__ == "__main__":
    unittest.main()
