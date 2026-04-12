# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


@dataclass
class ToolContext:
    working_directory: str
    abort_requested: Callable[[], bool]


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
