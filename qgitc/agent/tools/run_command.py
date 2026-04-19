# -*- coding: utf-8 -*-

import os
import subprocess
from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult


class RunCommandTool(Tool):
    name = "run_command"
    description = (
        "Execute an arbitrary command in the repository directory or a specified directory.\n"
        "This tool allows running any shell command when needed. Use with caution as "
        "it can execute potentially destructive commands."
    )

    def isReadOnly(self):
        return False

    def isDestructive(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        command = input_data.get("command")
        if not command:
            return ToolResult(content="command is required.", is_error=True)

        working_dir = input_data.get("workingDir") or context.working_directory

        if not working_dir or not os.path.isdir(working_dir):
            return ToolResult(
                content="Invalid working directory: {}".format(working_dir),
                is_error=True,
            )

        timeout = input_data.get("timeout", 60)
        if not isinstance(timeout, (int, float)):
            timeout = 60
        timeout = max(1, min(int(timeout), 300))

        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(
                command,
                shell=True,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
            )

            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                return ToolResult(
                    content="Command timed out after {} seconds.\nPartial output:\n{}{}".format(
                        timeout, stdout or "", stderr or ""
                    ),
                    is_error=True,
                )

            ok = process.returncode == 0
            output = (stdout or "").strip("\n")

            # Only include stderr when the command fails.
            if not ok:
                err_text = (stderr or "").strip("\n")
                if err_text:
                    if output:
                        output += "\n"
                    output += err_text

            if not output:
                output = "Command executed {} (no output).".format(
                    "successfully" if ok else "with errors"
                )

            return ToolResult(content=output, is_error=not ok)

        except Exception as e:
            return ToolResult(
                content="Failed to execute command: {}".format(e),
                is_error=True,
            )

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "The command to execute. This should be a complete shell command."
                    ),
                },
                "workingDir": {
                    "type": "string",
                    "description": (
                        "Optional working directory. If not specified, "
                        "uses the repository directory."
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        "Maximum execution time in seconds (default 60, max 300)."
                    ),
                    "default": 60,
                    "minimum": 1,
                    "maximum": 300,
                },
                "explanation": {
                    "type": "string",
                    "description": (
                        "A short explanation of why this command is being run."
                    ),
                },
            },
            "required": ["command", "explanation"],
            "additionalProperties": False,
        }
