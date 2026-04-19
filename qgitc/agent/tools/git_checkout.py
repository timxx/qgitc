# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import runGit


class GitCheckoutTool(Tool):
    name = "git_checkout"
    description = "Switch branches"

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        branch = input_data.get("branch")
        if not branch:
            return ToolResult(
                content="Missing required parameter: branch",
                is_error=True,
            )

        args = ["checkout", str(branch)]
        ok, output = runGit(context.working_directory, args)
        if not ok:
            return ToolResult(content=output, is_error=True)
        return ToolResult(content=output)

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "branch": {
                    "type": "string",
                    "description": "Branch name to checkout",
                },
            },
            "required": ["branch"],
            "additionalProperties": False,
        }
