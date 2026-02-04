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
    toolType: int
    parameters: Dict[str, Any]
    modelClass: Optional[Type[BaseModel]] = None

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
    repoDir: Optional[str] = Field(
        None, description="Optional repo directory. Defaults to current repo.")
    untracked: bool = Field(
        True, description="Include untracked files (default true).")


class GitLogParams(BaseModel):
    """Parameters for git_log tool."""
    repoDir: Optional[str] = None
    nth: Optional[int] = Field(
        None, ge=1, le=10000, description="Fetch only the Nth commit from HEAD (1-based). If set, returns exactly one commit.")
    maxCount: Optional[int] = Field(
        20, ge=1, le=200, description="Number of commits to show (default 20).")
    since: Optional[str] = Field(
        None, description="Show commits more recent than a specific date (e.g., '2 weeks ago', '2023-01-01').")
    until: Optional[str] = Field(
        None, description="Show commits older than a specific date.")


class GitDiffParams(BaseModel):
    """Parameters for git_diff tool."""
    repoDir: Optional[str] = None
    rev: str = Field(...,
                     description="The commit SHA or revision range to diff")
    files: Optional[List[str]] = Field(
        None, description="If provided, limits the diff to these files.")


class GitDiffUnstagedParams(BaseModel):
    """Parameters for git_diff_unstaged tool."""
    repoDir: Optional[str] = None
    nameOnly: bool = Field(
        False, description="If true, shows only names of changed files.")
    files: Optional[List[str]] = Field(
        None, description="If provided, limits the diff to these files.")


class GitDiffStagedParams(BaseModel):
    """Parameters for git_diff_staged tool."""
    repoDir: Optional[str] = None
    nameOnly: bool = Field(
        False, description="If true, shows only names of changed files.")
    files: Optional[List[str]] = Field(
        None, description="If provided, limits the diff to these files.")


class GitShowParams(BaseModel):
    """Parameters for git_show tool."""
    repoDir: Optional[str] = None
    rev: str = Field(...,
                     description="Commit-ish to show (sha, HEAD, tag, etc.).")


class GitShowFileParams(BaseModel):
    """Parameters for git_show_file tool."""
    repoDir: Optional[str] = None
    rev: str = Field(...,
                     description="Commit-ish to read from (sha, HEAD, tag, etc.).")
    path: str = Field(...,
                      description="File path within the repository at that revision.")
    startLine: Optional[int] = Field(
        None, ge=1, description="Starting line number (1-based). If not provided, starts from the beginning.")
    endLine: Optional[int] = Field(
        None, ge=1, description="Ending line number (1-based). If not provided, reads until the end.")


class GitShowIndexFileParams(BaseModel):
    """Parameters for git_show_index_file tool."""
    repoDir: Optional[str] = None
    path: str = Field(..., description="File path within the repository to read from the index (staged).")
    startLine: Optional[int] = Field(
        None, ge=1, description="Starting line number (1-based). If not provided, starts from the beginning.")
    endLine: Optional[int] = Field(
        None, ge=1, description="Ending line number (1-based). If not provided, reads until the end.")


class GitCurrentBranchParams(BaseModel):
    """Parameters for git_current_branch tool."""
    repoDir: Optional[str] = None


class GitBranchParams(BaseModel):
    """Parameters for git_branch tool."""
    repoDir: Optional[str] = None
    all: bool = Field(False, description="If true, include remotes (`-a`).")


class GitCheckoutParams(BaseModel):
    """Parameters for git_checkout tool."""
    repoDir: Optional[str] = None
    branch: str = Field(..., description="Branch name to checkout")


class GitCherryPickParams(BaseModel):
    """Parameters for git_cherry_pick tool."""
    repoDir: Optional[str] = None
    commits: List[str] = Field(..., min_length=1,
                               description="List of commit SHAs to cherry-pick")


class GitCommitParams(BaseModel):
    """Parameters for git_commit tool."""
    repoDir: Optional[str] = None
    message: str = Field(..., description="Commit message")


class GitAddParams(BaseModel):
    """Parameters for git_add tool."""
    repoDir: Optional[str] = None
    files: List[str] = Field(..., min_length=1,
                             description="List of file paths to stage.")


