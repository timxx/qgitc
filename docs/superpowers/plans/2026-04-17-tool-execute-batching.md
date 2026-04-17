# Tool Execute Batching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor agent tool execution so consecutive read-only tools run in parallel batches, non-read-only tools run one-by-one, and output order stays identical to the original tool call sequence.

**Architecture:** Keep `AgentLoop` as orchestration owner and extract batching/execution mechanics into a dedicated `tool_executor` module. The executor partitions tool blocks by read-only safety and executes batch-by-batch. Per-block behavior (skill allowlist, permission checks, signals, error mapping) remains equivalent to the current implementation.

**Tech Stack:** Python 3, PySide6 signals/threading, unittest, concurrent.futures ThreadPoolExecutor

---

## File Structure

- Create: `qgitc/agent/tool_executor.py`
  - Owns batching model and execution entrypoint.
  - Exposes `execute_tool_blocks(...)` and `_partition_tool_calls(...)` helpers.
- Modify: `qgitc/agent/agent_loop.py`
  - Replaces in-method sequential loop with executor delegation.
  - Keeps all signal emissions and permission wait semantics via callbacks.
- Create: `tests/test_agent_tool_executor.py`
  - Unit tests for partitioning and order-preserving execution behavior.
- Modify: `tests/test_agent_loop.py`
  - Integration-style checks to assert `AgentLoop` behavior remains compatible while allowing grouped execution.

### Task 1: Add Executor Module Skeleton With Partitioning

**Files:**
- Create: `qgitc/agent/tool_executor.py`
- Test: `tests/test_agent_tool_executor.py`

- [ ] **Step 1: Write the failing partition test**

```python
# tests/test_agent_tool_executor.py
# -*- coding: utf-8 -*-

import unittest

from qgitc.agent.tool import Tool
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import ToolUseBlock
from qgitc.agent.tool_executor import _partition_tool_calls


class _ReadOnlyTool(Tool):
    name = "read"
    description = "read only"

    def is_read_only(self):
        return True

    def execute(self, input_data, context):
        raise NotImplementedError()

    def input_schema(self):
        return {"type": "object", "properties": {}}


class _WriteTool(Tool):
    name = "write"
    description = "write tool"

    def execute(self, input_data, context):
        raise NotImplementedError()

    def input_schema(self):
        return {"type": "object", "properties": {}}


class TestPartitionToolCalls(unittest.TestCase):

    def test_partitions_consecutive_read_only_groups(self):
        registry = ToolRegistry()
        registry.register(_ReadOnlyTool())
        registry.register(_WriteTool())

        blocks = [
            ToolUseBlock(id="1", name="read", input={}),
            ToolUseBlock(id="2", name="read", input={}),
            ToolUseBlock(id="3", name="write", input={}),
            ToolUseBlock(id="4", name="read", input={}),
        ]

        batches = _partition_tool_calls(blocks, registry)

        self.assertEqual(len(batches), 3)
        self.assertTrue(batches[0].is_parallel)
        self.assertEqual([b.id for b in batches[0].blocks], ["1", "2"])
        self.assertFalse(batches[1].is_parallel)
        self.assertEqual([b.id for b in batches[1].blocks], ["3"])
        self.assertTrue(batches[2].is_parallel)
        self.assertEqual([b.id for b in batches[2].blocks], ["4"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_agent_tool_executor.TestPartitionToolCalls.test_partitions_consecutive_read_only_groups -v`
Expected: FAIL with `ModuleNotFoundError` or missing `_partition_tool_calls`.

- [ ] **Step 3: Write minimal partition implementation**

```python
# qgitc/agent/tool_executor.py
# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import List

from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import ToolUseBlock


@dataclass
class ToolBatch:
    is_parallel: bool
    blocks: List[ToolUseBlock]


def _is_parallel_safe(block, registry):
    tool = registry.get(block.name)
    return tool is not None and tool.is_read_only()


def _partition_tool_calls(tool_blocks, registry):
    # type: (List[ToolUseBlock], ToolRegistry) -> List[ToolBatch]
    batches = []
    for block in tool_blocks:
        is_parallel = _is_parallel_safe(block, registry)
        if is_parallel and batches and batches[-1].is_parallel:
            batches[-1].blocks.append(block)
        else:
            batches.append(ToolBatch(is_parallel=is_parallel, blocks=[block]))
    return batches
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_agent_tool_executor.TestPartitionToolCalls.test_partitions_consecutive_read_only_groups -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/tool_executor.py tests/test_agent_tool_executor.py
git commit -m "feat(agent): add tool batch partitioning for read-only groups"
```

