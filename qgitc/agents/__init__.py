# -*- coding: utf-8 -*-
"""
Agent framework for multi-agent orchestration with Qt event loop.

This package provides the core runtime for sequential agent execution,
supporting optional model overrides and sub-agent transfers.
"""

from qgitc.agents.agentruntime import (
    AgentEvent,
    BaseAgent,
    EventActions,
    InvocationContext,
    LlmAgent,
    SequentialAgent,
    resolveModelId,
)

__all__ = [
    "AgentEvent",
    "EventActions",
    "InvocationContext",
    "BaseAgent",
    "LlmAgent",
    "SequentialAgent",
    "resolveModelId",
]
