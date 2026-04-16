# -*- coding: utf-8 -*-

import os
from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.read_file import buildReadFileOutput, normalizeToolFilePath


class ReadExternalFileTool(Tool):
    name = "read_external_file"
    description = (
        "Read a file by absolute path on the host machine "
        "(may be inside or outside the repository).\n"
        "Use this only when you explicitly need to inspect an absolute-path file "
        "(e.g. system config, logs), and only after the user approves the action.\n"
        "Do NOT use this tool for repo-relative paths; use read_file instead."
    )

    def is_read_only(self):
        return False

    def is_destructive(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        filePath = normalizeToolFilePath(input_data.get("filePath", ""))
        if not filePath:
            return ToolResult(content="filePath is required.", is_error=True)
        if not os.path.isabs(filePath):
            return ToolResult(
                content="read_external_file requires an absolute filePath.",
                is_error=True,
            )

        absPath = os.path.abspath(filePath)
        if not os.path.isfile(absPath):
            return ToolResult(
                content="File does not exist: {}".format(absPath),
                is_error=True,
            )

        startLine = input_data.get("startLine")
        endLine = input_data.get("endLine")

        ok, outputOrErr = buildReadFileOutput(absPath, startLine, endLine)
        return ToolResult(content=outputOrErr, is_error=not ok)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filePath": {
                    "type": "string",
                    "description": (
                        "Absolute path to a file to read (outside the repository)."
                    ),
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
                "explanation": {
                    "type": "string",
                    "description": (
                        "Why you need to read this file. The user will see this "
                        "in the approval UI. Prefer a clear, minimal explanation."
                    ),
                },
            },
            "required": ["filePath", "explanation"],
            "additionalProperties": False,
        }
