# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import runGit


class GitStatusTool(Tool):
    name = "git_status"
    description = "Show the working tree status including branch info"

    def isReadOnly(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        args = ["status", "--porcelain=v1", "-b"]

        untracked = input_data.get("untracked", True)
        if not untracked:
            args.append("--untracked-files=no")

        ok, output = runGit(context.working_directory, args)
        if not ok:
            return ToolResult(content=output, is_error=True)

        # Porcelain v1 with -b typically includes a branch line like:
        #   ## main...origin/main [ahead 1]
        # If that's the only line, the working tree is clean.
        lines = output.splitlines()
        if not lines:
            output = "working tree clean (no changes)."
        elif len(lines) == 1 and lines[0].startswith("##"):
            output = "{}\nworking tree clean (no changes).".format(lines[0])

        return ToolResult(content=output)

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "untracked": {
                    "type": "boolean",
                    "description": "Include untracked files (default true).",
                    "default": True,
                },
            },
            "additionalProperties": False,
        }
