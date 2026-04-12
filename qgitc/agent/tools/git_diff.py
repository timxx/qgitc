# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools._utils import run_git


class GitDiffTool(Tool):
    name = "git_diff"
    description = (
        "Get the diff (patch) introduced by a specific commit (commit-ish). "
        "For comparing two revisions/ranges (A..B / A...B) or investigating renames, use git_diff_range."
    )

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        rev = input_data.get("rev", "")
        files = input_data.get("files")

        args = ["diff-tree", "-r", "--root", rev,
                "-p", "--textconv", "--submodule",
                "-C", "--no-commit-id", "-U3"]
        if files:
            args += ["--"] + [str(f) for f in files]

        ok, output = run_git(context.working_directory, args)
        if ok and not output.strip():
            output = "No differences found"
        return ToolResult(content=output, is_error=not ok)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rev": {
                    "type": "string",
                    "description": "A single commit-ish to diff (typically a commit SHA).",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "If provided, limits the diff to these files.",
                },
            },
            "required": ["rev"],
            "additionalProperties": False,
        }
