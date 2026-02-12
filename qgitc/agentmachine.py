# -*- coding: utf-8 -*-

"""
Agent Tool Machine: Orchestrates tool execution with strategies and parallel support.

This module provides a standalone, testable tool execution orchestrator that:
- Supports pluggable execution strategies (auto-run vs. confirmation)
- Handles parallel tool execution (up to N concurrent tools)
- Manages tool grouping and batch completion
- Emits signals for UI integration (no direct UI dependencies)
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from PySide6.QtCore import QObject, QTimer, Signal

from qgitc.agenttools import AgentTool, AgentToolRegistry, AgentToolResult, ToolType
from qgitc.common import logger

# ============================================================================
# Helper Functions
# ============================================================================


def parseToolArguments(arguments: Optional[str]) -> Dict:
    """Parse JSON tool arguments, returning empty dict if invalid."""
    if not arguments:
        return {}
    try:
        parsed = json.loads(arguments)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Failed to parse tool arguments: {arguments}")
        return {}


# ============================================================================
# Strategy Pattern
# ============================================================================

class ToolExecutionStrategy(ABC):
    """Abstract strategy for determining tool execution behavior.
    
    Strategies decide whether a tool should auto-run or require user approval
    based on tool type, name, and parameters.
    """

    @abstractmethod
    def shouldAutoRun(self, toolName: str, toolType: int, params: Dict) -> bool:
        """Determine if a tool should execute automatically.
        
        Args:
            toolName: Name of the tool to execute
            toolType: ToolType value (READ_ONLY, WRITE, DANGEROUS)
            params: Tool parameters dict
            
        Returns:
            True to auto-run, False to require user confirmation
        """
        pass


class DefaultStrategy(ToolExecutionStrategy):
    """Default strategy: Auto-run READ_ONLY tools only.
    
    This is the safest default behavior - only tools that cannot modify
    state are executed automatically. All write/dangerous operations
    require explicit user approval.
    """

    def shouldAutoRun(self, toolName: str, toolType: int, params: Dict) -> bool:
        return toolType == ToolType.READ_ONLY


class AggressiveStrategy(ToolExecutionStrategy):
    """Aggressive strategy: Auto-run READ_ONLY and WRITE tools.
    
    This strategy auto-runs most tools except those marked as DANGEROUS.
    Useful for power users who trust the AI to make modifications.
    
    Note: DANGEROUS tools still require confirmation.
    """

    def shouldAutoRun(self, toolName: str, toolType: int, params: Dict) -> bool:
        return toolType != ToolType.DANGEROUS


class SafeStrategy(ToolExecutionStrategy):
    """Safe strategy: Require approval for ALL tools.
    
    This strategy never auto-runs any tool, requiring explicit user
    confirmation for every operation (including reads).
    Useful for learning or auditing AI behavior.
    """

    def shouldAutoRun(self, toolName: str, toolType: int, params: Dict) -> bool:
        return False


class CustomStrategy(ToolExecutionStrategy):
    """Custom strategy with configurable tool whitelists.
    
    Allows fine-grained control over which tools auto-run based on
    exact tool names or patterns.
    """

    def __init__(self, autoRunTools: Optional[List[str]] = None):
        """Initialize custom strategy.
        
        Args:
            autoRunTools: List of tool names that should auto-run.
                         If None, defaults to empty (same as SafeStrategy).
        """
        self._autoRunTools = set(autoRunTools or [])

    def shouldAutoRun(self, toolName: str, toolType: int, params: Dict) -> bool:
        return toolName in self._autoRunTools

    def addAutoRunTool(self, toolName: str) -> None:
        """Add a tool to the auto-run whitelist."""
        self._autoRunTools.add(toolName)

    def removeAutoRunTool(self, toolName: str) -> None:
        """Remove a tool from the auto-run whitelist."""
        self._autoRunTools.discard(toolName)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ToolRequest:
    """Internal representation of a tool execution request.
    
    Tracks all metadata needed to execute a tool and correlate results.
    """
    toolName: str
    params: Dict
    toolCallId: Optional[str]
    groupId: int
    source: str  # 'auto' | 'approved'
    toolType: int
    description: str


# ============================================================================
# Agent Tool Machine
# ============================================================================

class AgentToolMachine(QObject):
    """Orchestrates tool execution with parallel support and execution strategies.
    
    This class is the core tool execution orchestrator, managing:
    - Tool execution decisions (via strategy pattern)
    - Parallel execution (up to maxConcurrent tools at once)
    - Tool grouping and batch completion tracking
    - Out-of-order completion handling
    - Signal emission for UI integration
    
    The machine operates as a state machine with these states:
    - Idle: No tools pending or executing
    - Queued: Tools waiting to execute (queue not empty)
    - Executing: Tools currently running (inProgress not empty)
    - Awaiting: Tools finished, waiting for agent continuation
    
    Signals:
        toolExecutionRequested: Emitted when a tool should be executed
        userConfirmationNeeded: Emitted when user approval is required
        agentContinuationReady: Emitted when all tools done and agent can continue
    """

    # Signal: Request tool execution (connect to actual executor)
    # Args: toolCallId, toolName, params
    toolExecutionRequested = Signal(str, str, dict)

    # Signal: Tool requires user confirmation
    # Args: toolCallId, toolName, params, toolDesc, toolType
    userConfirmationNeeded = Signal(str, str, dict, str, int)

    # toolCallId, toolName, toolType
    toolExecutionCancelled = Signal(str, str, int)

    # Signal: All tools complete, agent can continue
    agentContinuationReady = Signal()

    def __init__(
        self,
        strategy: Optional[ToolExecutionStrategy] = None,
        maxConcurrent: int = 4,
        # Optional callable: (toolName: str) -> Optional[AgentTool]
        toolLookupFn=None,
        parent: Optional[QObject] = None
    ):
        """Initialize the tool machine.
        
        Args:
            strategy: Execution strategy (defaults to DefaultStrategy)
            maxConcurrent: Maximum concurrent tool executions (default 4)
            toolLookupFn: Optional callable to resolve tools by name.
                         If provided, called first; falls back to AgentToolRegistry if returns None.
                         This allows UI tools and custom tool resolution.
            parent: Qt parent object
        """
        super().__init__(parent)
        self._strategy = strategy or DefaultStrategy()
        self._maxConcurrent = maxConcurrent
        self._toolLookupFn = toolLookupFn

        # Tool tracking
        self._toolQueue: List[ToolRequest] = []
        # toolCallId -> ToolRequest
        self._inProgress: Dict[str, ToolRequest] = {}

        # Grouping: tools in the same group wait for each other
        # groupId -> {remaining, auto_continue}
        self._autoToolGroups: Dict[int, Dict[str, object]] = {}

        # Metadata and state
        # toolCallId -> tool
        self._awaitingToolResults: Dict[str, AgentTool] = {}
        self._ignoredToolCallIds: Set[str] = set()  # toolCallIds user rejected

        # Sequencing
        self._nextAutoGroupId: int = 1

    # ========================================================================
    # Public API: Configuration
    # ========================================================================

    def setStrategy(self, strategy: ToolExecutionStrategy) -> None:
        """Change the tool execution strategy at runtime.
        
        Args:
            strategy: New strategy to use for future tool decisions
        """
        self._strategy = strategy
        logger.info(
            f"AgentToolMachine strategy changed to {strategy.__class__.__name__}")

    def setMaxConcurrent(self, maxConcurrent: int) -> None:
        """Change maximum concurrent execution limit.
        
        Args:
            maxConcurrent: New limit (must be >= 1)
        """
        if maxConcurrent < 1:
            maxConcurrent = 1
        self._maxConcurrent = maxConcurrent
        logger.info(f"AgentToolMachine maxConcurrent set to {maxConcurrent}")

    # ========================================================================
    # Public API: Tool Processing
    # ========================================================================

    def processToolCalls(self, toolCalls: List[Dict]) -> None:
        """Process tool calls from an assistant response.
        
        This is the main entry point for handling tool calls. It:
        1. Parses each tool call
        2. Consults the strategy to decide auto-run vs. confirmation
        3. Queues auto-run tools in batches
        4. Emits confirmation signals for non-auto tools
        5. Starts draining the queue
        
        Args:
            toolCalls: List of OpenAI-format tool calls, each with:
                      {"id": str, "type": "function", "function": {"name": str, "arguments": str}}
        """
        if not toolCalls:
            return

        autoGroupId: Optional[int] = None
        autoToolsCount = 0
        hasConfirmations = False

        for tc in (toolCalls or []):
            func = (tc or {}).get("function") or {}
            toolName = func.get("name")
            argsJson = func.get("arguments")
            toolCallId = (tc or {}).get("id")

            if not toolName:
                logger.warning(f"Tool call missing name: {tc}")
                continue

            # Parse arguments
            args = parseToolArguments(argsJson)

            # Get tool metadata
            tool = self._toolByName(toolName)
            toolType = tool.toolType if tool else ToolType.WRITE
            toolDesc = tool.description if tool else f"Tool: {toolName}"

            # Cache metadata
            if toolCallId:
                self._awaitingToolResults[toolCallId] = tool

            # Check strategy
            if self._strategy.shouldAutoRun(toolName, toolType, args):
                # Queue for auto-execution
                if autoGroupId is None:
                    autoGroupId = self._nextAutoGroupId
                    self._nextAutoGroupId += 1

                request = ToolRequest(
                    toolName=toolName,
                    params=args,
                    toolCallId=toolCallId,
                    groupId=autoGroupId,
                    source='auto',
                    toolType=toolType,
                    description=toolDesc,
                )
                self._toolQueue.append(request)
                autoToolsCount += 1

                logger.debug(
                    f"Auto-queued tool: {toolName} (callId={toolCallId}, group={autoGroupId})")
            else:
                # Requires user confirmation
                hasConfirmations = True
                self.userConfirmationNeeded.emit(
                    toolCallId or "",
                    toolName,
                    args,
                    toolDesc,
                    toolType)
                logger.debug(
                    f"Tool requires confirmation: {toolName} (callId={toolCallId})")

        # Set up batch tracking for auto-tools
        if autoGroupId is not None and autoToolsCount > 0:
            self._autoToolGroups[autoGroupId] = {
                "remaining": autoToolsCount,
                # Only auto-continue if no confirmations needed
                "auto_continue": not hasConfirmations,
            }
            logger.info(
                f"Created tool batch group {autoGroupId} with {autoToolsCount} tools (auto_continue={not hasConfirmations})")

            # Start executing queued tools
            QTimer.singleShot(0, self._drainQueue)

    def approveToolExecution(self, toolName: str, params: Dict, toolCallId: str) -> None:
        """User approved a tool execution - queue it.
        
        Args:
            toolName: Name of the approved tool
            params: Tool parameters
            toolCallId: Tool call ID for correlation
        """
        if not toolCallId:
            logger.warning(
                f"approveToolExecution called without toolCallId for {toolName}")
            return

        tool = self._toolByName(toolName)
        toolType = tool.toolType if tool else ToolType.WRITE
        toolDesc = tool.description if tool else f"Tool: {toolName}"
        self._awaitingToolResults[toolCallId] = tool

        # Create a new single-tool group for approved tool
        groupId = self._nextAutoGroupId
        self._nextAutoGroupId += 1
        self._autoToolGroups[groupId] = {
            "remaining": 1,
            "auto_continue": False,  # Don't auto-continue after manual approval
        }

        request = ToolRequest(
            toolName=toolName,
            params=params,
            toolCallId=toolCallId,
            groupId=groupId,
            source='approved',
            toolType=toolType,
            description=toolDesc,
        )
        self._toolQueue.append(request)

        logger.info(
            f"Tool approved: {toolName} (callId={toolCallId}, group={groupId})")

        # Start draining queue
        QTimer.singleShot(0, self._drainQueue)

    def rejectToolExecution(self, toolName: str, toolCallId: str) -> None:
        """User rejected a tool execution.
        
        Args:
            toolName: Name of the rejected tool
            toolCallId: Tool call ID
        """
        if toolCallId:
            self._ignoredToolCallIds.add(toolCallId)
            self._awaitingToolResults.pop(toolCallId, None)
            logger.info(f"Tool rejected: {toolName} (callId={toolCallId})")

        # Check if we can continue now
        if not self._awaitingToolResults and not self._inProgress:
            logger.info(
                "All tools complete after rejection, emitting agentContinuationReady")
            self.agentContinuationReady.emit()

    def onToolFinished(self, result: AgentToolResult) -> None:
        """Handle tool execution completion.
        
        Called when a tool executor finishes executing a tool.
        Processes the result, updates group tracking, and continues queue.
        
        Args:
            result: AgentToolResult with toolCallId, ok, output, toolName
        """
        toolCallId = result.toolCallId
        if not toolCallId:
            logger.warning(
                f"Tool result missing toolCallId: {result.toolName}")
            return

        # Ignore if cancelled/rejected
        if toolCallId in self._ignoredToolCallIds:
            self._ignoredToolCallIds.discard(toolCallId)
            self._awaitingToolResults.pop(toolCallId, None)
            logger.debug(f"Ignoring cancelled tool result: {toolCallId}")
            return

        # Record result
        request = self._inProgress.pop(toolCallId, None)
        self._awaitingToolResults.pop(toolCallId, None)

        logger.debug(
            f"Tool finished: {result.toolName} (callId={toolCallId}, ok={result.ok})")

        # Update group tracking if applicable
        if request and request.source == "auto" and request.groupId in self._autoToolGroups:
            groupId = request.groupId
            group = self._autoToolGroups[groupId]

            # Decrement remaining
            remaining = int(group.get("remaining", 0)) - 1
            group["remaining"] = remaining

            logger.debug(f"Tool group {groupId}: {remaining} remaining")

            # Check if batch complete
            if remaining <= 0:
                auto_continue = bool(group.get("auto_continue", False))
                del self._autoToolGroups[groupId]

                logger.info(
                    f"Tool batch {groupId} complete (auto_continue={auto_continue})")
                if not auto_continue:
                    return
            else:
                # Continue processing queue
                self._drainQueue()
                return

        # If everything done, signal ready
        if not self._awaitingToolResults and not self._inProgress:
            logger.info("All tools complete, emitting agentContinuationReady")
            self.agentContinuationReady.emit()

    # ========================================================================
    # Public API: State Management
    # ========================================================================

    def hasPendingResults(self) -> bool:
        """Check if waiting for tool results.
        
        Returns:
            True if any tools are awaiting results or in progress
        """
        return bool(self._awaitingToolResults or self._inProgress)

    def readyToContinue(self) -> bool:
        """Check if ready for agent continuation.
        
        Returns:
            True if no tools pending, queued, or executing
        """
        return not bool(self._awaitingToolResults or self._inProgress or self._toolQueue)

    def reset(self) -> None:
        """Clear all tool state and reset to initial state.
        
        Use this when starting a new conversation or clearing context.
        """
        self._toolQueue.clear()
        self._inProgress.clear()
        self._autoToolGroups.clear()
        self._awaitingToolResults.clear()
        self._ignoredToolCallIds.clear()
        self._nextAutoGroupId = 1
        logger.info("AgentToolMachine reset")

    # ========================================================================
    # Public API: Introspection (for debugging/testing)
    # ========================================================================

    def getInProgressTools(self) -> List[str]:
        """Get list of currently executing tool names.
        
        Returns:
            List of tool names currently in progress
        """
        return [req.toolName for req in self._inProgress.values()]

    def getQueuedTools(self) -> List[str]:
        """Get list of queued tool names.
        
        Returns:
            List of tool names waiting to execute
        """
        return [req.toolName for req in self._toolQueue]

    def getAwaitingCount(self) -> int:
        """Get count of tools awaiting results.
        
        Returns:
            Number of tool call IDs we're waiting for
        """
        return len(self._awaitingToolResults)

    def taskInProgress(self):
        return len(self._inProgress) > 0

    def rejectPendingResults(self):
        """ Cancel all in-progress tasks and clear state. """
        ignoredCallIds = self._ignoredToolCallIds.copy()
        for toolCallId, tool in self._awaitingToolResults.items():
            logger.info(f"Cancelling awaiting tool result: {toolCallId}")
            if tool:
                toolName = tool.name
                toolType = tool.toolType
            else:
                toolName = "Unknown"
                toolType = ToolType.WRITE
            ignoredCallIds.add(toolCallId)
            self.toolExecutionCancelled.emit(toolCallId, toolName, toolType)

        self.reset()
        self._ignoredToolCallIds = ignoredCallIds

    def addAwaitingToolResult(self, toolCallId: str, tool: AgentTool) -> None:
        self._awaitingToolResults[toolCallId] = tool

    # ========================================================================
    # Private Methods
    # ========================================================================

    def _drainQueue(self) -> None:
        """Start executing queued tools up to max concurrent limit.
        
        This is the core scheduling loop that:
        1. Checks how many slots are available
        2. Pulls requests from the queue
        3. Moves them to in-progress
        4. Emits execution signals
        """
        while len(self._inProgress) < self._maxConcurrent and self._toolQueue:
            request = self._toolQueue.pop(0)

            if not request.toolCallId:
                logger.warning(
                    f"Skipping tool request without callId: {request.toolName}")
                continue

            self._inProgress[request.toolCallId] = request

            logger.debug(
                f"Executing tool: {request.toolName} (callId={request.toolCallId}, concurrent={len(self._inProgress)})")

            self.toolExecutionRequested.emit(
                request.toolCallId,
                request.toolName,
                request.params,
            )

    def _toolByName(self, toolName: str) -> Optional[AgentTool]:
        """Get tool definition by name, checking custom lookup first, then registry.
        
        Supports both regular tools and UI tools if a lookup function is provided.
        
        Args:
            toolName: Name of the tool
            
        Returns:
            AgentTool if found (including UI tools), None otherwise
        """
        if not toolName:
            return None

        # First: check custom lookup function (supports UI tools)
        if self._toolLookupFn:
            tool = self._toolLookupFn(toolName)
            if tool:
                return tool

        # Second: check agent tool registry (regular tools + tools in registry)
        tool = AgentToolRegistry.tool_by_name(toolName)
        if tool:
            return tool

        # Not found anywhere
        logger.debug(f"Tool not found: {toolName}")
        return None
