# -*- coding: utf-8 -*-

import os
from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult


class CreateFileTool(Tool):
    name = "create_file"
    description = (
        "Create a new file with the given content. The directory will be "
        "created if it does not already exist. Never use this tool to edit "
        "a file that already exists."
    )

    def is_read_only(self):
        return False

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        filePath = input_data.get("filePath")
        if not filePath:
            return ToolResult(content="filePath is required.", is_error=True)

        content = input_data.get("content")
        if content is None:
            return ToolResult(content="content is required.", is_error=True)

        repoDir = context.working_directory
        if not repoDir or not os.path.isdir(repoDir):
            return ToolResult(
                content="No repository is currently opened.", is_error=True
            )

        # Normalize path: strip whitespace and quotes
        filePath = (filePath or "").strip().strip('"').strip("'")

        # Handle Unix-style absolute paths on Windows
        if os.name == "nt" and filePath.startswith("/") and filePath.find(":") != 1:
            filePath = filePath.lstrip("/")

        if os.path.isabs(filePath):
            absPath = os.path.abspath(filePath)
        else:
            absPath = os.path.abspath(os.path.join(repoDir, filePath))

        # Ensure the resolved path stays within the repo
        try:
            repoRoot = os.path.abspath(repoDir)
            common = os.path.commonpath([repoRoot, absPath])
        except Exception:
            return ToolResult(
                content="Invalid file path: {}".format(filePath),
                is_error=True,
            )

        if common != repoRoot:
            return ToolResult(
                content="Refusing to access paths outside the repository: {}".format(
                    filePath
                ),
                is_error=True,
            )

        if os.path.exists(absPath):
            return ToolResult(
                content="File already exists: {}".format(absPath),
                is_error=True,
            )

        parent = os.path.dirname(absPath)
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception as e:
            return ToolResult(
                content="Failed to create directories: {}".format(e),
                is_error=True,
            )

        try:
            with open(absPath, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            rel = os.path.relpath(absPath, repoDir)
            size = os.path.getsize(absPath)
            return ToolResult(content="Created {} ({} bytes).".format(rel, size))
        except Exception as e:
            return ToolResult(
                content="Failed to create file: {}".format(e), is_error=True
            )

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filePath": {
                    "type": "string",
                    "description": (
                        "The absolute path to the file to create."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file.",
                },
            },
            "required": ["filePath", "content"],
            "additionalProperties": False,
        }