### Task 2: Implement Order-Preserving Batch Execution In Executor

**Files:**
- Modify: `qgitc/agent/tool_executor.py`
- Modify: `tests/test_agent_tool_executor.py`

- [ ] **Step 1: Write failing order-preservation test for parallel batch**

```python
# tests/test_agent_tool_executor.py
from concurrent.futures import ThreadPoolExecutor
from qgitc.agent.permissions import PermissionEngine
from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tool_executor import execute_tool_blocks


class _SleepyReadTool(Tool):
    name = "sleepy_read"
    description = "read only with delay"

    def is_read_only(self):
        return True

    def execute(self, input_data, context):
        import time
        time.sleep(input_data.get("delay", 0))
        return ToolResult(content=input_data["label"])

    def input_schema(self):
        return {"type": "object", "properties": {}}


class TestExecuteToolBlocks(unittest.TestCase):

    def test_parallel_batch_preserves_original_order(self):
        registry = ToolRegistry()
        registry.register(_SleepyReadTool())

        blocks = [
            ToolUseBlock(id="a", name="sleepy_read", input={"label": "A", "delay": 0.15}),
            ToolUseBlock(id="b", name="sleepy_read", input={"label": "B", "delay": 0.01}),
        ]

        calls = []

        def on_start(tool_id, tool_name, tool_input):
            calls.append(("start", tool_id, tool_name))

        def on_result(tool_id, content, is_error):
            calls.append(("result", tool_id, content, is_error))

        def request_permission(tool_id, tool, tool_input):
            return True

        context = ToolContext(
            working_directory=".",
            abort_requested=lambda: False,
            extra={},
        )
        engine = PermissionEngine()

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=engine,
            context=context,
            is_aborted=lambda: False,
            request_permission=request_permission,
            on_tool_start=on_start,
            on_tool_result=on_result,
            max_workers=4,
        )

        self.assertEqual([r.tool_use_id for r in results], ["a", "b"])
        self.assertEqual([r.content for r in results], ["A", "B"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_agent_tool_executor.TestExecuteToolBlocks.test_parallel_batch_preserves_original_order -v`
Expected: FAIL because `execute_tool_blocks` is missing or returns wrong order.

- [ ] **Step 3: Implement batch execution with stable ordering**

```python
# qgitc/agent/tool_executor.py
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from qgitc.agent.permissions import PermissionAsk, PermissionDeny
from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.types import ToolResultBlock


def execute_tool_blocks(
    tool_blocks,
    registry,
    permission_engine,
    context,
    is_aborted,
    request_permission,
    on_tool_start,
    on_tool_result,
    max_workers=4,
):
    batches = _partition_tool_calls(tool_blocks, registry)
    by_index = [None] * len(tool_blocks)
    index_map = {id(block): i for i, block in enumerate(tool_blocks)}

    for batch in batches:
        if is_aborted():
            return None
        if batch.is_parallel:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        _execute_one_block,
                        block,
                        registry,
                        permission_engine,
                        context,
                        is_aborted,
                        request_permission,
                        on_tool_start,
                        on_tool_result,
                    )
                    for block in batch.blocks
                ]
                for block, future in zip(batch.blocks, futures):
                    by_index[index_map[id(block)]] = future.result()
        else:
            block = batch.blocks[0]
            by_index[index_map[id(block)]] = _execute_one_block(
                block,
                registry,
                permission_engine,
                context,
                is_aborted,
                request_permission,
                on_tool_start,
                on_tool_result,
            )

    return by_index
```

- [ ] **Step 4: Run tests for executor module**

Run: `python -m unittest tests.test_agent_tool_executor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/tool_executor.py tests/test_agent_tool_executor.py
git commit -m "feat(agent): execute read-only tool batches in parallel with stable ordering"
```

### Task 3: Port Existing Per-Block Validation/Permission/Signal Logic Into Executor

**Files:**
- Modify: `qgitc/agent/tool_executor.py`
- Modify: `tests/test_agent_tool_executor.py`

- [ ] **Step 1: Write failing tests for unknown tool, denied permission, and user-denied ask**

