# -*- coding: utf-8 -*-
"""
Core agent runtime types and interfaces.

Provides the foundational data structures for the sequential agent framework:
- AgentEvent: atomic unit of an agent execution
- EventActions: metadata about agent state changes and transfers
- InvocationContext: per-invocation state tracking
- BaseAgent: interface for agent implementations
- LlmAgent: LLM-based agent
- SequentialAgent: sequential orchestrator for sub-agents
"""

from __future__ import annotations

import uuid
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# ============================================================================
# Event and Action Models
# ============================================================================


@dataclass
class EventActions:
    """Metadata about event actions and state changes.
    
    Attributes:
        state_delta: Optional state changes to persist in context.
        transfer_to_agent: If set, request transfer to named sub-agent.
        end_of_agent: If True, agent execution has completed.
    """
    state_delta: Dict[str, Any] = field(default_factory=dict)
    transfer_to_agent: Optional[str] = None
    end_of_agent: bool = False

    def setTransfer(self, agentName: str) -> None:
        """Request transfer to a sub-agent by name."""
        self.transfer_to_agent = agentName

    def setEndOfAgent(self, end: bool = True) -> None:
        """Mark the agent as finished."""
        self.end_of_agent = end


@dataclass
class AgentEvent:
    """Atomic event emitted by an agent during execution.
    
    Attributes:
        id: Unique event identifier.
        invocationId: Invocation this event belongs to.
        author: Who emitted this (e.g. 'user', 'assistant', 'tool').
        content: Event content (message text, tool output, etc.).
        actions: Metadata about state changes and transfers.
        branch: Optional branch identifier (for parallel agents).
        partial: If True, this is a streaming delta.
        timestamp: When the event occurred.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    invocationId: str = ""
    author: str = ""  # 'user', 'assistant', 'system', 'tool'
    content: Optional[Dict[str, Any]] = None
    actions: EventActions = field(default_factory=EventActions)
    branch: Optional[str] = None
    partial: bool = False
    timestamp: float = field(
        default_factory=lambda: datetime.now().timestamp())

    def __post_init__(self):
        if not self.invocationId:
            self.invocationId = str(uuid.uuid4())


# ============================================================================
# Invocation Context
# ============================================================================


@dataclass
class InvocationContext:
    """Per-invocation state container for agent execution.
    
    Holds session data, current agent, run configuration, and state tracking
    for resumability and sub-agent management.
    
    Attributes:
        invocationId: Unique identifier for this invocation.
        session: Associated session (e.g., chat history).
        agent: Current agent being executed.
        runConfig: User-provided run configuration.
        branch: Optional branch for parallel execution.
        end_invocation: Flag to signal end of invocation.
        agentStates: State storage per agent (agent_name -> state_dict).
        endOfAgents: Tracking which agents have finished.
        parentModelId: Model ID from parent agent (for fallback).
    """
    invocationId: str = field(default_factory=lambda: str(uuid.uuid4()))
    session: Optional[Any] = None
    agent: Optional[BaseAgent] = None
    runConfig: Dict[str, Any] = field(default_factory=dict)
    branch: Optional[str] = None
    end_invocation: bool = False
    agentStates: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    endOfAgents: Dict[str, bool] = field(default_factory=dict)
    parentModelId: Optional[str] = None

    def setAgentState(self, agentName: str, state: Dict[str, Any]) -> None:
        """Store state for an agent."""
        self.agentStates[agentName] = state

    def getAgentState(self, agentName: str) -> Dict[str, Any]:
        """Retrieve state for an agent, defaulting to empty dict."""
        return self.agentStates.get(agentName, {})

    def markAgentFinished(self, agentName: str) -> None:
        """Mark an agent as finished."""
        self.endOfAgents[agentName] = True

    def isAgentFinished(self, agentName: str) -> bool:
        """Check if an agent has finished."""
        return self.endOfAgents.get(agentName, False)

    def clone(self, newAgent: Optional[BaseAgent] = None) -> InvocationContext:
        """Create a child context (e.g., for sub-agent execution).
        
        Args:
            newAgent: Agent to assign to the new context.
            
        Returns:
            New InvocationContext with shared session and invocation ID.
        """
        return InvocationContext(
            invocationId=self.invocationId,
            session=self.session,
            agent=newAgent or self.agent,
            runConfig=self.runConfig,
            branch=self.branch,
            end_invocation=self.end_invocation,
            agentStates=self.agentStates,  # Shared reference
            endOfAgents=self.endOfAgents,  # Shared reference
            parentModelId=self.parentModelId,
        )


# ============================================================================
# Agent Interfaces and Implementations
# ============================================================================


class BaseAgent(ABC):
    """Abstract base class for all agents.
    
    Agents are responsible for producing events during execution.
    They can have sub-agents for orchestration.
    """

    def __init__(
        self,
        name: str,
        sub_agents: Optional[List[BaseAgent]] = None,
        parent_agent: Optional[BaseAgent] = None,
    ):
        """Initialize an agent.
        
        Args:
            name: Unique identifier for this agent.
            sub_agents: Optional list of child agents for orchestration.
            parent_agent: Reference to parent agent (None for root).
        """
        self.name = name
        self.sub_agents = sub_agents or []
        self.parent_agent = parent_agent

    def runSync(self, ctx: InvocationContext) -> List[AgentEvent]:
        """Run the agent synchronously (Qt-driven, not async).
        
        This is the main execution entry point. Subclasses override to provide
        actual behavior. Returns a list of events (accumulated during execution).
        
        Args:
            ctx: Invocation context with session, config, and state.
            
        Returns:
            List of AgentEvent objects emitted during execution.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.runSync() not implemented")

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


