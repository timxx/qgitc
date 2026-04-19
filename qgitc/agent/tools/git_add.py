# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import runGit


class GitAddTool(Tool):
    name = "git_add"
    description = "Add file contents to the index"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        files = input_data.get("files")
        if not files:
            return ToolResult(
                content="Missing required parameter: files",
                is_error=True,
            )

        args = ["add"] + [str(f) for f in files]
        ok, output = runGit(context.working_directory, args)
        if not ok:
            return ToolResult(content=output, is_error=True)
        return ToolResult(content=output)

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "List of file paths to stage.",
                },
            },
            "required": ["files"],
            "additionalProperties": False,
        }