class RunCommandParams(BaseModel):
    """Parameters for run_command tool."""
    command: str = Field(
        ..., description="The command to execute. This should be a complete shell command.")
    workingDir: Optional[str] = Field(
        None, description="Optional working directory. If not specified, uses the repository directory.")
    timeout: int = Field(
        60, ge=1, le=300, description="Maximum execution time in seconds (default 60, max 300).")
    explanation: Optional[str] = Field(
        ..., description="A short explanation of why this command is being run.")


class ReadFileParams(BaseModel):
    """Parameters for read_file tool."""
    filePath: str = Field(..., description="Path to the file to read.")
    startLine: Optional[int] = Field(
        None, ge=1, description="Starting line number (1-based). If not provided, starts from the beginning.")
    endLine: Optional[int] = Field(
        None, ge=1, description="Ending line number (1-based). If not provided, reads until the end.")


class ReadNonRepoFileParams(BaseModel):
    """Parameters for read_nonrepo_file tool."""
    filePath: str = Field(
        ...,
        description="Absolute path to a file to read (outside the repository).")
    startLine: Optional[int] = Field(
        None, ge=1, description="Starting line number (1-based). If not provided, starts from the beginning.")
    endLine: Optional[int] = Field(
        None, ge=1, description="Ending line number (1-based). If not provided, reads until the end.")
    explanation: str = Field(
        ...,
        description=(
            "Why you need to read this file. The user will see this in the approval UI. "
            "Prefer a clear, minimal explanation."
        ),
    )


class CreateFileParams(BaseModel):
    """Parameters for create_file tool."""
    filePath: str = Field(...,
                          description="The absolute path to the file to create.")
    content: str = Field(..., description="The content to write to the file.")


class GrepSearchParams(BaseModel):
    """Parameters for grep_search tool."""
    repoDir: Optional[str] = Field(
        None, description="Optional repo directory. Defaults to current repo.")
    query: str = Field(
        ..., description="The pattern or text to search for. Search is case-insensitive.")
    isRegexp: bool = Field(
        ..., description="Whether query should be treated as a regular expression.")
    includeIgnoredFiles: bool = Field(
        False,
        description=(
            "If true, also search files ignored by .gitignore and other Git ignore rules. "
            "Warning: using this may cause the search to be slower. Only set it when you want to search in ignored folders like node_modules or build outputs."
        ),
    )
    includePattern: Optional[str] = Field(
        None,
        description=(
            "Optional glob pattern to filter files to search (e.g. 'qgitc/**/*.py')."
        ),
    )
    maxResults: Optional[int] = Field(
        30, ge=1,
        description=(
            "Maximum number of matches to return (default 30)."
            "By default, only some matches are returned. If you use this and don't see what you're looking for, you can try again with a more specific query or a larger maxResults."
        ),
    )


class ApplyPatchParams(BaseModel):
    """Parameters for apply_patch tool (V4A diff format)."""
    input: str = Field(...,
                       description="The edit patch to apply (V4A format).")
    explanation: str = Field(
        ..., description="A short description of what the patch is aiming to achieve.")


# ==================== Helper Function ====================

