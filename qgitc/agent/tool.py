# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


@dataclass
class ToolContext:
    working_directory: str
    abort_requested: Callable[[], bool]
    extra: Dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    name: str = ""
    description: str = ""

    def isReadOnly(self) -> bool:
        return False

    def isDestructive(self) -> bool:
        return False

    @abstractmethod
    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        ...

    @abstractmethod
    def inputSchema(self) -> Dict[str, Any]:
        ...

    def openaiSchema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.inputSchema(),
            },
        }


class ToolType:
    """Tool type constants for UI rendering."""
    READ_ONLY = 0
    WRITE = 1
    DANGEROUS = 2


def toolTypeFromTool(tool):
    # type: (Tool) -> int
    """Convert Tool boolean flags to ToolType constant for UI."""
    if tool.isDestructive():
        return ToolType.DANGEROUS
    if tool.isReadOnly():
        return ToolType.READ_ONLY
    return ToolType.WRITE
