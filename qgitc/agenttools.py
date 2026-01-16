# -*- coding: utf-8 -*-

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class ToolType:
    """Tool type categorization for visual distinction"""
    READ_ONLY = 0   # Safe operations: status, log, diff
    WRITE = 1       # Modifying operations: commit, checkout, merge
    DANGEROUS = 2   # Potentially destructive: reset, force push


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    tool_type: int
    parameters: Dict[str, Any]

    def to_openai_tool(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class AgentToolRegistry:
    """Registry of git tools exposed to the LLM in Agent mode."""

    @staticmethod
    def tools() -> List[AgentTool]:
        # Keep this list small and safe; expand in future phases.
        return [
            AgentTool(
                name="git_status",
                description=(
                    "Show repository status (like `git status --porcelain -b`). "
                    "If there are no changes, the result explicitly includes 'working tree clean (no changes)'."
                ),
                tool_type=ToolType.READ_ONLY,
                parameters={
                    "type": "object",
                    "properties": {
                        "repo_dir": {
                            "type": "string",
                            "description": "Optional repo directory. Defaults to current repo.",
                        },
                        "untracked": {
                            "type": "boolean",
                            "description": "Include untracked files (default true).",
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            AgentTool(
                name="git_log",
                description=(
                    "Show commits. Use `nth` to fetch only the Nth commit from HEAD (1-based) without listing earlier commits. "
                    "When `nth` is provided, the tool returns exactly one labeled line like 'nth=N (1-based from HEAD): <sha> <subject>'. "
                    "Do not request commits 1..N just to locate the Nth commit."
                ),
                tool_type=ToolType.READ_ONLY,
                parameters={
                    "type": "object",
                    "properties": {
                        "repo_dir": {"type": "string"},
                        "nth": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10000,
                            "description": "Fetch only the Nth commit from HEAD (1-based). If set, returns exactly one commit.",
                        },
                        "max_count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "description": "Number of commits to show (default 20).",
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            AgentTool(
                name="git_diff",
                description="Show working tree diff (optionally staged).",
                tool_type=ToolType.READ_ONLY,
                parameters={
                    "type": "object",
                    "properties": {
                        "repo_dir": {"type": "string"},
                        "staged": {
                            "type": "boolean",
                            "description": "If true, show staged diff (`--staged`).",
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            AgentTool(
                name="git_show",
                description="Show a commit (like `git show <rev>`).",
                tool_type=ToolType.READ_ONLY,
                parameters={
                    "type": "object",
                    "properties": {
                        "repo_dir": {"type": "string"},
                        "rev": {
                            "type": "string",
                            "description": "Commit-ish to show (sha, HEAD, tag, etc.).",
                        },
                    },
                    "required": ["rev"],
                    "additionalProperties": False,
                },
            ),
            AgentTool(
                name="git_branch",
                description="List branches (like `git branch` / `git branch -a`).",
                tool_type=ToolType.READ_ONLY,
                parameters={
                    "type": "object",
                    "properties": {
                        "repo_dir": {"type": "string"},
                        "all": {
                            "type": "boolean",
                            "description": "If true, include remotes (`-a`).",
                        },
                    },
                    "additionalProperties": False,
                },
            ),
            AgentTool(
                name="git_current_branch",
                description=(
                    "Get the current branch name only (no branch listing). "
                    "Uses `git rev-parse --abbrev-ref HEAD`. "
                    "If in detached HEAD state, returns a detached HEAD message."
                ),
                tool_type=ToolType.READ_ONLY,
                parameters={
                    "type": "object",
                    "properties": {
                        "repo_dir": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ),
            AgentTool(
                name="git_checkout",
                description="Checkout a branch (like `git checkout <branch>`).",
                tool_type=ToolType.WRITE,
                parameters={
                    "type": "object",
                    "properties": {
                        "repo_dir": {"type": "string"},
                        "branch": {"type": "string"},
                    },
                    "required": ["branch"],
                    "additionalProperties": False,
                },
            ),
            AgentTool(
                name="git_cherry_pick",
                description="Cherry-pick one or more commits onto the current branch.",
                tool_type=ToolType.WRITE,
                parameters={
                    "type": "object",
                    "properties": {
                        "repo_dir": {"type": "string"},
                        "commits": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        },
                    },
                    "required": ["commits"],
                    "additionalProperties": False,
                },
            ),
        ]

    @staticmethod
    def tool_by_name(name: str) -> Optional[AgentTool]:
        for tool in AgentToolRegistry.tools():
            if tool.name == name:
                return tool
        return None

    @staticmethod
    def openai_tools() -> List[Dict[str, Any]]:
        return [t.to_openai_tool() for t in AgentToolRegistry.tools()]


def parseToolArguments(arguments: Any) -> Dict[str, Any]:
    """Tool-call arguments can be either a dict or a JSON string."""
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        arguments = arguments.strip()
        if not arguments:
            return {}
        try:
            value = json.loads(arguments)
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    return {}
