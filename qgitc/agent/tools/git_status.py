# -*- coding: utf-8 -*-

import subprocess
from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult


class GitStatusTool(Tool):
    name = "git_status"
    description = "Show the working tree status including branch info"

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain", "-b"],
                cwd=context.working_directory,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            return ToolResult(
                content="git executable not found", is_error=True
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                content="git status timed out after 30 seconds",
                is_error=True,
            )
        except OSError as e:
            return ToolResult(content=str(e), is_error=True)

        if proc.returncode != 0:
            error_msg = proc.stderr.strip() if proc.stderr else (
                "git status failed with exit code {}".format(proc.returncode)
            )
            return ToolResult(content=error_msg, is_error=True)

        return ToolResult(content=proc.stdout)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
