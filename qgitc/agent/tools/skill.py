# -*- coding: utf-8 -*-

from typing import Any, Dict

from qgitc.agent.tool import Tool, ToolContext, ToolResult


class SkillTool(Tool):
    name = "Skill"
    description = "Execute a skill by name and load its instructions"

    def is_read_only(self):
        return True

    def _resolve_registry(self, context):
        # type: (ToolContext) -> Any
        return context.extra.get("skill_registry") if context.extra else None

    def _substitute_arguments(self, content, args):
        # type: (str, str) -> str
        if not args:
            return content

        replaced = content.replace("$ARGUMENTS", args)
        if replaced == content:
            return content + "\n\nARGUMENTS: {}".format(args)
        return replaced

    def execute(self, input_data: Dict[str, Any], context: ToolContext) -> ToolResult:
        skill_name = (input_data.get("skill") or "").strip()
        args = input_data.get("args") or ""

        if skill_name.startswith("/"):
            skill_name = skill_name[1:]

        if not skill_name:
            return ToolResult(content="skill is required", is_error=True)

        registry = self._resolve_registry(context)
        if registry is None:
            return ToolResult(content="No skill registry available", is_error=True)

        skill = registry.get(skill_name)
        if skill is None:
            return ToolResult(content="Unknown skill: {}".format(skill_name), is_error=True)

        if skill.disable_model_invocation:
            return ToolResult(
                content="Skill {} cannot be model-invoked".format(skill_name),
                is_error=True,
            )

        content = self._substitute_arguments(skill.content, args)

        # Keep common substitutions to align with external skill format conventions.
        if skill.skill_root:
            normalized_root = skill.skill_root.replace("\\", "/")
            content = content.replace("${CLAUDE_SKILL_DIR}", normalized_root)
        session_id = context.extra.get("session_id") if context.extra else None
        if session_id:
            content = content.replace("${CLAUDE_SESSION_ID}", str(session_id))

        if skill.allowed_tools:
            context.extra["tool_allowed_tools"] = list(skill.allowed_tools)

        return ToolResult(content=content)

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "Skill name to invoke.",
                },
                "args": {
                    "type": "string",
                    "description": "Optional arguments passed into the skill.",
                },
            },
            "required": ["skill"],
            "additionalProperties": False,
        }
