# -*- coding: utf-8 -*-

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from qgitc.basemodel import BaseModel, Field
from qgitc.tools.applypatch import APPLY_PATCH_TOOL_DESC


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
    model_class: Optional[Type[BaseModel]] = None

    def to_openai_tool(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class GitStatusParams(BaseModel):
    """Parameters for git_status tool."""
    repo_dir: Optional[str] = Field(
        None, description="Optional repo directory. Defaults to current repo.")
    untracked: bool = Field(
        True, description="Include untracked files (default true).")


class GitLogParams(BaseModel):
    """Parameters for git_log tool."""
    repo_dir: Optional[str] = None
    nth: Optional[int] = Field(
        None, ge=1, le=10000, description="Fetch only the Nth commit from HEAD (1-based). If set, returns exactly one commit.")
    max_count: Optional[int] = Field(
        20, ge=1, le=200, description="Number of commits to show (default 20).")
    since: Optional[str] = Field(
        None, description="Show commits more recent than a specific date (e.g., '2 weeks ago', '2023-01-01').")
    until: Optional[str] = Field(
        None, description="Show commits older than a specific date.")


class GitDiffParams(BaseModel):
    """Parameters for git_diff tool."""
    repo_dir: Optional[str] = None
    rev: str = Field(...,
                     description="The commit SHA or revision range to diff")
    files: Optional[List[str]] = Field(
        None, description="If provided, limits the diff to these files.")


class GitDiffUnstagedParams(BaseModel):
    """Parameters for git_diff_unstaged tool."""
    repo_dir: Optional[str] = None
    name_only: bool = Field(
        False, description="If true, shows only names of changed files.")
    files: Optional[List[str]] = Field(
        None, description="If provided, limits the diff to these files.")


class GitDiffStagedParams(BaseModel):
    """Parameters for git_diff_staged tool."""
    repo_dir: Optional[str] = None
    name_only: bool = Field(
        False, description="If true, shows only names of changed files.")
    files: Optional[List[str]] = Field(
        None, description="If provided, limits the diff to these files.")


class GitShowParams(BaseModel):
    """Parameters for git_show tool."""
    repo_dir: Optional[str] = None
    rev: str = Field(...,
                     description="Commit-ish to show (sha, HEAD, tag, etc.).")


class GitShowFileParams(BaseModel):
    """Parameters for git_show_file tool."""
    repo_dir: Optional[str] = None
    rev: str = Field(...,
                     description="Commit-ish to read from (sha, HEAD, tag, etc.).")
    path: str = Field(...,
                      description="File path within the repository at that revision.")
    start_line: Optional[int] = Field(
        None, ge=1, description="Starting line number (1-based). If not provided, starts from the beginning.")
    end_line: Optional[int] = Field(
        None, ge=1, description="Ending line number (1-based). If not provided, reads until the end.")


class GitShowIndexFileParams(BaseModel):
    """Parameters for git_show_index_file tool."""
    repo_dir: Optional[str] = None
    path: str = Field(..., description="File path within the repository to read from the index (staged).")
    start_line: Optional[int] = Field(
        None, ge=1, description="Starting line number (1-based). If not provided, starts from the beginning.")
    end_line: Optional[int] = Field(
        None, ge=1, description="Ending line number (1-based). If not provided, reads until the end.")


class GitCurrentBranchParams(BaseModel):
    """Parameters for git_current_branch tool."""
    repo_dir: Optional[str] = None


class GitBranchParams(BaseModel):
    """Parameters for git_branch tool."""
    repo_dir: Optional[str] = None
    all: bool = Field(False, description="If true, include remotes (`-a`).")


class GitCheckoutParams(BaseModel):
    """Parameters for git_checkout tool."""
    repo_dir: Optional[str] = None
    branch: str = Field(..., description="Branch name to checkout")


class GitCherryPickParams(BaseModel):
    """Parameters for git_cherry_pick tool."""
    repo_dir: Optional[str] = None
    commits: List[str] = Field(..., min_length=1,
                               description="List of commit SHAs to cherry-pick")


class GitCommitParams(BaseModel):
    """Parameters for git_commit tool."""
    repo_dir: Optional[str] = None
    message: str = Field(..., description="Commit message")


class GitAddParams(BaseModel):
    """Parameters for git_add tool."""
    repo_dir: Optional[str] = None
    files: List[str] = Field(..., min_length=1,
                             description="List of file paths to stage.")


class RunCommandParams(BaseModel):
    """Parameters for run_command tool."""
    command: str = Field(
        ..., description="The command to execute. This should be a complete shell command.")
    working_dir: Optional[str] = Field(
        None, description="Optional working directory. If not specified, uses the repository directory.")
    timeout: int = Field(
        60, ge=1, le=300, description="Maximum execution time in seconds (default 60, max 300).")


class ReadFileParams(BaseModel):
    """Parameters for read_file tool."""
    file_path: str = Field(..., description="Path to the file to read.")
    start_line: Optional[int] = Field(
        None, ge=1, description="Starting line number (1-based). If not provided, starts from the beginning.")
    end_line: Optional[int] = Field(
        None, ge=1, description="Ending line number (1-based). If not provided, reads until the end.")


class CreateFileParams(BaseModel):
    """Parameters for create_file tool."""
    filePath: str = Field(..., description="The absolute path to the file to create.")
    content: str = Field(..., description="The content to write to the file.")


class ApplyPatchParams(BaseModel):
    """Parameters for apply_patch tool (V4A diff format)."""
    input: str = Field(..., description="The edit patch to apply (V4A format).")
    explanation: str = Field(..., description="A short description of what the patch is aiming to achieve.")


# ==================== Helper Function ====================

def create_tool_from_model(
    name: str,
    description: str,
    tool_type: int,
    model_class: Type[BaseModel]
) -> AgentTool:
    """Create an AgentTool from a BaseModel."""
    schema = model_class.model_json_schema()
    # Convert BaseModel schema to OpenAI tool schema
    parameters = {
        "type": "object",
        "properties": schema.get("properties", {}),
        "additionalProperties": False,
    }
    if "required" in schema:
        parameters["required"] = schema["required"]

    return AgentTool(
        name=name,
        description=description,
        tool_type=tool_type,
        parameters=parameters,
        model_class=model_class,
    )


class AgentToolRegistry:
    """Registry of git tools exposed to the LLM in Agent mode."""

    _openai_tools: Optional[List[Dict[str, Any]]] = None
    _cached_tools: Optional[List[AgentTool]] = None

    @staticmethod
    def tools() -> List[AgentTool]:
        if AgentToolRegistry._cached_tools is None:
            AgentToolRegistry._cached_tools = AgentToolRegistry._createTools()
        return AgentToolRegistry._cached_tools

    @staticmethod
    def _createTools() -> List[AgentTool]:
        return [
            create_tool_from_model(
                name="git_status",
                description=(
                    "Shows the working tree status. "
                    "If there are no changes, the result explicitly includes 'working tree clean (no changes)'."
                ),
                tool_type=ToolType.READ_ONLY,
                model_class=GitStatusParams,
            ),
            create_tool_from_model(
                name="git_log",
                description="Show commit logs. Can filter by date range and limit number of commits.",
                tool_type=ToolType.READ_ONLY,
                model_class=GitLogParams,
            ),
            create_tool_from_model(
                name="git_diff",
                description="Get the diff of a specific commit",
                tool_type=ToolType.READ_ONLY,
                model_class=GitDiffParams,
            ),
            create_tool_from_model(
                name="git_diff_unstaged",
                description="Shows changes in the working directory that are not yet staged",
                tool_type=ToolType.READ_ONLY,
                model_class=GitDiffUnstagedParams,
            ),
            create_tool_from_model(
                name="git_diff_staged",
                description="Shows changes that are staged for commit",
                tool_type=ToolType.READ_ONLY,
                model_class=GitDiffStagedParams,
            ),
            create_tool_from_model(
                name="git_show",
                description="Show the contents of a commit",
                tool_type=ToolType.READ_ONLY,
                model_class=GitShowParams,
            ),
            create_tool_from_model(
                name="git_show_file",
                description=(
                    "Show the contents of a file at a specific revision (e.g. 'HEAD:path/to/file').\n"
                    "Useful for code review when the working tree may differ from the commit being reviewed.\n"
                    "Supports optional line range selection."
                ),
                tool_type=ToolType.READ_ONLY,
                model_class=GitShowFileParams,
            ),
            create_tool_from_model(
                name="git_show_index_file",
                description=(
                    "Show the contents of a staged (index) file (equivalent to 'git show :path').\n"
                    "Useful when reviewing staged changes where the working tree may differ.\n"
                    "Supports optional line range selection."
                ),
                tool_type=ToolType.READ_ONLY,
                model_class=GitShowIndexFileParams,
            ),
            create_tool_from_model(
                name="git_current_branch",
                description=(
                    "Get the current branch name. "
                    "If in detached HEAD state, returns a detached HEAD message."
                ),
                tool_type=ToolType.READ_ONLY,
                model_class=GitCurrentBranchParams,
            ),
            create_tool_from_model(
                name="git_branch",
                description="List Git branches",
                tool_type=ToolType.READ_ONLY,
                model_class=GitBranchParams,
            ),
            create_tool_from_model(
                name="git_checkout",
                description="Switch branches",
                tool_type=ToolType.WRITE,
                model_class=GitCheckoutParams,
            ),
            create_tool_from_model(
                name="git_cherry_pick",
                description="Cherry-pick one or more commits onto the current branch.",
                tool_type=ToolType.WRITE,
                model_class=GitCherryPickParams,
            ),
            create_tool_from_model(
                name="git_commit",
                description="Record changes to the repository",
                tool_type=ToolType.WRITE,
                model_class=GitCommitParams,
            ),
            create_tool_from_model(
                name="git_add",
                description="Add file contents to the index",
                tool_type=ToolType.WRITE,
                model_class=GitAddParams,
            ),
            create_tool_from_model(
                name="run_command",
                description=(
                    "Execute an arbitrary command in the repository directory or a specified directory.\n"
                    "This tool allows running any shell command when needed. Use with caution as "
                    "it can execute potentially destructive commands."
                ),
                tool_type=ToolType.DANGEROUS,
                model_class=RunCommandParams,
            ),
            create_tool_from_model(
                name="read_file",
                description=(
                    "Read the contents of a file, optionally specifying line ranges.\n"
                    "If it is a relative path, treat it as relative to the repository root."
                ),
                tool_type=ToolType.READ_ONLY,
                model_class=ReadFileParams,
            ),

            create_tool_from_model(
                name="create_file",
                description=(
                    "Create a new file with the given content. The directory will be created if it does not already exist. Never use this tool to edit a file that already exists."
                ),
                tool_type=ToolType.WRITE,
                model_class=CreateFileParams,
            ),
            create_tool_from_model(
                name="apply_patch",
                description=APPLY_PATCH_TOOL_DESC,
                tool_type=ToolType.WRITE,
                model_class=ApplyPatchParams,
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
        if AgentToolRegistry._openai_tools is None:
            AgentToolRegistry._openai_tools = [
                t.to_openai_tool() for t in AgentToolRegistry.tools()
            ]
        return AgentToolRegistry._openai_tools


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
