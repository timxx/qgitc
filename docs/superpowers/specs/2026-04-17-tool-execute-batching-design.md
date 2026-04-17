# Tool Execute Batching Design

Date: 2026-04-17
Status: Draft approved in chat, pending final file review
Scope: Refactor tool execution in agent loop to support grouped parallel execution for read-only tools while preserving strict output order.

## Objective

Refactor agent tool execution so that:
1. Tool calls are still processed in assistant-declared order.
2. Consecutive read-only tools execute in parallel batches.
3. Non-read-only tools execute one-by-one and split batch boundaries.
4. Final ToolResultBlock order is always identical to input ToolUseBlock order.
5. Existing permission, skill-allowlist, signal, and error behavior remain compatible.

## Non-Goals

1. No change to tool schema contracts.
2. No change to permission policy semantics.
3. No change to message protocol with the model provider.
4. No broad refactor of AgentLoop lifecycle outside tool execution.

## Current State Summary

Today, AgentLoop executes tool blocks strictly sequentially in qgitc/agent/agent_loop.py. Each block performs:
1. Skill allowlist check.
2. Tool lookup.
3. Permission check (deny, ask, allow).
4. Tool execution.
5. ToolResultBlock emission and signal emission.

This is correct but does not exploit safe parallelism for read-only tools.

## Component Boundaries

1. AgentLoop (existing)
- Keeps conversation loop, compaction, provider streaming, and message appending.
- Delegates tool block execution to a new executor module.

2. Tool Executor (new module: qgitc/agent/tool_executor.py)
- Partitions ToolUseBlock list into execution batches.
- Executes read-only batches in parallel.
- Executes non-read-only blocks sequentially.
- Reassembles results in stable original order.

3. Existing dependencies reused
- ToolRegistry for lookup.
- PermissionEngine for permission checks.
- ToolContext for execution context.
- Qt signal callbacks remain owned by AgentLoop.

## Partitioning Rules

Given ordered tool blocks B0..Bn:
1. Resolve tool by name.
2. A block is parallel-safe only if tool exists and tool.is_read_only() is true.
3. Unknown tools are treated as non-parallel-safe for conservative behavior.
4. Consecutive parallel-safe blocks are grouped into one batch.
5. Each non-parallel-safe block forms its own single-item sequential batch.

Example:
- Input: R1, R2, W1, R3, R4, U1
- Batches: [R1,R2], [W1], [R3,R4], [U1]

Where:
- R = read-only tool
- W = write or destructive tool
- U = unknown tool

## Batch Execution Rules

1. Read-only batch
- Execute all blocks concurrently using a thread pool.
- Capture each block result by original index.

2. Sequential batch
- Execute single block directly.

3. Abort behavior
- Stop scheduling new work when abort flag is set.
- Any unscheduled blocks become interrupted error ToolResultBlock entries.

## Stable Ordering Guarantee

For every block, keep original position index i.
1. Parallel executions may complete in any runtime order.
2. Final list is assembled by ascending original index.
3. Returned ToolResultBlock sequence always matches input ToolUseBlock sequence exactly.

## Behavioral Compatibility

The following remain unchanged:
1. Skill allowlist enforcement.
2. Permission deny and ask flows.
3. User approval wait semantics for PermissionAsk.
4. Error messages for unknown tools and denied execution.
5. toolCallStart and toolCallResult emission frequency (once per block).

## Detailed Per-Block Flow

For a single block, execution keeps existing semantics:
1. Skill allowlist check.
2. Tool lookup.
3. Permission check.
4. Optional permission wait.
5. toolCallStart emit.
6. Tool execute with ToolContext.
7. Exception wrapping to ToolResult is_error true.
8. ToolResultBlock append.
9. toolCallResult emit.

This logic is extracted or shared, not behaviorally rewritten.

## Concurrency and Threading Notes

1. AgentLoop continues running in its QThread.
2. Parallel read-only execution uses Python worker threads from inside that thread.
3. Shared mutable structures in executor use index-addressed writes to avoid order races.
4. Signal emission must remain thread-safe under Qt queued connections as today.

## Error Handling

1. One block failure does not cancel sibling read-only block executions.
2. Unknown tool yields per-block error ToolResultBlock.
3. Permission denied yields per-block error ToolResultBlock.
4. Permission ask denied by user yields per-block error ToolResultBlock.
5. Tool exceptions are wrapped as per-block error ToolResultBlock.
6. Abort prevents unscheduled executions and marks remaining blocks interrupted.

## Testing Strategy

Add or update unit tests covering:
1. All read-only tools execute as one parallel batch and preserve output order.
2. Mixed read-only and non-read-only tools split into expected batches.
3. Read-only groups split around non-read-only middle tool.
4. Unknown tool acts as sequential boundary and returns expected error.
5. Permission ask denied in middle block returns error and later blocks proceed when not aborted.
6. Abort during execution returns interrupted errors for unscheduled blocks.
7. Signal emission count and mapping per block remain unchanged.

## Rollout Plan

1. Introduce executor module with partition and execute helpers.
2. Wire AgentLoop to call executor.
3. Keep old sequential code path behavior via equivalent per-block helper.
4. Add focused tests before and after wiring.
5. Validate with targeted test run, then full test suite.

## Risks and Mitigations

1. Risk: signal interleaving surprises UI.
- Mitigation: keep per-block emits; test deterministic ordering of returned results, not completion timing.

2. Risk: permission wait interaction with parallel branch.
- Mitigation: permission ask only occurs in per-block flow; read-only tools should typically auto-allow but flow supports ask safely.

3. Risk: hidden side effects in tools marked read-only.
- Mitigation: classification relies on existing tool metadata; retain conservative unknown-tool behavior.

## Acceptance Criteria

1. Consecutive read-only calls execute concurrently.
2. Non-read-only calls execute one-by-one.
3. Returned ToolResultBlock list always preserves original call order.
4. Existing permission and signal contracts continue to pass tests.
5. No regression in unknown-tool, deny, ask, and exception handling.
