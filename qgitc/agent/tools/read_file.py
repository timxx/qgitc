# -*- coding: utf-8 -*-

import os
from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.tools.readfile import (
    buildReadFileOutput,
    normalizeToolFilePath,
    resolveRepoPath,
)


class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read the contents of a file, optionally specifying line ranges.\n"
        "If it is a relative path, treat it as relative to the repository root."
    )

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        filePath = normalizeToolFilePath(input_data.get("filePath", ""))
        if not filePath:
            return ToolResult(content="filePath is required.", is_error=True)

        repoDir = context.working_directory
        if not repoDir:
            return ToolResult(
                content="No repository is currently opened.", is_error=True
            )

        ok, absPathOrErr = resolveRepoPath(repoDir, filePath)
        if not ok:
            return ToolResult(content=absPathOrErr, is_error=True)
        if not os.path.isfile(absPathOrErr):
            return ToolResult(
                content="File does not exist: {}".format(absPathOrErr),
                is_error=True,
            )

        startLine = input_data.get("startLine")
        endLine = input_data.get("endLine")

        ok, outputOrErr = buildReadFileOutput(absPathOrErr, startLine, endLine)
        return ToolResult(content=outputOrErr, is_error=not ok)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filePath": {
                    "type": "string",
                    "description": "Path to the file to read.",
                },
                "startLine": {
                    "type": "integer",
                    "description": (
                        "Starting line number (1-based). "
                        "If not provided, starts from the beginning."
                    ),
                    "minimum": 1,
                },
                "endLine": {
                    "type": "integer",
                    "description": (
                        "Ending line number (1-based). "
                        "If not provided, reads until the end."
                    ),
                    "minimum": 1,
                },
            },
            "required": ["filePath"],
            "additionalProperties": False,
        }
