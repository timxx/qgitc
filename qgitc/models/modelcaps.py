# -*- coding: utf-8 -*-

from qgitc.llm import AiModelCapabilities

KnownModelCapabilities = {
    "glm-4.5": AiModelCapabilities(
        context_window=131072, max_output_tokens=98304, tool_calls=True
    ),
    "glm-4.6": AiModelCapabilities(
        context_window=204800, max_output_tokens=131072, tool_calls=True
    ),
    "glm-4.7": AiModelCapabilities(
        context_window=204800, max_output_tokens=131072, tool_calls=True
    ),
    "glm-4.7-flash": AiModelCapabilities(
        context_window=202752, max_output_tokens=131072, tool_calls=True
    ),
    "glm-5": AiModelCapabilities(
        context_window=202752, max_output_tokens=202752, tool_calls=True
    ),
    "glm-5.1": AiModelCapabilities(
        context_window=204800, max_output_tokens=131072, tool_calls=True
    ),
    "glm-5v-turbo": AiModelCapabilities(
        context_window=200000, max_output_tokens=131072, tool_calls=True
    ),
    "gemma4:31b": AiModelCapabilities(
        context_window=262144, max_output_tokens=8192, tool_calls=True
    ),
    "gemma4:26b": AiModelCapabilities(
        context_window=262144, max_output_tokens=262144, tool_calls=True
    ),
    "qwen3.5:27b": AiModelCapabilities(
        context_window=262144, max_output_tokens=65536, tool_calls=True
    ),
    "qwen3.5:9b": AiModelCapabilities(
        context_window=262144, max_output_tokens=65536, tool_calls=True
    ),
    "qwen3.5-flash": AiModelCapabilities(
        context_window=1000000, max_output_tokens=64000, tool_calls=True
    ),
    "qwen3.5-plus": AiModelCapabilities(
        context_window=1000000, max_output_tokens=64000, tool_calls=True
    ),
    "qwen3.6-plus": AiModelCapabilities(
        context_window=1000000, max_output_tokens=65536, tool_calls=True
    ),
    "deepseek-chat": AiModelCapabilities(
        context_window=163840, max_output_tokens=163840, tool_calls=True
    ),
    "deepseek-reasoner": AiModelCapabilities(
        context_window=128000, max_output_tokens=64000, tool_calls=True
    ),
    "deepseek-v4-flash": AiModelCapabilities(
        context_window=1000000, max_output_tokens=384000, tool_calls=True
    ),
    "deepseek-v4-pro": AiModelCapabilities(
        context_window=1000000, max_output_tokens=384000, tool_calls=True
    ),
    "kimi-k2-0905": AiModelCapabilities(
        context_window=262144, max_output_tokens=16384, tool_calls=True
    ),
    "kimi-k2.5": AiModelCapabilities(
        context_window=262144, max_output_tokens=262144, tool_calls=True
    ),
    "kimi-k2-thinking": AiModelCapabilities(
        context_window=262144, max_output_tokens=262144, tool_calls=True
    ),
    "kimi-k2-thinking-turbo": AiModelCapabilities(
        context_window=262144, max_output_tokens=262144, tool_calls=True
    ),
    "llama3.1": AiModelCapabilities(
        context_window=131072, max_output_tokens=131072, tool_calls=True
    ),
    "claude-opus-4.6": AiModelCapabilities(
        context_window=1000000, max_output_tokens=128000, tool_calls=True
    ),
    "claude-sonnet-4.6": AiModelCapabilities(
        context_window=1000000, max_output_tokens=128000, tool_calls=True
    ),
    "claude-opus-4-7": AiModelCapabilities(
        context_window=1000000, max_output_tokens=128000, tool_calls=True
    ),
    "gemini-2.5-flash-lite": AiModelCapabilities(
        context_window=1048576, max_output_tokens=65536, tool_calls=True
    ),
    "gemini-3.1-flash-image-preview": AiModelCapabilities(
        context_window=131072, max_output_tokens=32768, tool_calls=True
    ),
    "gemini-2.5-flash-lite": AiModelCapabilities(
        context_window=1048576, max_output_tokens=65536, tool_calls=True
    ),
    "gemini-3-flash-preview": AiModelCapabilities(
        context_window=1048576, max_output_tokens=65536, tool_calls=True
    ),
    "gemini-3-pro-image-preview": AiModelCapabilities(
        context_window=1048756, max_output_tokens=65536, tool_calls=True
    ),
    "gemini-3-pro-preview": AiModelCapabilities(
        context_window=1000000, max_output_tokens=64000, tool_calls=True
    ),
    "gpt-4o": AiModelCapabilities(
        context_window=128000, max_output_tokens=16384, tool_calls=True
    ),
    "gpt-4o-mini": AiModelCapabilities(
        context_window=128000, max_output_tokens=16384, tool_calls=True
    ),
    "gpt-5.2": AiModelCapabilities(
        context_window=400000, max_output_tokens=128000, tool_calls=True
    ),
    "gpt-5.4": AiModelCapabilities(
        context_window=400000, max_output_tokens=128000, tool_calls=True
    ),
    "gpt-5.4-mini": AiModelCapabilities(
        context_window=400000, max_output_tokens=128000, tool_calls=True
    ),
    "gpt-5-mini": AiModelCapabilities(
        context_window=400000, max_output_tokens=128000, tool_calls=True
    ),
    "gpt-5.5": AiModelCapabilities(
        context_window=1050000, max_output_tokens=130000, tool_calls=True
    ),
    "doubao-seed-1-6": AiModelCapabilities(
        context_window=256000, max_output_tokens=16384, tool_calls=True
    ),
    "doubao-seed-1-8": AiModelCapabilities(
        context_window=128000, max_output_tokens=8192, tool_calls=True
    ),
    "doubao-seed-2-0": AiModelCapabilities(
        context_window=256000, max_output_tokens=128000, tool_calls=True
    ),
    "mimo-v2-omni": AiModelCapabilities(
        context_window=262144, max_output_tokens=65536, tool_calls=True
    ),
    "mimo-v2-pro": AiModelCapabilities(
        context_window=1048576, max_output_tokens=65536, tool_calls=True
    )
}
