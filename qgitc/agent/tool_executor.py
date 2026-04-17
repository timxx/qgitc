# -*- coding: utf-8 -*-

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from qgitc.agent.permissions import PermissionAsk, PermissionDeny, PermissionEngine
from qgitc.agent.tool import ToolContext, ToolResult
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import ToolResultBlock, ToolUseBlock


@dataclass
class ToolBatch:
    is_parallel: bool = False
    blocks: List[ToolUseBlock] = field(default_factory=list)


@dataclass
class _PreparedExecution:
    block: ToolUseBlock
    tool: Optional[object] = None
    immediate_result: Optional[ToolResultBlock] = None


def _build_error_result(block_id: str, message: str) -> ToolResultBlock:
    return ToolResultBlock(tool_use_id=block_id, content=message, is_error=True)


def _prepare_block_execution(
    block: ToolUseBlock,
    registry: ToolRegistry,
    permission_engine: PermissionEngine,
    context: ToolContext,
    is_aborted: Callable[[], bool],
    request_permission: Callable[[str, object, dict], bool],
) -> _PreparedExecution:
    if is_aborted():
        return _PreparedExecution(
            block=block,
            immediate_result=_build_error_result(block.id, "Tool execution aborted"),
        )

    allowed_tools = context.extra.get("tool_allowed_tools")
    if (
        isinstance(allowed_tools, list)
        and allowed_tools
        and block.name != "Skill"
        and block.name not in allowed_tools
    ):
        message = "Tool '{}' is not allowed by active skill".format(block.name)
        return _PreparedExecution(
            block=block,
            immediate_result=_build_error_result(block.id, message),
        )

    tool = registry.get(block.name)
    if tool is None:
        message = "Unknown tool: {}".format(block.name)
        return _PreparedExecution(
            block=block,
            immediate_result=_build_error_result(block.id, message),
        )

    perm = permission_engine.check(tool, block.input)
    if isinstance(perm, PermissionDeny):
        return _PreparedExecution(
            block=block,
            immediate_result=_build_error_result(block.id, perm.message),
        )

    if isinstance(perm, PermissionAsk):
        if not request_permission(block.id, tool, block.input):
            message = "The user chose to skip the tool call, they want to proceed without running it"
            return _PreparedExecution(
                block=block,
                immediate_result=_build_error_result(block.id, message),
            )

    return _PreparedExecution(block=block, tool=tool)


def _execute_tool(block: ToolUseBlock, tool: object, block_context: ToolContext) -> ToolResultBlock:
    try:
        result = tool.execute(block.input, block_context)
    except Exception as e:
        result = ToolResult(content=str(e), is_error=True)

    return ToolResultBlock(
        tool_use_id=block.id,
        content=result.content,
        is_error=result.is_error,
    )


def _execute_one_block(
    block: ToolUseBlock,
    registry: ToolRegistry,
    permission_engine: PermissionEngine,
    context: ToolContext,
    is_aborted: Callable[[], bool],
    request_permission: Callable[[str, object, dict], bool],
    on_tool_start: Callable[[str, str, dict], None],
    on_tool_result: Callable[[str, str, bool], None],
) -> Optional[ToolResultBlock]:
    prepared = _prepare_block_execution(
        block,
        registry,
        permission_engine,
        context,
        is_aborted,
        request_permission,
    )

    if prepared.immediate_result is not None:
        on_tool_result(block.id, prepared.immediate_result.content, True)
        return prepared.immediate_result

    on_tool_start(block.id, block.name, block.input)
    block_context = ToolContext(
        working_directory=context.working_directory,
        abort_requested=context.abort_requested,
        extra=context.extra,
    )
    result = _execute_tool(block, prepared.tool, block_context)
    on_tool_result(block.id, result.content, result.is_error)
    return result


def execute_tool_blocks(
    tool_blocks: List[ToolUseBlock],
    registry: ToolRegistry,
    permission_engine: PermissionEngine,
    context: ToolContext,
    is_aborted: Callable[[], bool],
    request_permission: Callable[[str, object, dict], bool],
    on_tool_start: Callable[[str, str, dict], None],
    on_tool_result: Callable[[str, str, bool], None],
    max_workers: int = 4,
) -> Optional[List[ToolResultBlock]]:
    batches = _partition_tool_calls(tool_blocks, registry)
    ordered_results: List[ToolResultBlock] = []

    for batch in batches:
        if batch.is_parallel and len(batch.blocks) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                parallel_futures: List[Optional[Future]] = []
                for block in batch.blocks:
                    prepared = _prepare_block_execution(
                        block,
                        registry,
                        permission_engine,
                        context,
                        is_aborted,
                        request_permission,
                    )

                    if prepared.immediate_result is not None:
                        on_tool_result(
                            prepared.block.id,
                            prepared.immediate_result.content,
                            True,
                        )
                        ordered_results.append(prepared.immediate_result)
                        parallel_futures.append(None)
                        continue

                    on_tool_start(prepared.block.id, prepared.block.name, prepared.block.input)
                    block_context = ToolContext(
                        working_directory=context.working_directory,
                        abort_requested=context.abort_requested,
                        extra=context.extra.copy(),
                    )
                    parallel_futures.append(
                        executor.submit(
                            _execute_tool,
                            prepared.block,
                            prepared.tool,
                            block_context,
                        )
                    )

                for future in parallel_futures:
                    result = future.result()
                    on_tool_result(result.tool_use_id, result.content, result.is_error)
                    ordered_results.append(result)
        else:
            for block in batch.blocks:
                result = _execute_one_block(
                    block,
                    registry,
                    permission_engine,
                    context,
                    is_aborted,
                    request_permission,
                    on_tool_start,
                    on_tool_result,
                )
                if result is not None:
                    ordered_results.append(result)

    return ordered_results


def _is_parallel_safe(block: ToolUseBlock, registry: ToolRegistry) -> bool:
    if block.name == "Skill":
        return False
    tool = registry.get(block.name)
    return tool is not None and tool.is_read_only()


def _partition_tool_calls(
    tool_blocks: List[ToolUseBlock],
    registry: ToolRegistry,
) -> List[ToolBatch]:
    batches: List[ToolBatch] = []

    for block in tool_blocks:
        is_parallel = _is_parallel_safe(block, registry)
        if is_parallel and batches and batches[-1].is_parallel:
            batches[-1].blocks.append(block)
        else:
            batches.append(ToolBatch(is_parallel=is_parallel, blocks=[block]))

    return batches
