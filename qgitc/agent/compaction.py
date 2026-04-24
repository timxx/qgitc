# -*- coding: utf-8 -*-

import json
import math
import re
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

# Tokens reserved for the summary output — caps the max_output_tokens
# contribution to the compaction threshold.
MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000

# Buffer subtracted from the effective window before the threshold check.
AUTOCOMPACT_BUFFER_TOKENS = 13_000


def roughEstimateTokens(messages):
    # type: (List[Message]) -> int
    """Estimate token count without an API call.

    Uses char/4 with a 4/3 padding factor per message
    """
    total = 0

    for msg in messages:
        msgChars = 0

        if isinstance(msg, SystemMessage):
            msgChars = len(msg.content)
        elif hasattr(msg, "content"):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    msgChars += len(block.text)
                elif isinstance(block, ToolUseBlock):
                    msgChars += len(block.name)
                    msgChars += len(json.dumps(block.input))
                elif isinstance(block, ToolResultBlock):
                    msgChars += len(block.content) if isinstance(block.content, str) else 0
                elif isinstance(block, ThinkingBlock):
                    msgChars += len(block.thinking)

        total += math.ceil(msgChars / 4 * (4 / 3))

    return total


_NO_TOOLS_PREAMBLE = (
    "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.\n\n"
    "- Do NOT use any tool calls.\n"
    "- You already have all the context you need in the conversation above.\n"
    "- Tool calls will be REJECTED and will waste your only turn \u2014 you will fail the task.\n"
    "- Your entire response must be plain text: an <analysis> block followed by a <summary> block.\n\n"
)

_BASE_COMPACT_PROMPT = """\
Your task is to create a detailed summary of the conversation so far, paying close attention \
to the user's explicit requests and your previous actions.

Before providing your final summary, wrap your analysis in <analysis> tags to organize your \
thoughts. In your analysis:
1. Chronologically analyze each message, identifying: the user's explicit requests and intents, \
your approach, key decisions, technical concepts, code patterns, specific details \
(file names, code snippets, function signatures, file edits), errors encountered and fixes, \
and user feedback.
2. Double-check for technical accuracy and completeness.

Your summary should include the following sections wrapped in <summary> tags:

1. Primary Request and Intent: Capture all of the user's explicit requests and intents in detail
2. Key Technical Concepts: List all important technical concepts, technologies, and frameworks discussed.
3. Files and Code Sections: Enumerate specific files and code sections examined, modified, or created. \
Include full code snippets where applicable.
4. Errors and fixes: List all errors encountered and how you fixed them.
5. Problem Solving: Document problems solved and any ongoing troubleshooting.
6. All user messages: List ALL user messages that are not tool results.
7. Pending Tasks: Outline any pending tasks explicitly requested.
8. Current Work: Describe precisely what was being worked on immediately before this summary.
9. Optional Next Step: List the next step directly in line with the most recent user request.

Example structure:
<analysis>
[Your analysis]
</analysis>

<summary>
1. Primary Request and Intent:
   [detail]
...
9. Optional Next Step:
   [step]
</summary>
"""

_NO_TOOLS_TRAILER = (
    "\n\nREMINDER: Do NOT call any tools. Respond with plain text only \u2014 "
    "an <analysis> block followed by a <summary> block. "
    "Tool calls will be rejected and you will fail the task."
)


def _getCompactPrompt():
    # type: () -> str
    """Return the structured compaction prompt (ports TS getCompactPrompt)."""
    return _NO_TOOLS_PREAMBLE + _BASE_COMPACT_PROMPT + _NO_TOOLS_TRAILER


def _formatCompactSummary(text):
    # type: (str) -> str
    """Strip <analysis> scratchpad and extract <summary> content.
    Returns text unchanged if no XML tags found.
    """
    # Strip analysis scratchpad
    text = re.sub(r"<analysis>[\s\S]*?</analysis>", "", text)

    # Extract summary section
    match = re.search(r"<summary>([\s\S]*?)</summary>", text)
    if match:
        content = match.group(1).strip()
        text = re.sub(
            r"<summary>[\s\S]*?</summary>",
            lambda m: "Summary:\n" + content,
            text,
        )

    # Clean up any orphaned opening/closing summary tags (e.g., truncated output)
    text = re.sub(r"</?summary>", "", text)

    # Collapse extra blank lines
    text = re.sub(r"\n\n+", "\n\n", text)

    return text.strip()


_MICROCOMPACT_CLEARED = "[Old tool result content cleared]"


def microcompactMessages(messages, thresholdChars=5000):
    # type: (List[Message], int) -> List[Message]
    """Truncate oversized tool results from old turns to reduce context size.

    Protects tool results from UserMessages at or after the second-to-last
    AssistantMessage index. Returns the same list object if no changes.
    Never mutates input.
    """
    if not messages:
        return messages

    assistantIndices = [
        i for i, m in enumerate(messages) if isinstance(m, AssistantMessage)
    ]
    if assistantIndices:
        cutoffIndex = assistantIndices[-1]
    else:
        cutoffIndex = 0

    result = []
    changed = False
    for i, msg in enumerate(messages):
        if not isinstance(msg, UserMessage) or i >= cutoffIndex:
            result.append(msg)
            continue

        newContent = []
        msgChanged = False
        for block in msg.content:
            if (isinstance(block, ToolResultBlock)
                    and isinstance(block.content, str)
                    and len(block.content) > thresholdChars):
                newContent.append(ToolResultBlock(
                    tool_use_id=block.tool_use_id,
                    content=_MICROCOMPACT_CLEARED,
                    is_error=block.is_error,
                ))
                msgChanged = True
                changed = True
            else:
                newContent.append(block)

        if msgChanged:
            result.append(UserMessage(content=newContent))
        else:
            result.append(msg)

    return result if changed else messages


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
        reserved = min(self._max_output_tokens, MAX_OUTPUT_TOKENS_FOR_SUMMARY)
        effectiveWindow = self._context_window - reserved
        threshold = effectiveWindow - AUTOCOMPACT_BUFFER_TOKENS
        return roughEstimateTokens(messages) > threshold

    def compact(self, messages):
        # type: (List[Message]) -> CompactionResult
        """Compact the conversation by summarizing it via the provider."""
        if not messages:
            raise ValueError("Cannot compact an empty message list")

        preTokens = roughEstimateTokens(messages)

        promptMsg = UserMessage(content=[TextBlock(text=_getCompactPrompt())])

        messageToSummarize = messages
        summaryParts = []  # type: List[str]
        for event in self._provider.stream(
                messageToSummarize + [promptMsg]):
            if isinstance(event, ContentDelta):
                summaryParts.append(event.text)

        summaryText = "".join(summaryParts)
        if not summaryText:
            raise RuntimeError("Compaction produced no summary")

        formatted = _formatCompactSummary(summaryText)
        framed = (
            "This session is being continued from a previous conversation "
            "that ran out of context. The summary below covers the earlier "
            "portion of the conversation.\n\n" + formatted
        )

        boundary = SystemMessage(
            subtype="compact_boundary",
            content="Conversation compacted.",
        )
        summary = UserMessage(content=[TextBlock(text=framed)])
        post_tokens = roughEstimateTokens([boundary, summary])

        return CompactionResult(
            boundary=boundary,
            summary=summary,
            pre_token_estimate=preTokens,
            post_token_estimate=post_tokens,
        )
