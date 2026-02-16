# -*- coding: utf-8 -*-

"""Tests for TaskSessionStore."""

import unittest
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication

from qgitc.tasksession import TaskSession
from qgitc.tasksessionstore import TaskSessionStore


class TestTaskSessionStore(unittest.TestCase):
    """Test TaskSessionStore persistence."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for Qt signals."""
        if not QCoreApplication.instance():
            cls._app = QCoreApplication([])

    def setUp(self):
        """Create a temporary directory for each test."""
        self.tempDir = TemporaryDirectory()
        self.store = TaskSessionStore(self.tempDir.name)

    def tearDown(self):
        """Clean up temporary directory."""
        self.tempDir.cleanup()

    def test_save_and_load_task(self):
        """Save a task and load it back."""
        task1 = TaskSession("code_review")
        task1.summary = "Review completed"
        task1.addTool("git_diff", True)
        task1.issuesFound = 5
        task1.markComplete("done")

        # Save
        self.assertTrue(self.store.saveTask(task1))

        # Load
        task2 = self.store.loadTask(task1.taskId)

        # Verify
        self.assertIsNotNone(task2)
        self.assertEqual(task2.taskId, task1.taskId)
        self.assertEqual(task2.taskType, "code_review")
        self.assertEqual(task2.status, "done")
        self.assertEqual(task2.summary, "Review completed")
        self.assertEqual(task2.issuesFound, 5)
        self.assertEqual(len(task2.toolsRun), 1)

    def test_load_nonexistent_task_returns_none(self):
        """Loading a nonexistent task returns None."""
        task = self.store.loadTask("non_existent_id")
        self.assertIsNone(task)

    def test_list_tasks(self):
        """List all stored tasks."""
        task1 = TaskSession("code_review")
        task1.summary = "Task 1"
        task2 = TaskSession("resolve_conflict")
        task2.summary = "Task 2"

        self.store.saveTask(task1)
        self.store.saveTask(task2)

        tasks = self.store.listTasks()

        self.assertEqual(len(tasks), 2)
        self.assertIn(task1.taskId, [t.taskId for t in tasks])
        self.assertIn(task2.taskId, [t.taskId for t in tasks])

    def test_list_tasks_sorted_by_creation_time(self):
        """Listed tasks are sorted by creation time (newest first)."""
        task1 = TaskSession("code_review")
        task2 = TaskSession("code_review")

        self.store.saveTask(task1)
        self.store.saveTask(task2)  # task2 created after task1

        tasks = self.store.listTasks()

        # task2 should be first (newest)
        self.assertEqual(tasks[0].taskId, task2.taskId)
        self.assertEqual(tasks[1].taskId, task1.taskId)

    def test_delete_task(self):
        """Delete a task."""
        task = TaskSession("code_review")
        self.store.saveTask(task)

        # Verify task exists
        self.assertIsNotNone(self.store.loadTask(task.taskId))

        # Delete
        self.assertTrue(self.store.deleteTask(task.taskId))

        # Verify task is gone
        self.assertIsNone(self.store.loadTask(task.taskId))

    def test_get_tasks_by_type(self):
        """Filter tasks by type."""
        task1 = TaskSession("code_review")
        task1.summary = "Review 1"
        task2 = TaskSession("code_review")
        task2.summary = "Review 2"
        task3 = TaskSession("resolve_conflict")
        task3.summary = "Resolve 1"

        self.store.saveTask(task1)
        self.store.saveTask(task2)
        self.store.saveTask(task3)

        reviews = self.store.getTasksByType("code_review")
        resolves = self.store.getTasksByType("resolve_conflict")

        self.assertEqual(len(reviews), 2)
        self.assertEqual(len(resolves), 1)
        self.assertTrue(all(t.taskType == "code_review" for t in reviews))
        self.assertTrue(
            all(t.taskType == "resolve_conflict" for t in resolves))

    def test_get_tasks_by_status(self):
        """Filter tasks by status."""
        task1 = TaskSession("code_review")
        task1.status = "done"
        task2 = TaskSession("code_review")
        task2.status = "executing"
        task3 = TaskSession("code_review")
        task3.status = "failed"

        self.store.saveTask(task1)
        self.store.saveTask(task2)
        self.store.saveTask(task3)

        done_tasks = self.store.getTasksByStatus("done")
        executing_tasks = self.store.getTasksByStatus("executing")

        self.assertEqual(len(done_tasks), 1)
        self.assertEqual(len(executing_tasks), 1)
        self.assertEqual(done_tasks[0].status, "done")

    def test_save_signal_emitted(self):
        """taskSaved signal is emitted when task is saved."""
        task = TaskSession("code_review")

        signalEmitted = []
        self.store.taskSaved.connect(
            lambda taskId: signalEmitted.append(taskId))

        self.store.saveTask(task)

        self.assertEqual(len(signalEmitted), 1)
        self.assertEqual(signalEmitted[0], task.taskId)

    def test_load_signal_emitted(self):
        """taskLoaded signal is emitted when task is loaded."""
        task = TaskSession("code_review")
        self.store.saveTask(task)

        signalEmitted = []
        self.store.taskLoaded.connect(
            lambda taskId: signalEmitted.append(taskId))

        self.store.loadTask(task.taskId)

        self.assertEqual(len(signalEmitted), 1)
        self.assertEqual(signalEmitted[0], task.taskId)

    def test_save_preserves_history(self):
        """Task history is preserved when saved and loaded."""
        task1 = TaskSession("code_review")
        # Note: history is empty by default; we're just testing that it survives round-trip
        task1.history.messages = [{"role": "user", "content": "Test message"}]

        self.store.saveTask(task1)
        task2 = self.store.loadTask(task1.taskId)

        self.assertEqual(task2.history.historyId, task1.history.historyId)
        self.assertEqual(len(task2.history.messages), 1)
        self.assertEqual(task2.history.messages[0]["content"], "Test message")
