# -*- coding: utf-8 -*-

import json
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QCoreApplication

from qgitc.agent.tool_executor import TOOL_ABORTED_MESSAGE, TOOL_SKIPPED_MESSAGE
from qgitc.agent.types import (
    AssistantMessage,
    Message,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    Usage,
    UserMessage,
)


def messagesToHistoryDicts(messages):
    # type: (List[Message]) -> List[Dict[str, Any]]
    """Convert agent Message list to the history store dict format.

    Each dict has: role, content, reasoning, description, tool_calls, reasoning_data.
    A UserMessage containing multiple ToolResultBlocks is expanded into
    one dict per result (matching the old per-tool-call history format).
    """
    result = []  # type: List[Dict[str, Any]]
    toolId2Name = {}  # type: Dict[str, str]

    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append({
                "role": "system",
                "content": msg.content,
            })

        elif isinstance(msg, UserMessage):
            tool_results = [b for b in msg.content if isinstance(b, ToolResultBlock)]
            if tool_results:
                for tr in tool_results:
                    prefix = "✗" if tr.is_error else "✓"
                    toolName = toolId2Name.get(tr.tool_use_id, "Unknown")
                    desc_fmt = None
                    if tr.is_error:
                        if tr.content == TOOL_ABORTED_MESSAGE:
                            desc_fmt = "✗ `{}` cancelled"
                        elif tr.content == TOOL_SKIPPED_MESSAGE:
                            desc_fmt = "✗ `{}` skipped"
   
                    app = QCoreApplication.instance()
                    if app:
                        if not desc_fmt:
                            desc = app.translate("AiChatWidget", "{} `{}` output").format(prefix, toolName)
                        else:
                            desc = app.translate("AiChatWidget", desc_fmt).format(toolName)
                    else:
                        if not desc_fmt:
                            desc = "{} `{}` output".format(prefix, toolName)
                        else:
                            desc = desc_fmt.format(toolName)

                    result.append({
                        "role": "tool",
                        "content": tr.content,
                        "description": desc,
                        "tool_calls": {"tool_call_id": tr.tool_use_id},
                    })
            else:
                text = _extract_text(msg.content)
                result.append({
                    "role": "user",
                    "content": text,
                })

        elif isinstance(msg, AssistantMessage):
            text = _extract_text(msg.content)
            reasoning = _extract_reasoning(msg.content)
            reasoning_data = _extract_reasoning_data(msg.content)
            tool_calls = _extract_tool_calls(msg.content, toolId2Name)
            entry = {
                "role": "assistant",
                "content": text,
            }  # type: Dict[str, Any]
            if reasoning:
                entry["reasoning"] = reasoning
            if reasoning_data:
                entry["reasoning_data"] = reasoning_data
            if tool_calls:
                entry["tool_calls"] = tool_calls
            if msg.usage:
                entry["usage"] = {
                    "input_tokens": msg.usage.input_tokens,
                    "output_tokens": msg.usage.output_tokens,
                }
            result.append(entry)

    return result


def historyDictsToMessages(dicts):
    # type: (List[Dict[str, Any]]) -> List[Message]
    """Convert history store dicts back to agent Message list.

    Consecutive tool-role dicts are merged into a single UserMessage
    containing ToolResultBlocks.
    """
    messages = []  # type: List[Message]
    i = 0
    while i < len(dicts):
        d = dicts[i]
        role = d.get("role", "user")

        if role == "system":
            messages.append(SystemMessage(
                subtype="system",
                content=d.get("content") or "",
            ))
            i += 1

        elif role == "user":
            content = []
            text = d.get("content") or ""
            if text:
                content.append(TextBlock(text=text))
            messages.append(UserMessage(content=content))
            i += 1

        elif role == "assistant":
            content = []
            usage = None
            reasoning = d.get("reasoning")
            if reasoning:
                reasoning_data = d.get("reasoning_data")
                content.append(ThinkingBlock(thinking=reasoning, reasoning_data=reasoning_data))
            text = d.get("content") or ""
            if text:
                content.append(TextBlock(text=text))
            tool_calls = d.get("tool_calls")
            if isinstance(tool_calls, list):
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    func = tc.get("function") or {}
                    args_raw = func.get("arguments", "{}")
                    if isinstance(args_raw, str):
                        try:
                            args = json.loads(args_raw)
                        except (json.JSONDecodeError, ValueError):
                            args = {}
                    else:
                        args = args_raw if isinstance(args_raw, dict) else {}
                    content.append(ToolUseBlock(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        input=args,
                    ))
            usage = d.get("usage")
            if isinstance(usage, dict):
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                if input_tokens > 0 or output_tokens > 0:
                    usage = Usage(input_tokens=input_tokens, output_tokens=output_tokens)
            messages.append(AssistantMessage(content=content, usage=usage))
            i += 1

        elif role == "tool":
            tool_results = []
            while i < len(dicts) and dicts[i].get("role") == "tool":
                td = dicts[i]
                tc_data = td.get("tool_calls")
                if isinstance(tc_data, dict):
                    tc_id = tc_data.get("tool_call_id", "")
                elif isinstance(tc_data, str):
                    tc_id = tc_data
                else:
                    tc_id = ""
                tool_results.append(ToolResultBlock(
                    tool_use_id=tc_id,
                    content=td.get("content") or "",
                    is_error=False,
                ))
                i += 1
            messages.append(UserMessage(content=tool_results))

        else:
            i += 1

    return messages


def _extract_text(content):
    # type: (list) -> str
    parts = []
    for block in content:
        if isinstance(block, TextBlock):
            parts.append(block.text)
    return "".join(parts)


def _extract_reasoning(content):
    # type: (list) -> str
    parts = []
    for block in content:
        if isinstance(block, ThinkingBlock):
            parts.append(block.thinking)
    return "".join(parts) if parts else None


def _extract_reasoning_data(content):
    # type: (list) -> Optional[Dict[str, Any]]
    for block in content:
        if isinstance(block, ThinkingBlock) and block.reasoning_data:
            return block.reasoning_data
    return None


def _extract_tool_calls(content, toolId2Name):
    # type: (list, Dict[str, str]) -> list
    calls = []
    for block in content:
        if isinstance(block, ToolUseBlock):
            calls.append({
                "id": block.id,
                "type": "function",
                "function": {
                    "name": block.name,
                    "arguments": json.dumps(block.input, ensure_ascii=False),
                },
            })
            toolId2Name[block.id] = block.name
    return calls if calls else None
