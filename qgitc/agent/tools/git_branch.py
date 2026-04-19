# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import runGit


class GitBranchTool(Tool):
    name = "git_branch"
    description = "List Git branches"

    def isReadOnly(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        args = ["branch"]
        if input_data.get("all", False):
            args.append("-a")

        ok, output = runGit(context.working_directory, args)
        if not ok:
            return ToolResult(content=output, is_error=True)
        return ToolResult(content=output)

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "all": {
                    "type": "boolean",
                    "description": "If true, include remotes (`-a`).",
                    "default": False,
                },
            },
            "additionalProperties": False,
        }
