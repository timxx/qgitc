# -*- coding: utf-8 -*-

from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.tools.apply_patch import ApplyPatchTool
from qgitc.agent.tools.create_file import CreateFileTool
from qgitc.agent.tools.git_add import GitAddTool
from qgitc.agent.tools.git_blame import GitBlameTool
from qgitc.agent.tools.git_branch import GitBranchTool
from qgitc.agent.tools.git_checkout import GitCheckoutTool
from qgitc.agent.tools.git_cherry_pick import GitCherryPickTool
from qgitc.agent.tools.git_commit import GitCommitTool
from qgitc.agent.tools.git_current_branch import GitCurrentBranchTool
from qgitc.agent.tools.git_diff import GitDiffTool
from qgitc.agent.tools.git_diff_range import GitDiffRangeTool
from qgitc.agent.tools.git_diff_staged import GitDiffStagedTool
from qgitc.agent.tools.git_diff_unstaged import GitDiffUnstagedTool
from qgitc.agent.tools.git_log import GitLogTool
from qgitc.agent.tools.git_show import GitShowTool
from qgitc.agent.tools.git_show_file import GitShowFileTool
from qgitc.agent.tools.git_show_index_file import GitShowIndexFileTool
from qgitc.agent.tools.git_status import GitStatusTool
from qgitc.agent.tools.grep_search import GrepSearchTool
from qgitc.agent.tools.read_external_file import ReadExternalFileTool
from qgitc.agent.tools.read_file import ReadFileTool
from qgitc.agent.tools.run_command import RunCommandTool
from qgitc.agent.tools.skill import SkillTool


_BUILTIN_TOOLS = [
    GitStatusTool,
    GitLogTool,
    GitDiffTool,
    GitDiffRangeTool,
    GitDiffStagedTool,
    GitDiffUnstagedTool,
    GitShowTool,
    GitShowFileTool,
    GitShowIndexFileTool,
    GitBlameTool,
    GitCurrentBranchTool,
    GitBranchTool,
    GitCheckoutTool,
    GitCherryPickTool,
    GitCommitTool,
    GitAddTool,
    GrepSearchTool,
    ReadFileTool,
    ReadExternalFileTool,
    CreateFileTool,
    ApplyPatchTool,
    RunCommandTool,
    SkillTool,
]


def register_builtin_tools(registry):
    # type: (ToolRegistry) -> None
    """Register all built-in agent tools into the given registry."""
    for tool_cls in _BUILTIN_TOOLS:
        registry.register(tool_cls())