def createToolFromModel(
    name: str,
    description: str,
    toolType: int,
    modeClass: Type[BaseModel]
) -> AgentTool:
    """Create an AgentTool from a BaseModel."""
    schema = modeClass.model_json_schema()
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
        toolType=toolType,
        parameters=parameters,
        modelClass=modeClass,
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
            createToolFromModel(
                name="git_status",
                description=(
                    "Shows the working tree status. "
                    "If there are no changes, the result explicitly includes 'working tree clean (no changes)'."
                ),
                toolType=ToolType.READ_ONLY,
                modeClass=GitStatusParams,
            ),
            createToolFromModel(
                name="git_log",
                description="Show commit logs. Can filter by date range and limit number of commits.",
                toolType=ToolType.READ_ONLY,
                modeClass=GitLogParams,
            ),
            createToolFromModel(
                name="git_diff",
                description="Get the diff of a specific commit",
                toolType=ToolType.READ_ONLY,
                modeClass=GitDiffParams,
            ),
            createToolFromModel(
                name="git_diff_unstaged",
                description="Shows changes in the working directory that are not yet staged",
                toolType=ToolType.READ_ONLY,
                modeClass=GitDiffUnstagedParams,
            ),
            createToolFromModel(
                name="git_diff_staged",
                description="Shows changes that are staged for commit",
                toolType=ToolType.READ_ONLY,
                modeClass=GitDiffStagedParams,
            ),
            createToolFromModel(
                name="git_show",
                description="Show the contents of a commit",
                toolType=ToolType.READ_ONLY,
                modeClass=GitShowParams,
            ),
            createToolFromModel(
                name="git_show_file",
                description=(
                    "Show the contents of a file at a specific revision (e.g. 'HEAD:path/to/file').\n"
                    "Useful for code review when the working tree may differ from the commit being reviewed.\n"
                    "Supports optional line range selection."
                ),
                toolType=ToolType.READ_ONLY,
                modeClass=GitShowFileParams,
            ),
            createToolFromModel(
                name="git_show_index_file",
                description=(
                    "Show the contents of a staged (index) file (equivalent to 'git show :path').\n"
                    "Useful when reviewing staged changes where the working tree may differ.\n"
                    "Supports optional line range selection."
                ),
                toolType=ToolType.READ_ONLY,
                modeClass=GitShowIndexFileParams,
            ),
            createToolFromModel(
                name="git_current_branch",
                description=(
                    "Get the current branch name. "
                    "If in detached HEAD state, returns a detached HEAD message."
                ),
                toolType=ToolType.READ_ONLY,
                modeClass=GitCurrentBranchParams,
            ),
            createToolFromModel(
                name="git_branch",
                description="List Git branches",
                toolType=ToolType.READ_ONLY,
                modeClass=GitBranchParams,
            ),
            createToolFromModel(
                name="git_checkout",
                description="Switch branches",
                toolType=ToolType.WRITE,
                modeClass=GitCheckoutParams,
            ),
            createToolFromModel(
                name="git_cherry_pick",
                description="Cherry-pick one or more commits onto the current branch.",
                toolType=ToolType.WRITE,
                modeClass=GitCherryPickParams,
            ),
            createToolFromModel(
                name="git_commit",
                description="Record changes to the repository",
                toolType=ToolType.WRITE,
                modeClass=GitCommitParams,
            ),
            createToolFromModel(
                name="git_add",
                description="Add file contents to the index",
                toolType=ToolType.WRITE,
                modeClass=GitAddParams,
            ),
            createToolFromModel(
                name="run_command",
                description=(
                    "Execute an arbitrary command in the repository directory or a specified directory.\n"
                    "This tool allows running any shell command when needed. Use with caution as "
                    "it can execute potentially destructive commands."
                ),
                toolType=ToolType.DANGEROUS,
                modeClass=RunCommandParams,
            ),
            createToolFromModel(
                name="read_file",
                description=(
                    "Read the contents of a file, optionally specifying line ranges.\n"
                    "If it is a relative path, treat it as relative to the repository root."
                ),
                toolType=ToolType.READ_ONLY,
                modeClass=ReadFileParams,
            ),

            createToolFromModel(
                name="read_nonrepo_file",
                description=(
                    "Read a file by absolute path that is NOT inside the current repository.\n"
                    "Use this only when you explicitly need a file outside the repo (e.g. system config), "
                    "and only after the user approves the action.\n"
                    "Do NOT use this tool for files inside the repository; use read_file instead."
                ),
                toolType=ToolType.DANGEROUS,
                modeClass=ReadNonRepoFileParams,
            ),

            createToolFromModel(
                name="grep_search",
                description=(
                    "Search for text across files in the current repository.\n"
                    "Use this tool when you want to search with an exact string or regex. "
                    "If you are not sure what words will appear in the workspace, prefer using regex patterns with alternation (|) or character classes to search for multiple potential words at once instead of making separate searches. "
                    "For example, use 'function|method|procedure' to look for all of those words at once."
                ),
                toolType=ToolType.READ_ONLY,
                modeClass=GrepSearchParams,
            ),

            createToolFromModel(
                name="create_file",
                description=(
                    "Create a new file with the given content. The directory will be created if it does not already exist. Never use this tool to edit a file that already exists."
                ),
                toolType=ToolType.WRITE,
                modeClass=CreateFileParams,
            ),
            createToolFromModel(
                name="apply_patch",
                description=APPLY_PATCH_TOOL_DESC,
                toolType=ToolType.WRITE,
                modeClass=ApplyPatchParams,
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
