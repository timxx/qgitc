# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import runGit


class GitShowIndexFileTool(Tool):
    name = "git_show_index_file"
    description = (
        "Show the contents of a staged (index) file (equivalent to 'git show :path').\n"
        "Useful when reviewing staged changes where the working tree may differ.\n"
        "Supports optional line range selection."
    )

    def isReadOnly(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        path = input_data.get("path")
        if not path:
            return ToolResult(
                content="Missing required parameter: path", is_error=True
            )

        spec = ":{}".format(path)
        ok, output = runGit(context.working_directory, ["show", spec])
        if not ok:
            return ToolResult(content=output, is_error=True)

        lines = output.splitlines()
        start_line = input_data.get("startLine")
        end_line = input_data.get("endLine")
        start = (start_line - 1) if start_line else 0
        end = end_line if end_line else len(lines)
        output = "\n".join(lines[start:end])

        return ToolResult(content=output)

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path within the repository to read from the index (staged).",
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
            "required": ["path"],
            "additionalProperties": False,
        }
