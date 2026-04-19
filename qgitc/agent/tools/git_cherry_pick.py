# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import runGit


class GitCherryPickTool(Tool):
    name = "git_cherry_pick"
    description = "Cherry-pick one or more commits onto the current branch."

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        commits = input_data.get("commits")
        if not commits:
            return ToolResult(
                content="Missing required parameter: commits",
                is_error=True,
            )

        args = ["cherry-pick"] + [str(c) for c in commits]
        ok, output = runGit(context.working_directory, args)
        if not ok:
            return ToolResult(content=output, is_error=True)
        return ToolResult(content=output)

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "commits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "List of commit SHAs to cherry-pick",
                },
            },
            "required": ["commits"],
            "additionalProperties": False,
        }
