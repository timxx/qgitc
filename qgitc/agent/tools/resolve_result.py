# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult


class ResolveResultTool(Tool):
    name = "resolve_result"
    description = "Record the final status of a resolve session"

    def __init__(self, resolveContext):
        self._resolveContext = resolveContext

    def isReadOnly(self):
        return True

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        status = input_data.get("status", "").strip()
        reason = input_data.get("reason", "").strip()

        if status not in ("ok", "failed"):
            return ToolResult(
                content="status must be 'ok' or 'failed'",
                is_error=True,
            )

        self._resolveContext.setResult(status, reason)
        return ToolResult(content="Recorded resolve result: {}".format(status))

    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["ok", "failed"],
                    "description": "Resolve status.",
                },
                "reason": {
                    "type": "string",
                    "description": "Short summary of the outcome.",
                },
            },
            "required": ["status"],
            "additionalProperties": False,
        }