```python
# tests/test_agent_tool_executor.py
class _WriteNeedsAskTool(Tool):
    name = "write_needs_ask"
    description = "write tool"

    def execute(self, input_data, context):
        return ToolResult(content="ok")

    def input_schema(self):
        return {"type": "object", "properties": {}}


class TestExecuteErrorsAndPermission(unittest.TestCase):

    def test_unknown_tool_maps_to_error_block(self):
        registry = ToolRegistry()
        context = ToolContext(working_directory=".", abort_requested=lambda: False, extra={})
        engine = PermissionEngine()

        blocks = [ToolUseBlock(id="x", name="missing", input={})]

        results = execute_tool_blocks(
            tool_blocks=blocks,
            registry=registry,
            permission_engine=engine,
            context=context,
            is_aborted=lambda: False,
            request_permission=lambda *args: True,
            on_tool_start=lambda *args: None,
            on_tool_result=lambda *args: None,
        )

        self.assertEqual(results[0].tool_use_id, "x")
        self.assertTrue(results[0].is_error)
        self.assertIn("Unknown tool", results[0].content)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_agent_tool_executor.TestExecuteErrorsAndPermission.test_unknown_tool_maps_to_error_block -v`
Expected: FAIL until `_execute_one_block` matches current behavior.

- [ ] **Step 3: Implement per-block logic equivalent to current AgentLoop behavior**

```python
# qgitc/agent/tool_executor.py

def _execute_one_block(
    block,
    registry,
    permission_engine,
    context,
    is_aborted,
    request_permission,
    on_tool_start,
    on_tool_result,
):
    if is_aborted():
        return ToolResultBlock(tool_use_id=block.id, content="Interrupted by user before tool execution", is_error=True)

    allowed_tools = context.extra.get("tool_allowed_tools")
    if isinstance(allowed_tools, list) and allowed_tools and block.name != "Skill" and block.name not in allowed_tools:
        message = "Tool '{}' is not allowed by active skill".format(block.name)
        on_tool_result(block.id, message, True)
        return ToolResultBlock(tool_use_id=block.id, content=message, is_error=True)

    tool = registry.get(block.name)
    if tool is None:
        message = "Unknown tool: {}".format(block.name)
        on_tool_result(block.id, message, True)
        return ToolResultBlock(tool_use_id=block.id, content=message, is_error=True)

    perm = permission_engine.check(tool, block.input)
    if isinstance(perm, PermissionDeny):
        on_tool_result(block.id, perm.message, True)
        return ToolResultBlock(tool_use_id=block.id, content=perm.message, is_error=True)

    if isinstance(perm, PermissionAsk):
        approved = request_permission(block.id, tool, block.input)
        if not approved:
            message = "Tool execution denied by user"
            on_tool_result(block.id, message, True)
            return ToolResultBlock(tool_use_id=block.id, content=message, is_error=True)

    on_tool_start(block.id, block.name, block.input)
    try:
        result = tool.execute(block.input, context)
    except Exception as e:
        result = ToolResult(content=str(e), is_error=True)

    on_tool_result(block.id, result.content, result.is_error)
    return ToolResultBlock(tool_use_id=block.id, content=result.content, is_error=result.is_error)
```

- [ ] **Step 4: Run permission/error tests**

Run: `python -m unittest tests.test_agent_tool_executor.TestExecuteErrorsAndPermission -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/tool_executor.py tests/test_agent_tool_executor.py
git commit -m "refactor(agent): move tool block permission and error mapping into executor"
```

### Task 4: Integrate Executor Into AgentLoop

**Files:**
- Modify: `qgitc/agent/agent_loop.py`
- Modify: `tests/test_agent_loop.py`

- [ ] **Step 1: Write failing integration test for grouped execution semantics**

```python
# tests/test_agent_loop.py
class MultiToolCallProvider(ModelProvider):

    def __init__(self):
        self._call_count = 0

    def stream(self, messages, tools=None, model=None, max_tokens=4096):
        self._call_count += 1
        if self._call_count == 1:
            yield ToolCallDelta(id="c1", name="echo", arguments_delta='{"text":"one"}')
            yield ToolCallDelta(id="c2", name="echo", arguments_delta='{"text":"two"}')
            yield MessageComplete(stop_reason="tool_use")
        else:
            yield ContentDelta(text="done")
            yield MessageComplete(stop_reason="end_turn")

    def count_tokens(self, messages, system_prompt=None, tools=None):
        return 10


class TestAgentLoopToolExecution(TestBase):

    def test_two_read_only_tool_calls_emit_two_results_in_order(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        provider = MultiToolCallProvider()
        loop = _make_loop(provider, registry=registry)
        params = _make_params(provider)

        finished_spy = QSignalSpy(loop.agentFinished)
        result_spy = QSignalSpy(loop.toolCallResult)

        loop.submit("run", params)
        waitFor(self.app, lambda: finished_spy.count() > 0)

        self.assertEqual(result_spy.count(), 2)
        self.assertEqual(result_spy.at(0)[0], "c1")
        self.assertEqual(result_spy.at(1)[0], "c2")

        loop.abort()
        loop.wait(3000)
```

- [ ] **Step 2: Run failing integration test**

