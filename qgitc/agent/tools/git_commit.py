# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import run_git


class GitCommitTool(Tool):
    name = "git_commit"
    description = "Record changes to the repository"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        message = input_data.get("message")
        if not message:
            return ToolResult(
                content="Missing required parameter: message",
                is_error=True,
            )

        args = ["commit", "-m", str(message), "--no-edit"]
        ok, output = run_git(context.working_directory, args)
        if not ok:
            return ToolResult(content=output, is_error=True)
        return ToolResult(content=output)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message",
                },
            },
            "required": ["message"],
            "additionalProperties": False,
        }
