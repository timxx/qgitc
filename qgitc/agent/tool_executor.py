# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from typing import List

from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import ToolUseBlock


@dataclass
class ToolBatch:
    is_parallel: bool = False
    blocks: List[ToolUseBlock] = field(default_factory=list)


def _is_parallel_safe(block: ToolUseBlock, registry: ToolRegistry) -> bool:
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
