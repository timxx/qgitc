# -*- coding: utf-8 -*-

from typing import Any, Dict, List, Optional

from qgitc.agent.tool import Tool


class ToolRegistry:

    def __init__(self):
        self._tools = {}  # type: Dict[str, Tool]

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [tool.openai_schema() for tool in self._tools.values()]
