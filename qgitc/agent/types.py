# -*- coding: utf-8 -*-

import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union


def _auto_uuid():
    # type: () -> str
    return str(_uuid.uuid4())


def _auto_timestamp():
    # type: () -> str
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TextBlock:
    text: str = ""


@dataclass
class ToolUseBlock:
    id: str = ""
    name: str = ""
    input: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResultBlock:
    tool_use_id: str = ""
    content: str = ""
    is_error: bool = False


@dataclass
class ThinkingBlock:
    thinking: str = ""


ContentBlock = Union[TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class UserMessage:
    content: List[ContentBlock] = field(default_factory=list)
    uuid: str = field(default_factory=_auto_uuid)
    timestamp: str = field(default_factory=_auto_timestamp)


@dataclass
class AssistantMessage:
    content: List[ContentBlock] = field(default_factory=list)
    uuid: str = field(default_factory=_auto_uuid)
    timestamp: str = field(default_factory=_auto_timestamp)
    model: Optional[str] = None
    stop_reason: Optional[str] = None
    usage: Optional[Usage] = None


@dataclass
class SystemMessage:
    subtype: str = ""
    content: str = ""
    uuid: str = field(default_factory=_auto_uuid)
    timestamp: str = field(default_factory=_auto_timestamp)
    compact_metadata: Optional[Dict[str, Any]] = None


Message = Union[UserMessage, AssistantMessage, SystemMessage]
