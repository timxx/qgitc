# -*- coding: utf-8 -*-
"""
LLM Flow: Encapsulates the model request/response/tool execution loop.

The flow handles:
1. Building model parameters from context (tools, system prompt, etc.)
2. Calling the LLM model
3. Parsing responses and detecting tool calls
4. Delegating to AgentToolMachine for tool execution
5. Handling continuation requests after tool results
6. Emitting events for each step
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtCore import QObject, Signal

from qgitc.agentmachine import AgentToolMachine
from qgitc.agents.agentruntime import (
    AgentEvent,
    InvocationContext,
    LlmAgent,
    resolveModelId,
)
from qgitc.common import logger
from qgitc.llm import AiChatMode, AiModelBase, AiParameters, AiResponse


class LlmFlow(QObject):
    """Encapsulates LLM model interaction with tool execution.
    
    Manages the full loop:
    - Build params from context (tools, system prompt, temperature, etc.)
    - Call model with queryAsync
    - On response: emit event and check for tool_calls
    - If tool_calls: delegate to AgentToolMachine
    - On tool completion: emit tool result events + continue with continue_only=True
    - Repeat until no tool_calls or stop reason
    
    Emits events for each step of the flow.
    
    Signals:
        eventEmitted: Emitted when an event is produced (AgentEvent)
        flowFinished: Emitted when flow is complete (no more tool_calls)
    """

    eventEmitted = Signal(object)  # AgentEvent
    flowFinished = Signal()

    def __init__(
        self,
        toolMachine: AgentToolMachine,
        modelLookupFn: Optional[Callable[[str], Optional[AiModelBase]]] = None,
        toolExecutor: Optional[QObject] = None,
        parent: Optional[QObject] = None,
    ):
        """Initialize the LLM flow.
        
        Args:
            toolMachine: AgentToolMachine for tool execution orchestration.
            modelLookupFn: Optional callable(modelId: str) -> Optional[AiModelBase].
                          If provided, used to resolve models by ID. Required to support
                          model overrides in sub-agents.
            toolExecutor: Optional tool executor with execute(toolCallId, toolName, params) method
                         and toolFinished signal. If None, tools won't be executed (test mode).
            parent: Qt parent object.
        """
        super().__init__(parent)
        self._toolMachine = toolMachine
        self._modelLookupFn = modelLookupFn
        self._toolExecutor = toolExecutor

        # Current model being used
        self._currentModel: Optional[AiModelBase] = None

        # Invocation context (holds state across the flow)
        self._ctx: Optional[InvocationContext] = None

        # Flow state: tracks if we're in a tool loop
        self._inToolLoop = False

        # Model response handlers
        self._connectModelSignals(None)

        # Tool machine signal handlers
        self._connectToolMachineSignals()

        # Tool executor signal handlers
        self._connectToolExecutorSignals()

    def run(self, ctx: InvocationContext, userPrompt: str = "", sysPrompt: Optional[str] = None) -> None:
        """Start the LLM flow.
        
        Builds params and initiates the model request. After this call, events
        are emitted via eventEmitted signal. When flow completes, flowFinished
        is emitted.
        
        Args:
            ctx: InvocationContext with session, agent, config.
            userPrompt: User message to send (can be empty for continuation).
            sysPrompt: Optional system prompt override.
        """
        self._ctx = ctx

        # Get the agent (should be an LlmAgent)
        if not isinstance(ctx.agent, LlmAgent):
            logger.warning(
                f"LlmFlow.run() called with non-LlmAgent: {ctx.agent}")
            return

        # Resolve which model to use
        modelId = resolveModelId(ctx.agent, ctx)

        # Lookup the actual model object
        model = self._lookupModel(modelId)
        if not model:
            logger.error(f"LlmFlow: Failed to lookup model: {modelId}")
            self._emitError("Model not available")
            self.flowFinished.emit()
            return

        self._currentModel = model
        self._connectModelSignals(model)

        # Build request parameters
        params = self._buildModelParams(ctx, userPrompt, sysPrompt)

        logger.debug(
            f"LlmFlow: Starting model request with params: chat_mode={params.chat_mode}, tools={bool(params.tools)}")

        # Send the request
        model.queryAsync(params)

    def continueAfterTools(self) -> None:
        """Continue the flow after tool execution.
        
        Called when AgentToolMachine emits agentContinuationReady.
        Sends a continue_only=True request to the model.
        """
        if not self._currentModel or not self._ctx:
            logger.warning(
                "LlmFlow.continueAfterTools() called without active model or context")
            return

        params = self._buildModelParams(
            self._ctx, "", None, continue_only=True)
        logger.debug("LlmFlow: Sending continue_only request to model")
        self._currentModel.queryAsync(params)

    # ========================================================================
    # Private: Model Parameter Building
    # ========================================================================

    def _buildModelParams(
        self,
        ctx: InvocationContext,
        userPrompt: str = "",
        sysPrompt: Optional[str] = None,
        continue_only: bool = False,
    ) -> AiParameters:
        """Build AI model parameters from context.
        
        Args:
            ctx: Invocation context.
            userPrompt: User message (empty for continuation).
            sysPrompt: Optional system prompt override.
            continue_only: If True, sends history as-is without new user message.
            
        Returns:
            AiParameters configured for the model request.
        """
        params = AiParameters()
        params.prompt = userPrompt
        params.sys_prompt = sysPrompt or self._getSystemPrompt(ctx)
        params.chat_mode = AiChatMode.Agent
        params.stream = True
        params.temperature = 0.1 if continue_only else 0.7
        params.reasoning = False  # Agent mode typically doesn't use reasoning
        params.continue_only = continue_only

        # Add tools if Agent has specified toolNames
        agent = ctx.agent
        if isinstance(agent, LlmAgent) and agent.modelId:
            # If agent has a model override, pass it through
            params.model = agent.modelId

        return params

    def _getSystemPrompt(self, ctx: InvocationContext) -> Optional[str]:
        """Get system prompt for this flow.
        
        Priority:
        1. Agent's explicit systemPrompt (if LlmAgent)
        2. None (caller should provide default)
        
        Args:
            ctx: Invocation context.
            
        Returns:
            System prompt string, or None.
        """
        agent = ctx.agent
        if isinstance(agent, LlmAgent) and agent.systemPrompt:
            return agent.systemPrompt
        return None

    # ========================================================================
    # Private: Model Signal Handlers
    # ========================================================================

    def _connectModelSignals(self, model: Optional[AiModelBase]) -> None:
        """Connect/disconnect from model signals."""
        # Disconnect from previous model if any
        if self._currentModel:
            try:
                self._currentModel.responseAvailable.disconnect(
                    self._onModelResponse)
                self._currentModel.finished.disconnect(self._onModelFinished)
            except:
                pass

        # Connect to new model if provided
        if model:
            model.responseAvailable.connect(self._onModelResponse)
            model.finished.connect(self._onModelFinished)

    def _onModelResponse(self, response: AiResponse) -> None:
        """Handle response from model."""
        if not self._ctx:
            return

        role = response.role

        # Emit assistant message event
        if response.message or response.reasoning:
            event = AgentEvent(
                invocationId=self._ctx.invocationId,
                author=role.name.lower(),
                content={
                    "message": response.message or "",
                    "reasoning": response.reasoning or "",
                },
            )
            self.eventEmitted.emit(event)

        # Check for tool calls
        if response.tool_calls:
            logger.debug(
                f"LlmFlow: Received {len(response.tool_calls)} tool calls")
            self._inToolLoop = True

            # Emit tool call event
            for tc in response.tool_calls:
                tc_id = tc.get("id", "")
                func_name = tc.get("function", {}).get("name", "unknown")
                event = AgentEvent(
                    invocationId=self._ctx.invocationId,
                    author="tool_request",
                    content={"tool_name": func_name, "tool_call_id": tc_id},
                )
                self.eventEmitted.emit(event)

            # Delegate to tool machine
            self._toolMachine.processToolCalls(response.tool_calls)

    def _onModelFinished(self) -> None:
        """Handle model request completion."""
        if not self._inToolLoop:
            logger.debug("LlmFlow: Model finished, no tools pending")
            self.flowFinished.emit()
        else:
            logger.debug(
                "LlmFlow: Model finished while in tool loop (waiting for tool machine)")

    # ========================================================================
    # Private: Tool Execution Handlers
    # ========================================================================

    def _connectToolMachineSignals(self) -> None:
        """Connect to tool machine signals."""
        self._toolMachine.toolExecutionRequested.connect(
            self._onToolExecutionRequested)
        self._toolMachine.agentContinuationReady.connect(
            self.continueAfterTools)

    def _connectToolExecutorSignals(self) -> None:
        """Connect to tool executor signals if available."""
        if self._toolExecutor and hasattr(self._toolExecutor, 'toolFinished'):
            self._toolExecutor.toolFinished.connect(self._onToolFinished)

    def _onToolExecutionRequested(self, toolCallId: str, toolName: str, params: Dict) -> None:
        """Handle tool execution request from tool machine.
        
        Args:
            toolCallId: Unique identifier for this tool call.
            toolName: Name of the tool to execute.
            params: Tool parameters dictionary.
        """
        logger.debug(
            f"LlmFlow: Tool execution requested: {toolName} (callId={toolCallId})")

        if not self._toolExecutor:
            logger.warning(
                "LlmFlow: No tool executor configured, cannot execute tools")
            # Create a failure result
            from qgitc.agenttools import AgentToolResult
            result = AgentToolResult(
                toolCallId=toolCallId,
                toolName=toolName,
                ok=False,
                output="Tool executor not configured",
            )
            self._onToolFinished(result)
            return

        # Execute the tool via executor
        if hasattr(self._toolExecutor, 'execute'):
            self._toolExecutor.execute(toolCallId, toolName, params)
        else:
            logger.error(f"LlmFlow: Tool executor missing execute() method")

    def _onToolFinished(self, result) -> None:
        """Handle tool execution completion.
        
        Args:
            result: AgentToolResult with toolCallId, ok, output, toolName.
        """
        if not self._ctx:
            return

        toolName = result.toolName
        toolCallId = result.toolCallId
        ok = result.ok
        output = result.output or ""

        logger.debug(
            f"LlmFlow: Tool finished: {toolName} (callId={toolCallId}, ok={ok})")

        # Emit tool result event
        prefix = "✓" if ok else "✗"
        event = AgentEvent(
            invocationId=self._ctx.invocationId,
            author="tool",
            content={
                "tool_name": toolName,
                "tool_call_id": toolCallId,
                "output": output,
                "ok": ok,
                "description": f"{prefix} `{toolName}` output",
            },
        )
        self.eventEmitted.emit(event)

        # Notify tool machine of completion
        self._toolMachine.onToolFinished(result)

    # ========================================================================
    # Private: Utilities
    # ========================================================================

    def _lookupModel(self, modelId: Optional[str]) -> Optional[AiModelBase]:
        """Lookup a model by ID.
        
        Uses the provided modelLookupFn if available, otherwise returns None.
        
        Args:
            modelId: Model identifier (e.g. 'gpt-4', 'claude-3-sonnet').
            
        Returns:
            Model object, or None if not found.
        """
        if not modelId or not self._modelLookupFn:
            return None
        return self._modelLookupFn(modelId)

    def _emitError(self, message: str) -> None:
        """Emit an error event."""
        if not self._ctx:
            return
        event = AgentEvent(
            invocationId=self._ctx.invocationId,
            author="system",
            content={"error": message},
        )
        self.eventEmitted.emit(event)
