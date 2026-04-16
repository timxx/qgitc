# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import run_git


class GitShowTool(Tool):
    name = "git_show"
    description = "Show the contents of a commit"

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        rev = input_data.get("rev")
        if not rev:
            return ToolResult(
                content="Missing required parameter: rev", is_error=True
            )

        args = ["show", str(rev)]
        ok, output = run_git(context.working_directory, args)
        return ToolResult(content=output, is_error=not ok)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rev": {
                    "type": "string",
                    "description": "Commit-ish to show (sha, HEAD, tag, etc.).",
                },
            },
            "required": ["rev"],
            "additionalProperties": False,
        }
