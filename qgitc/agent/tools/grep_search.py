# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult
from qgitc.tools.grepsearch import grepSearch


class GrepSearchTool(Tool):
    name = "grep_search"
    description = (
        "Search for text across files in the current repository.\n"
        "Use this tool when you want to search with an exact string or regex. "
        "If you are not sure what words will appear in the workspace, prefer "
        "using regex patterns with alternation (|) or character classes to search "
        "for multiple potential words at once instead of making separate searches. "
        "For example, use 'function|method|procedure' to look for all of those "
        "words at once."
    )

    def is_read_only(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        query = input_data.get("query")
        if not query:
            return ToolResult(content="query is required.", is_error=True)

        isRegexp = input_data.get("isRegexp")
        if isRegexp is None:
            return ToolResult(content="isRegexp is required.", is_error=True)

        includeIgnoredFiles = input_data.get("includeIgnoredFiles", False)
        includePattern = input_data.get("includePattern")
        maxResults = input_data.get("maxResults", 30)
        if not isinstance(maxResults, int) or maxResults < 1:
            maxResults = 30

        repoDir = context.working_directory
        if not repoDir:
            return ToolResult(
                content="No repository is currently opened.", is_error=True
            )

        try:
            output = grepSearch(
                repoDir=repoDir,
                query=query,
                isRegexp=isRegexp,
                includeIgnoredFiles=includeIgnoredFiles,
                includePattern=includePattern,
                maxResults=maxResults,
            )
        except Exception as e:
            return ToolResult(content=str(e), is_error=True)

        return ToolResult(content=output)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The pattern or text to search for. "
                        "Search is case-insensitive."
                    ),
                },
                "isRegexp": {
                    "type": "boolean",
                    "description": (
                        "Whether query should be treated as a regular expression."
                    ),
                },
                "includeIgnoredFiles": {
                    "type": "boolean",
                    "description": (
                        "If true, also search files ignored by .gitignore and "
                        "other Git ignore rules. Warning: using this may cause "
                        "the search to be slower. Only set it when you want to "
                        "search in ignored folders like node_modules or build outputs."
                    ),
                    "default": False,
                },
                "includePattern": {
                    "type": "string",
                    "description": (
                        "Optional glob pattern to filter files to search "
                        "(e.g. 'qgitc/**/*.py')."
                    ),
                },
                "maxResults": {
                    "type": "integer",
                    "description": (
                        "Maximum number of matches to return (default 30). "
                        "By default, only some matches are returned. If you use "
                        "this and don't see what you're looking for, you can try "
                        "again with a more specific query or a larger maxResults."
                    ),
                    "default": 30,
                    "minimum": 1,
                },
            },
            "required": ["query", "isRegexp"],
            "additionalProperties": False,
        }
