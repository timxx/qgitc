# -*- coding: utf-8 -*-

from qgitc.agent.agent_loop import AgentLoop
from qgitc.agent.aimodel_adapter import AiModelBaseAdapter
from qgitc.agent.compaction import (
    CompactionResult,
    ConversationCompactor,
    estimate_tokens,
)
from qgitc.agent.message_convert import (
    history_dicts_to_messages,
    messages_to_history_dicts,
)
from qgitc.agent.permission_presets import create_permission_engine
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
from qgitc.agent.tool import Tool, ToolContext, ToolResult, ToolType, tool_type_from_tool
from qgitc.agent.tool_registry import ToolRegistry
from qgitc.agent.tool_registration import register_builtin_tools
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
    "PermissionAllow",
    "PermissionAsk",
    "PermissionBehavior",
    "PermissionDeny",
    "PermissionEngine",
    "PermissionRule",
    "PermissionUpdate",
    "ReasoningDelta",
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
    "create_permission_engine",
    "estimate_tokens",
    "history_dicts_to_messages",
    "messages_to_history_dicts",
    "register_builtin_tools",
    "tool_type_from_tool",
]
