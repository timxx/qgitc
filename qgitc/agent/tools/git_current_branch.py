# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import runGit


class GitCurrentBranchTool(Tool):
    name = "git_current_branch"
    description = (
        "Get the current branch name. "
        "If in detached HEAD state, returns a detached HEAD message."
    )

    def isReadOnly(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        ok, output = runGit(context.working_directory,
                             ["rev-parse", "--abbrev-ref", "HEAD"])
        if not ok:
            return ToolResult(content=output, is_error=True)

        branch = output.strip()
        if not branch:
            return ToolResult(
                content="Failed to determine current branch.",
                is_error=True,
            )

        if branch == "HEAD":
            ok2, sha = runGit(context.working_directory,
                               ["rev-parse", "--short", "HEAD"])
            sha = (sha or "").strip() if ok2 else ""
            msg = "detached HEAD" + (" at {}".format(sha) if sha else "")
            return ToolResult(content=msg)

        return ToolResult(content=branch)

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
