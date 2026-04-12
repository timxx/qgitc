# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools._utils import run_git


class GitDiffRangeTool(Tool):
    name = "git_diff_range"
    description = (
        "Show git diff for a revision spec or range (e.g. A..B). "
        "Supports rename/copy detection and name-status mode for rename/move investigation."
    )

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        rev = input_data.get("rev", "")
        files = input_data.get("files")
        name_status = input_data.get("nameStatus", False)
        context_lines = input_data.get("contextLines", 3)
        find_renames = input_data.get("findRenames", True)

        args = ["diff"]
        if name_status:
            args += ["--name-status"]
        else:
            args += ["-U{}".format(context_lines)]

        if find_renames:
            args += ["-M", "-C"]

        args.append(rev)

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
                    "description": (
                        "A git diff revision spec (e.g. 'HEAD', 'A..B', 'A...B'). "
                        "Note: for two explicit revisions, prefer using a range like 'A..B'."
                    ),
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "If provided, limits the diff to these files.",
                },
                "nameStatus": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, show only file name changes (with rename detection).",
                },
                "contextLines": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 20,
                    "default": 3,
                    "description": "Number of context lines for the diff (default 3).",
                },
                "findRenames": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable rename/copy detection (-M -C).",
                },
            },
            "required": ["rev"],
            "additionalProperties": False,
        }