@dataclass
class LlmAgent(BaseAgent):
    """Agent that uses an LLM to generate responses.
    
    Can optionally override the model and system prompt.
    
    Attributes:
        name: Agent identifier.
        description: Optional description of what this agent specializes in.
        toolNames: Optional list of tool names to restrict tool use.
                   If None, all tools are available.
        modelId: Optional model override. If None, inherits from parent context.
        systemPrompt: Optional system prompt override.
        sub_agents: Optional list of sub-agents.
        parent_agent: Reference to parent agent.
    """
    name: str = ""
    description: Optional[str] = None
    toolNames: Optional[List[str]] = None
    modelId: Optional[str] = None
    systemPrompt: Optional[str] = None
    sub_agents: List[BaseAgent] = field(default_factory=list)
    parent_agent: Optional[BaseAgent] = None

    def __post_init__(self):
        # Validate initialization
        if not self.name:
            raise ValueError("LlmAgent.name is required")

    def runSync(self, ctx: InvocationContext) -> List[AgentEvent]:
        """Run LLM agent (implemented by LlmFlow in Step 2)."""
        raise NotImplementedError(
            "LlmAgent.runSync() is implemented by the LlmFlow wrapper"
        )


@dataclass
class SequentialAgent(BaseAgent):
    """Orchestrator that runs sub-agents in sequence.
    
    Maintains `currentSubAgent` in context state and delegates execution.
    
    Attributes:
        name: Agent identifier.
        sub_agents: List of agents to run in order.
        parent_agent: Reference to parent agent.
    """
    name: str = ""
    sub_agents: List[BaseAgent] = field(default_factory=list)
    parent_agent: Optional[BaseAgent] = None

    def __post_init__(self):
        if not self.name:
            raise ValueError("SequentialAgent.name is required")
        if not self.sub_agents:
            raise ValueError("SequentialAgent.sub_agents cannot be empty")

    def runSync(self, ctx: InvocationContext) -> List[AgentEvent]:
        """Run sub-agents in sequence (implemented by AgentRunner in Step 3)."""
        raise NotImplementedError(
            "SequentialAgent.runSync() is implemented by the AgentRunner"
        )

    def resolveSubAgent(self, name: str) -> Optional[BaseAgent]:
        """Lookup a sub-agent by name.
        
        Args:
            name: Name of the sub-agent to find.
            
        Returns:
            The matching sub-agent, or None if not found.
        """
        for agent in self.sub_agents:
            if agent.name == name:
                return agent
        return None


# ============================================================================
# Helper Functions
# ============================================================================


def resolveModelId(
    agent: Optional[BaseAgent],
    parentCtx: Optional[InvocationContext],
) -> Optional[str]:
    """Resolve the model ID to use for an agent.
    
    Priority:
    1. Agent's explicit modelId (if it's an LlmAgent with modelId set)
    2. Parent context's parentModelId (inherited from parent agent)
    3. None (use default)
    
    Args:
        agent: The agent to resolve a model for.
        parentCtx: The parent invocation context.
        
    Returns:
        The resolved model ID, or None to use default.
    """
    if agent is None:
        return parentCtx.parentModelId if parentCtx else None

    # Check if this is an LlmAgent with explicit modelId
    if isinstance(agent, LlmAgent) and agent.modelId:
        return agent.modelId

    # Fall back to parent context's model
    if parentCtx:
        return parentCtx.parentModelId

    return None
