# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.agent.tools.utils import run_git


class GitLogTool(Tool):
    name = "git_log"
    description = (
        "Show commit history. By default shows repository-wide history. "
        "If you pass `path`, shows history for that file and can follow renames."
    )

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        nth = input_data.get("nth")
        max_count = input_data.get("maxCount", 20)
        since = input_data.get("since")
        until = input_data.get("until")
        name_status = input_data.get("nameStatus", False)
        rev = input_data.get("rev")
        path = input_data.get("path")
        follow = input_data.get("follow", True)

        args = ["log", "--oneline"]
        if nth:
            args += ["-n", "1", "--skip", str(nth - 1)]
        else:
            args += ["-n", str(max_count)]

        if since:
            args += ["--since", since]
        if until:
            args += ["--until", until]
        if name_status:
            args.append("--name-status")
        if rev:
            args.append(rev)

        if path:
            if follow:
                args.append("--follow")
            args += ["--", path]

        ok, output = run_git(context.working_directory, args)
        if ok:
            if nth:
                line = output.splitlines()[0].strip() if output.strip() else ""
                if line:
                    label = "nth={} (1-based from HEAD)".format(nth)
                    if path:
                        label += " (filtered by path={})".format(path)
                    return ToolResult(content="{}: {}".format(label, line))
                return ToolResult(
                    content="No commit found at nth={} (1-based from HEAD).".format(nth),
                    is_error=True,
                )

        if ok and not output.strip():
            output = "No commits found."

        return ToolResult(content=output, is_error=not ok)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "nth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10000,
                    "description": "Fetch only the Nth commit from HEAD (1-based). If set, returns exactly one commit.",
                },
                "maxCount": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 20,
                    "description": "Number of commits to show (default 20).",
                },
                "since": {
                    "type": "string",
                    "description": "Show commits more recent than a specific date (e.g., '2 weeks ago', '2023-01-01').",
                },
                "until": {
                    "type": "string",
                    "description": "Show commits older than a specific date.",
                },
                "rev": {
                    "type": "string",
                    "description": (
                        "Optional revision/range to start from (e.g. 'HEAD', a SHA, 'main', or 'A..B'). "
                        "If omitted, uses the current HEAD."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Optional file path to filter history by. "
                        "When set, git_log becomes file history (equivalent to `git log -- <path>`)."
                    ),
                },
                "follow": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When path is set: follow renames (equivalent to --follow). "
                        "Ignored when path is not set."
                    ),
                },
                "nameStatus": {
                    "type": "boolean",
                    "default": False,
                    "description": "When set: include --name-status (helps detect renames/moves).",
                },
            },
            "additionalProperties": False,
        }
