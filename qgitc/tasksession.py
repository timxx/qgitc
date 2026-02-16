# -*- coding: utf-8 -*-

"""Task session: A bounded execution context for specialized agent tasks.

TaskSession wraps:
- Task metadata (ID, type, timestamps, status)
- Independent AI chat history (separate from main chat)
- Optional plan steps, execution progress, and artifacts

Tasks are stored separately from chat history and can be archived,
reloaded, or linked from main chat summaries.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from qgitc.aichathistory import AiChatHistory


@dataclass
class TaskSession:
    """A single bounded task (e.g., code review, conflict resolution)."""

    # Identity
    taskId: str                         # UUID
    taskType: str                       # "code_review", "resolve_conflict", "free_agent"

    # Timestamps
    createdAt: datetime
    completedAt: Optional[datetime]     # None if ongoing

    # Status & Progress
    status: str                         # "executing", "planning", "done", "failed"
    summary: Optional[str]              # Compact summary for main chat
    lastAssistantMessage: Optional[str]  # Last message from assistant

    # History (separate from main chat)
    history: AiChatHistory              # Owned by this task

    # Optional Planning
    # True if AI decided to plan, False if not, None if not asked
    planDecision: Optional[bool]
    planSteps: Optional[List[str]]      # ["Step 1: ...", "Step 2: ...", ...]
    planApprovedAt: Optional[datetime]  # When user approved plan
    skippedSteps: List[int]             # User-skipped step indices (0-based)

    # Artifacts & Metrics
    artifacts: List[str]                # Paths to diffs, logs, reports, etc.
    toolsRun: List[tuple]               # [(tool_name, success), ...]
    linesChanged: int                   # If applicable (from diffs)
    issuesFound: int                    # If applicable (from code review)

    # Compaction
    compactedAt: Optional[datetime]     # When history was last compacted
    compactionSummary: Optional[str]    # Summarized old messages

    def __init__(self, taskType: str):
        """Initialize a new task session."""
        self.taskId = str(uuid.uuid4())
        self.taskType = taskType

        self.createdAt = datetime.now()
        self.completedAt = None

        self.status = "executing"
        self.summary = None
        self.lastAssistantMessage = None

        # Create independent history
        self.history = AiChatHistory()

        # Planning
        self.planDecision = None
        self.planSteps = None
        self.planApprovedAt = None
        self.skippedSteps = []

        # Artifacts & Progress
        self.artifacts = []
        self.toolsRun = []
        self.linesChanged = 0
        self.issuesFound = 0

        # Compaction
        self.compactedAt = None
        self.compactionSummary = None

    def toDict(self) -> Dict:
        """Serialize for storage (compact, not full history)."""
        return {
            "taskId": self.taskId,
            "taskType": self.taskType,
            "createdAt": self.createdAt.isoformat(),
            "completedAt": self.completedAt.isoformat() if self.completedAt else None,
            "status": self.status,
            "summary": self.summary,
            "lastAssistantMessage": self.lastAssistantMessage,
            # History stored separately
            "historyId": self.history.historyId,
            "planDecision": self.planDecision,
            "planSteps": self.planSteps,
            "planApprovedAt": self.planApprovedAt.isoformat() if self.planApprovedAt else None,
            "skippedSteps": self.skippedSteps,
            "artifacts": self.artifacts,
            "toolsRun": self.toolsRun,
            "linesChanged": self.linesChanged,
            "issuesFound": self.issuesFound,
            "compactedAt": self.compactedAt.isoformat() if self.compactedAt else None,
            "compactionSummary": self.compactionSummary,
        }

    @staticmethod
    def fromDict(data: Dict) -> "TaskSession":
        """Deserialize from storage."""
        task = TaskSession(data["taskType"])
        task.taskId = data.get("taskId", task.taskId)
        task.createdAt = datetime.fromisoformat(data["createdAt"])
        if data.get("completedAt"):
            task.completedAt = datetime.fromisoformat(data["completedAt"])

        task.status = data.get("status", "executing")
        task.summary = data.get("summary")
        task.lastAssistantMessage = data.get("lastAssistantMessage")

        task.planDecision = data.get("planDecision")
        task.planSteps = data.get("planSteps")
        if data.get("planApprovedAt"):
            task.planApprovedAt = datetime.fromisoformat(
                data["planApprovedAt"])
        task.skippedSteps = data.get("skippedSteps", [])

        task.artifacts = data.get("artifacts", [])
        task.toolsRun = [tuple(t) if isinstance(t, (list, tuple)) else t
                         for t in data.get("toolsRun", [])]
        task.linesChanged = data.get("linesChanged", 0)
        task.issuesFound = data.get("issuesFound", 0)

        if data.get("compactedAt"):
            task.compactedAt = datetime.fromisoformat(data["compactedAt"])
        task.compactionSummary = data.get("compactionSummary")

        return task

    def addTool(self, toolName: str, success: bool) -> None:
        """Record a tool execution."""
        self.toolsRun.append((toolName, success))

    def addArtifact(self, artifactPath: str) -> None:
        """Register an artifact (diff, log, report, etc.)."""
        if artifactPath not in self.artifacts:
            self.artifacts.append(artifactPath)

    def markComplete(self, status: str = "done") -> None:
        """Mark task as complete."""
        self.status = status
        self.completedAt = datetime.now()
