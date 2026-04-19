# -*- coding: utf-8 -*-

import json
from dataclasses import dataclass
from typing import List

from qgitc.agent.provider import ContentDelta, ModelProvider
from qgitc.agent.types import (
    AssistantMessage,
    Message,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


def _message_text(msg):
    # type: (Message) -> str
    """Extract all text from a message's content blocks."""
    if isinstance(msg, SystemMessage):
        return msg.content

    parts = []  # type: List[str]
    for block in msg.content:
        if isinstance(block, TextBlock):
            parts.append(block.text)
        elif isinstance(block, ToolUseBlock):
            parts.append(block.name)
            parts.append(json.dumps(block.input))
        elif isinstance(block, ToolResultBlock):
            parts.append(block.content)
        elif isinstance(block, ThinkingBlock):
            parts.append(block.thinking)
    return "".join(parts)


def estimateTokens(messages):
    # type: (List[Message]) -> int
    """Heuristic token estimation: ~4 chars per token."""
    total = 0
    for msg in messages:
        total += len(_message_text(msg))
    return total // 4


def _build_summarization_prompt(messages):
    # type: (List[Message]) -> str
    """Build a prompt asking the LLM to summarize the conversation."""
    lines = [
        "Summarize the following conversation concisely. "
        "Preserve key decisions, code changes, file paths, and outcomes. "
        "Omit greetings and filler.",
        "",
    ]
    for msg in messages:
        if isinstance(msg, UserMessage):
            label = "User"
        elif isinstance(msg, AssistantMessage):
            label = "Assistant"
        else:
            label = "System"
        lines.append("{}: {}".format(label, _message_text(msg)))
    return "\n".join(lines)


@dataclass
class CompactionResult:
    boundary: SystemMessage
    summary: UserMessage
    pre_token_estimate: int
    post_token_estimate: int


class ConversationCompactor:
    BUFFER_TOKENS = 2000

    def __init__(self, provider, context_window, max_output_tokens):
        # type: (ModelProvider, int, int) -> None
        self._provider = provider
        self._context_window = context_window
        self._max_output_tokens = max_output_tokens

    def shouldCompact(self, messages):
        # type: (List[Message]) -> bool
        """Check whether the conversation should be compacted."""
        if not messages:
            return False
        threshold = (self._context_window
                     - self._max_output_tokens
                     - self.BUFFER_TOKENS)
        return estimateTokens(messages) > threshold

    def compact(self, messages):
        # type: (List[Message]) -> CompactionResult
        """Compact the conversation by summarizing it via the provider."""
        if not messages:
            raise ValueError("Cannot compact an empty message list")

        pre_tokens = estimateTokens(messages)

        prompt_text = _build_summarization_prompt(messages)
        prompt_msg = UserMessage(content=[TextBlock(text=prompt_text)])

        summary_parts = []  # type: List[str]
        for event in self._provider.stream([prompt_msg]):
            if isinstance(event, ContentDelta):
                summary_parts.append(event.text)

        summary_text = "".join(summary_parts)

        boundary = SystemMessage(
            subtype="compact_boundary",
            content="Conversation compacted.",
        )
        summary = UserMessage(
            content=[TextBlock(
                text="[Conversation summary]\n" + summary_text
            )],
        )

        post_tokens = estimateTokens([boundary, summary])

        return CompactionResult(
            boundary=boundary,
            summary=summary,
            pre_token_estimate=pre_tokens,
            post_token_estimate=post_tokens,
        )