Run: `python -m unittest tests.test_agent_loop.TestAgentLoopToolExecution.test_two_read_only_tool_calls_emit_two_results_in_order -v`
Expected: FAIL until AgentLoop delegates correctly.

- [ ] **Step 3: Replace inline sequential loop with executor delegation**

```python
# qgitc/agent/agent_loop.py
from qgitc.agent.tool_executor import execute_tool_blocks


def _execute_tool_blocks(self, tool_blocks):
    # type: (List[ToolUseBlock]) -> Optional[List[ToolResultBlock]]
    if self._params is not None:
        self._context_extra_state["skill_registry"] = self._params.skill_registry

    ctx = ToolContext(
        working_directory=".",
        abort_requested=lambda: self._abort_flag,
        extra=self._context_extra_state,
    )

    def _request_permission(tool_call_id, tool, tool_input):
        self.permissionRequired.emit(tool_call_id, tool, tool_input)
        self._perm_mutex.lock()
        while (tool_call_id not in self._perm_decisions and not self._abort_flag):
            self._perm_cond.wait(self._perm_mutex)
        self._perm_mutex.unlock()
        if self._abort_flag:
            return False
        return self._perm_decisions.get(tool_call_id, False)

    return execute_tool_blocks(
        tool_blocks=tool_blocks,
        registry=self._tool_registry,
        permission_engine=self._permission_engine,
        context=ctx,
        is_aborted=lambda: self._abort_flag,
        request_permission=_request_permission,
        on_tool_start=lambda i, n, inp: self.toolCallStart.emit(i, n, inp),
        on_tool_result=lambda i, c, e: self.toolCallResult.emit(i, c, e),
    )
```

- [ ] **Step 4: Run agent loop test module**

Run: `python -m unittest tests.test_agent_loop -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add qgitc/agent/agent_loop.py tests/test_agent_loop.py
git commit -m "refactor(agent): delegate tool execution batching to executor"
```

### Task 5: Full Validation, Formatting, and Final Commit Hygiene

**Files:**
- Modify: `qgitc/agent/agent_loop.py`
- Modify: `qgitc/agent/tool_executor.py`
- Modify: `tests/test_agent_loop.py`
- Modify: `tests/test_agent_tool_executor.py`

- [ ] **Step 1: Run import sorting on changed Python files**

Run: `python -m isort qgitc/agent/agent_loop.py qgitc/agent/tool_executor.py tests/test_agent_loop.py tests/test_agent_tool_executor.py`
Expected: imports normalized with no errors.

- [ ] **Step 2: Run syntax validation on changed files**

Run: `python -m py_compile qgitc/agent/agent_loop.py qgitc/agent/tool_executor.py tests/test_agent_loop.py tests/test_agent_tool_executor.py`
Expected: no output and exit code 0.

- [ ] **Step 3: Run targeted and then full test suite**

Run: `python -m unittest tests.test_agent_tool_executor tests.test_agent_loop -v`
Expected: PASS

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: PASS

- [ ] **Step 4: Final commit if any cleanup remains**

```bash
git add qgitc/agent/agent_loop.py qgitc/agent/tool_executor.py tests/test_agent_loop.py tests/test_agent_tool_executor.py
git commit -m "test(agent): cover parallel read-only batching and order guarantees"
```

- [ ] **Step 5: Capture verification evidence in PR description**

```text
Verified commands:
- python -m unittest tests.test_agent_tool_executor tests.test_agent_loop -v
- python -m unittest discover -s tests -p "test_*.py" -v
- python -m py_compile qgitc/agent/agent_loop.py qgitc/agent/tool_executor.py tests/test_agent_loop.py tests/test_agent_tool_executor.py
```

## Plan Self-Review

1. Spec coverage check
- Parallel grouped execution for read-only tools: covered in Tasks 1-2.
- Non-read-only as boundaries and sequential execution: covered in Tasks 1-2.
- Stable result ordering: covered in Task 2 and Task 4 integration test.
- Permission and skill allowlist compatibility: covered in Task 3.
- AgentLoop integration and unchanged signal contract: covered in Task 4.
- Validation and repo-required checks (isort, py_compile, unittest): covered in Task 5.

2. Placeholder scan
- No TODO/TBD placeholders remain.
- All code-changing steps include concrete code snippets.
- All test steps include explicit commands and expected outcomes.

3. Type/signature consistency
- `execute_tool_blocks(...)` signature is used consistently across Tasks 2-4.
- `request_permission`, `on_tool_start`, and `on_tool_result` callback signatures match usage.
- `ToolResultBlock` generation fields match existing models (`tool_use_id`, `content`, `is_error`).
