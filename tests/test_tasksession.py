# -*- coding: utf-8 -*-

"""Tests for TaskSession."""

import unittest
from datetime import datetime

from qgitc.tasksession import TaskSession


class TestTaskSessionCreation(unittest.TestCase):
    """Test TaskSession initialization and basic operations."""

    def test_create_task_session(self):
        """Create a new task session."""
        task = TaskSession("code_review")

        self.assertIsNotNone(task.taskId)
        self.assertEqual(task.taskType, "code_review")
        self.assertEqual(task.status, "executing")
        self.assertIsNone(task.completedAt)
        self.assertIsNone(task.summary)
        self.assertIsNotNone(task.history)
        self.assertEqual(len(task.history.messages), 0)

    def test_task_id_is_unique(self):
        """Each task gets a unique ID."""
        task1 = TaskSession("code_review")
        task2 = TaskSession("code_review")

        self.assertNotEqual(task1.taskId, task2.taskId)

    def test_add_tool(self):
        """Record tool execution."""
        task = TaskSession("code_review")

        task.addTool("git_status", True)
        task.addTool("read_file", True)
        task.addTool("apply_patch", False)

        self.assertEqual(len(task.toolsRun), 3)
        self.assertEqual(task.toolsRun[0], ("git_status", True))
        self.assertEqual(task.toolsRun[2], ("apply_patch", False))

    def test_add_artifact(self):
        """Register artifacts."""
        task = TaskSession("code_review")

        task.addArtifact("/path/to/review.txt")
        task.addArtifact("/path/to/diff.patch")

        self.assertEqual(len(task.artifacts), 2)
        self.assertIn("/path/to/review.txt", task.artifacts)

    def test_add_duplicate_artifact_not_added_twice(self):
        """Duplicate artifacts are not added twice."""
        task = TaskSession("code_review")

        task.addArtifact("/path/to/review.txt")
        task.addArtifact("/path/to/review.txt")

        self.assertEqual(len(task.artifacts), 1)

    def test_mark_complete(self):
        """Mark task as complete."""
        task = TaskSession("code_review")

        self.assertIsNone(task.completedAt)
        task.markComplete("done")

        self.assertEqual(task.status, "done")
        self.assertIsNotNone(task.completedAt)


class TestTaskSessionSerialization(unittest.TestCase):
    """Test TaskSession serialization and deserialization."""

    def test_to_dict_has_all_fields(self):
        """TaskSession.toDict() includes all key fields."""
        task = TaskSession("code_review")
        task.summary = "Test summary"
        task.addTool("git_diff", True)
        task.linesChanged = 42
        task.issuesFound = 3
        task.markComplete("done")

        taskDict = task.toDict()

        self.assertEqual(taskDict["taskId"], task.taskId)
        self.assertEqual(taskDict["taskType"], "code_review")
        self.assertEqual(taskDict["status"], "done")
        self.assertEqual(taskDict["summary"], "Test summary")
        self.assertIsNotNone(taskDict["completedAt"])
        self.assertEqual(taskDict["linesChanged"], 42)
        self.assertEqual(taskDict["issuesFound"], 3)

    def test_round_trip_serialization(self):
        """Serialize and deserialize preserves state."""
        task1 = TaskSession("resolve_conflict")
        task1.summary = "Conflict resolved"
        task1.addTool("git_show_file", True)
        task1.addArtifact("/path/to/resolved.txt")
        task1.linesChanged = 10
        task1.markComplete("done")

        # Serialize
        taskDict = task1.toDict()

        # Deserialize
        task2 = TaskSession.fromDict(taskDict)

        # Verify
        self.assertEqual(task2.taskId, task1.taskId)
        self.assertEqual(task2.taskType, "resolve_conflict")
        self.assertEqual(task2.status, "done")
        self.assertEqual(task2.summary, "Conflict resolved")
        self.assertEqual(len(task2.toolsRun), 1)
        self.assertEqual(task2.toolsRun[0][0], "git_show_file")
        self.assertEqual(len(task2.artifacts), 1)
        self.assertEqual(task2.linesChanged, 10)


class TestTaskSessionPlanning(unittest.TestCase):
    """Test plan-related fields."""

    def test_plan_steps(self):
        """Set and retrieve plan steps."""
        task = TaskSession("code_review")

        task.planDecision = True
        task.planSteps = ["Step 1: Read file",
                          "Step 2: Analyze", "Step 3: Report"]
        task.planApprovedAt = datetime.now()

        self.assertTrue(task.planDecision)
        self.assertEqual(len(task.planSteps), 3)
        self.assertIsNotNone(task.planApprovedAt)

    def test_skipped_steps(self):
        """Track skipped plan steps."""
        task = TaskSession("code_review")
        task.planSteps = ["Step 1", "Step 2", "Step 3"]

        task.skippedSteps = [1]  # Skip step 2 (index 1)

        self.assertIn(1, task.skippedSteps)

    def test_plan_serialization(self):
        """Plan fields serialize/deserialize correctly."""
        task1 = TaskSession("code_review")
        task1.planDecision = True
        task1.planSteps = ["Read", "Analyze", "Report"]
        task1.planApprovedAt = datetime.now()
        task1.skippedSteps = [1]

        taskDict = task1.toDict()
        task2 = TaskSession.fromDict(taskDict)

        self.assertEqual(task2.planDecision, task1.planDecision)
        self.assertEqual(task2.planSteps, task1.planSteps)
        self.assertIsNotNone(task2.planApprovedAt)
        self.assertEqual(task2.skippedSteps, [1])


class TestTaskSessionCompaction(unittest.TestCase):
    """Test compaction-related fields."""

    def test_compaction_metadata(self):
        """Track compaction state."""
        task = TaskSession("code_review")

        self.assertIsNone(task.compactedAt)
        self.assertIsNone(task.compactionSummary)

        task.compactedAt = datetime.now()
        task.compactionSummary = "Compacted: 50 messages -> 5"

        self.assertIsNotNone(task.compactedAt)
        self.assertTrue("Compacted" in task.compactionSummary)

    def test_compaction_serialization(self):
        """Compaction fields serialize/deserialize."""
        task1 = TaskSession("code_review")
        compactedTime = datetime.now()
        task1.compactedAt = compactedTime
        task1.compactionSummary = "Old messages summarized"

        taskDict = task1.toDict()
        task2 = TaskSession.fromDict(taskDict)

        self.assertIsNotNone(task2.compactedAt)
        self.assertEqual(task2.compactionSummary, "Old messages summarized")
