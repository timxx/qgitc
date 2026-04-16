# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import run_git


class GitShowFileTool(Tool):
    name = "git_show_file"
    description = (
        "Show the contents of a file at a specific revision (e.g. 'HEAD:path/to/file').\n"
        "Useful for code review when the working tree may differ from the commit being reviewed.\n"
        "Supports optional line range selection."
    )

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        rev = input_data.get("rev")
        if not rev:
            return ToolResult(
                content="Missing required parameter: rev", is_error=True
            )

        path = input_data.get("path")
        if not path:
            return ToolResult(
                content="Missing required parameter: path", is_error=True
            )

        spec = "{}:{}".format(rev, path)
        ok, output = run_git(context.working_directory, ["show", spec])
        if not ok:
            return ToolResult(content=output, is_error=True)

        lines = output.splitlines()
        start_line = input_data.get("startLine")
        end_line = input_data.get("endLine")
        start = (start_line - 1) if start_line else 0
        end = end_line if end_line else len(lines)
        output = "\n".join(lines[start:end])

        return ToolResult(content=output)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rev": {
                    "type": "string",
                    "description": "Commit-ish to read from (sha, HEAD, tag, etc.).",
                },
                "path": {
                    "type": "string",
                    "description": "File path within the repository at that revision.",
                },
                "startLine": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Starting line number (1-based). If not provided, starts from the beginning.",
                },
                "endLine": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Ending line number (1-based). If not provided, reads until the end.",
                },
            },
            "required": ["rev", "path"],
            "additionalProperties": False,
        }
