# -*- coding: utf-8 -*-

from qgitc.agent.agent_loop import AgentLoop, QueryParams
from qgitc.agent.aimodel_adapter import AiModelBaseAdapter
from qgitc.agent.compaction import CompactionResult, ConversationCompactor
from qgitc.agent.message_convert import historyDictsToMessages, messagesToHistoryDicts
from qgitc.agent.permission_presets import createPermissionEngine
from qgitc.agent.permissions import (
    PermissionAllow,
    PermissionAsk,
    PermissionBehavior,
    PermissionDeny,
    PermissionEngine,
    PermissionRule,
    PermissionUpdate,
)
from qgitc.agent.provider import (
    ContentDelta,
    MessageComplete,
    ModelProvider,
    ReasoningDelta,
    StreamEvent,
    ToolCallDelta,
)
from qgitc.agent.skills.discovery import loadSkillRegistry
from qgitc.agent.skills.registry import SkillRegistry
from qgitc.agent.tool import Tool, ToolContext, ToolResult, ToolType, toolTypeFromTool
from qgitc.agent.tool_registration import registerBuiltinTools
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.types import (
    AssistantMessage,
    ContentBlock,
    Message,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    UserMessage,
)
from qgitc.agent.ui_tool import UiTool, UiToolDispatcher

__all__ = [
    "AgentLoop",
    "AiModelBaseAdapter",
    "AssistantMessage",
    "CompactionResult",
    "ContentBlock",
    "ContentDelta",
    "ConversationCompactor",
    "Message",
    "MessageComplete",
    "ModelProvider",
    "QueryParams",
    "PermissionAllow",
    "PermissionAsk",
    "PermissionBehavior",
    "PermissionDeny",
    "PermissionEngine",
    "PermissionRule",
    "PermissionUpdate",
    "ReasoningDelta",
    "SkillRegistry",
    "StreamEvent",
    "SystemMessage",
    "TextBlock",
    "ThinkingBlock",
    "Tool",
    "ToolCallDelta",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "ToolResultBlock",
    "ToolType",
    "ToolUseBlock",
    "UiTool",
    "UiToolDispatcher",
    "Usage",
    "UserMessage",
    "createPermissionEngine",
    "historyDictsToMessages",
    "messagesToHistoryDicts",
    "loadSkillRegistry",
    "registerBuiltinTools",
    "toolTypeFromTool",
]
