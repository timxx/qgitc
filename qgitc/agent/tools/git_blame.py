# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import run_git


class GitBlameTool(Tool):
    name = "git_blame"
    description = (
        "Show blame information for a file (optionally for a line range). "
        "Useful for understanding intent/ownership around conflicted lines."
    )

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        path = input_data.get("path")
        if not path:
            return ToolResult(
                content="Missing required parameter: path", is_error=True
            )

        args = ["blame"]

        ignore_whitespace = input_data.get("ignoreWhitespace", True)
        if ignore_whitespace:
            args.append("-w")

        start_line = input_data.get("startLine")
        end_line = input_data.get("endLine")

        if start_line and end_line:
            args += ["-L", "{},{}".format(start_line, end_line)]
        elif start_line and not end_line:
            args += ["-L", "{},".format(start_line)]
        elif end_line:
            args += ["-L", "1,{}".format(end_line)]

        rev = input_data.get("rev")
        if rev:
            args.append(str(rev))

        args += ["--", path]

        ok, output = run_git(context.working_directory, args)
        if ok and not output.strip():
            output = "No blame output"
        return ToolResult(content=output, is_error=not ok)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path within the repository to blame.",
                },
                "rev": {
                    "type": "string",
                    "description": (
                        "Optional revision to blame (e.g. 'HEAD', a SHA, or a branch name). "
                        "If omitted, defaults to HEAD."
                    ),
                },
                "startLine": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Starting line number (1-based). If not provided, starts from the beginning.",
                },
                "endLine": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Ending line number (1-based). If not provided, blames until the end.",
                },
                "ignoreWhitespace": {
                    "type": "boolean",
                    "description": "If true, ignore whitespace changes (-w).",
                    "default": True,
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }
