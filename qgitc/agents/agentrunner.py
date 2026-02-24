# -*- coding: utf-8 -*-
"""
Agent Runner: Orchestrates agent execution.

Provides implementations for running agents:
- AgentRunner (base): abstract runner interface
- SequentialAgentRunner: runs agents sequentially with transfer support
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from qgitc.agentmachine import AgentToolMachine
from qgitc.agents.agentruntime import (
    AgentEvent,
    BaseAgent,
    InvocationContext,
    LlmAgent,
    SequentialAgent,
)
from qgitc.agents.llmflow import LlmFlow
from qgitc.common import logger


class AgentRunner(QObject):
    """Base class for agent execution orchestrators.
    
    Signals:
        eventEmitted: Emitted when an agent produces an event (AgentEvent)
        runFinished: Emitted when execution is complete
    """

    eventEmitted = Signal(object)  # AgentEvent
    runFinished = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        """Initialize the runner.
        
        Args:
            parent: Qt parent object.
        """
        super().__init__(parent)

    def run(
        self,
        rootAgent: BaseAgent,
        ctx: InvocationContext,
        userPrompt: str = "",
        sysPrompt: Optional[str] = None,
    ) -> None:
        """Run the root agent with the given context.
        
        Args:
            rootAgent: The agent to execute.
            ctx: Invocation context with session and config.
            userPrompt: Initial user prompt (can be empty for continuation).
            sysPrompt: Optional system prompt override.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__}.run() not implemented")


class SequentialAgentRunner(AgentRunner):
    """Runs agents sequentially with support for sub-agent transfers.
    
    Manages:
    - Sequential execution of agents
    - Transfer requests (via EventActions.transfer_to_agent)
    - State tracking in InvocationContext
    - Event accumulation and emission
    """

    def __init__(
        self,
        toolMachine: AgentToolMachine,
        modelLookupFn=None,
        flowFactory=None,
        parent: Optional[QObject] = None,
    ):
        """Initialize the sequential runner.
        
        Args:
            toolMachine: AgentToolMachine for tool execution.
            modelLookupFn: Optional callable(modelId) -> AiModelBase for model lookup.
            flowFactory: Optional callable() -> LlmFlow. If provided, used for testing.
                        Otherwise, LlmFlow is instantiated normally.
            parent: Qt parent object.
        """
        super().__init__(parent)
        self._toolMachine = toolMachine
        self._modelLookupFn = modelLookupFn
        self._flowFactory = flowFactory

        # Current execution state
        self._rootAgent: Optional[BaseAgent] = None
        self._ctx: Optional[InvocationContext] = None
        self._flow: Optional[LlmFlow] = None
        self._currentAgent: Optional[BaseAgent] = None

    def run(
        self,
        rootAgent: BaseAgent,
        ctx: InvocationContext,
        userPrompt: str = "",
        sysPrompt: Optional[str] = None,
    ) -> None:
        """Start running the agent.
        
        Args:
            rootAgent: The agent to execute.
            ctx: Invocation context.
            userPrompt: Initial user prompt.
            sysPrompt: Optional system prompt override.
        """
        self._rootAgent = rootAgent
        self._ctx = ctx
        self._currentAgent = rootAgent

        logger.info(f"SequentialAgentRunner: Starting agent: {rootAgent.name}")

        # Create LlmFlow for this execution
        if self._flowFactory:
            self._flow = self._flowFactory()
        else:
            self._flow = LlmFlow(
                toolMachine=self._toolMachine,
                modelLookupFn=self._modelLookupFn,
                parent=self,
            )
        self._flow.eventEmitted.connect(self._onEventEmitted)
        self._flow.flowFinished.connect(self._onFlowFinished)

        # Start with the root agent
        self._runCurrentAgent(userPrompt, sysPrompt)

    def _runCurrentAgent(self, userPrompt: str = "", sysPrompt: Optional[str] = None) -> None:
        """Run the current agent.
        
        Args:
            userPrompt: User prompt for this agent.
            sysPrompt: Optional system prompt override.
        """
        if not self._currentAgent or not self._ctx or not self._flow:
            logger.warning(
                "SequentialAgentRunner._runCurrentAgent() called with missing state")
            return

        # Update context agent
        self._ctx.agent = self._currentAgent

        # If agent is LlmAgent, run via LlmFlow
        if isinstance(self._currentAgent, LlmAgent):
            self._flow.run(self._ctx, userPrompt, sysPrompt)
        else:
            logger.warning(
                f"Unsupported agent type for sequential execution: {type(self._currentAgent)}")
            self._onFlowFinished()

    def _onEventEmitted(self, event: AgentEvent) -> None:
        """Handle event from flow."""
        if not event or not self._ctx:
            return

        # Check if event signals a transfer
        if event.actions.transfer_to_agent:
            logger.info(
                f"SequentialAgentRunner: Transfer requested to {event.actions.transfer_to_agent}")
            self._onTransferRequested(event)
        else:
            # Normal event: emit and accumulate
            self.eventEmitted.emit(event)

    def _onTransferRequested(self, event: AgentEvent) -> None:
        """Handle transfer request from event.
        
        Finds the target sub-agent and switches to it.
        
        Args:
            event: Event with transfer_to_agent action.
        """
        targetName = event.actions.transfer_to_agent
        if not targetName:
            return

        # First emit the transfer event
        self.eventEmitted.emit(event)

        # If current agent is SequentialAgent, try to resolve from it
        if isinstance(self._currentAgent, SequentialAgent):
            target = self._currentAgent.resolveSubAgent(targetName)
            if target:
                logger.info(
                    f"SequentialAgentRunner: Transferring to sub-agent: {targetName}")
                self._currentAgent = target
                # Continue with the new agent (no user prompt)
                self._runCurrentAgent(
                    "", event.actions.state_delta.get("sys_prompt"))
                return

        logger.warning(
            f"SequentialAgentRunner: Transfer target not found: {targetName}")

    def _onFlowFinished(self) -> None:
        """Handle flow completion."""
        logger.info(
            f"SequentialAgentRunner: Agent finished: {self._currentAgent.name}")
        self.runFinished.emit()
