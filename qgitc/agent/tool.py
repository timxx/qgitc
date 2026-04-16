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

    def is_read_only(self) -> bool:
        return False

    def is_destructive(self) -> bool:
        return False

    @abstractmethod
    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        ...

    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        ...

    def openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema(),
            },
        }


class ToolType:
    """Tool type constants for UI rendering."""
    READ_ONLY = 0
    WRITE = 1
    DANGEROUS = 2


def tool_type_from_tool(tool):
    # type: (Tool) -> int
    """Convert Tool boolean flags to ToolType constant for UI."""
    if tool.is_destructive():
        return ToolType.DANGEROUS
    if tool.is_read_only():
        return ToolType.READ_ONLY
    return ToolType.WRITE
