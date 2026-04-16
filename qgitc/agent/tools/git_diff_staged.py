# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import run_git


class GitDiffStagedTool(Tool):
    name = "git_diff_staged"
    description = "Shows changes that are staged for commit"

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        name_only = input_data.get("nameOnly", False)
        files = input_data.get("files")

        if name_only:
            args = ["diff", "--name-only", "--cached"]
        else:
            args = ["diff-index", "--cached",
                    "HEAD", "-p", "--textconv",
                    "--submodule", "-C", "-U3"]
        if files:
            args += ["--"] + [str(f) for f in files]

        ok, output = run_git(context.working_directory, args)
        if not output:
            output = "No changed files found"
        return ToolResult(content=output, is_error=not ok)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "nameOnly": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, shows only names of changed files.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "If provided, limits the diff to these files.",
                },
            },
            "additionalProperties": False,
        }
