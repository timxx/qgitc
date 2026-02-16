# -*- coding: utf-8 -*-

"""Task session store: Persistent storage for task sessions.

Stores completed/archived task metadata and history summaries.
Maintains an index for quick lookups. Keeps dependencies minimal (JSON only).
"""

import json
import os
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from qgitc.aichathistory import AiChatHistory
from qgitc.common import logger
from qgitc.tasksession import TaskSession


class TaskSessionStore(QObject):
    """Persistent storage for task sessions.
    
    Stores task metadata and history in simple JSON format under a data directory.
    
    Layout:
        dataDir/
            task_index.json          # Metadata for all tasks
            tasks/
                taskId_metadata.json  # Task metadata
                taskId_history.json   # Task history messages
    """

    taskSaved = Signal(str)  # taskId
    taskLoaded = Signal(str)  # taskId

    def __init__(self, dataDir: str, parent: Optional[QObject] = None):
        """Initialize store.
        
        Args:
            dataDir: Base directory for task storage (e.g., ~/.qgitc/tasks/)
            parent: Qt parent
        """
        super().__init__(parent)
        self._dataDir = dataDir
        self._tasksDir = os.path.join(dataDir, "tasks")
        self._indexPath = os.path.join(dataDir, "task_index.json")

        # Ensure directories exist
        os.makedirs(self._tasksDir, exist_ok=True)

        # In-memory index (loaded on first access)
        # taskId -> [metadata, history]
        self._index: Optional[Dict[str, List[str]]] = None

    def _ensureIndex(self) -> None:
        """Load or create the task index."""
        if self._index is not None:
            return

        self._index = {}
        if os.path.exists(self._indexPath):
            try:
                with open(self._indexPath, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load task index: {e}")
                self._index = {}

    def _saveIndex(self) -> None:
        """Persist the task index."""
        try:
            os.makedirs(os.path.dirname(self._indexPath), exist_ok=True)
            with open(self._indexPath, "w", encoding="utf-8") as f:
                json.dump(self._index or {}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save task index: {e}")

    def saveTask(self, task: TaskSession) -> bool:
        """Save task metadata and history.
        
        Args:
            task: TaskSession to save
            
        Returns:
            True if successful
        """
        self._ensureIndex()

        try:
            # Save metadata
            metadataPath = os.path.join(
                self._tasksDir, f"{task.taskId}_metadata.json")
            taskDict = task.toDict()
            with open(metadataPath, "w", encoding="utf-8") as f:
                json.dump(taskDict, f, indent=2)

            # Save history
            historyPath = os.path.join(
                self._tasksDir, f"{task.taskId}_history.json")
            historyDict = task.history.toDict()
            with open(historyPath, "w", encoding="utf-8") as f:
                json.dump(historyDict, f, indent=2)

            # Update index
            self._index[task.taskId] = [
                task.taskType,
                task.createdAt.isoformat(),
                task.status,
            ]
            self._saveIndex()

            self.taskSaved.emit(task.taskId)
            logger.debug(f"Saved task {task.taskId} ({task.taskType})")
            return True
        except Exception as e:
            logger.error(f"Failed to save task {task.taskId}: {e}")
            return False

    def loadTask(self, taskId: str) -> Optional[TaskSession]:
        """Load a task by ID.
        
        Args:
            taskId: Task ID to load
            
        Returns:
            TaskSession if found, None otherwise
        """
        try:
            metadataPath = os.path.join(
                self._tasksDir, f"{taskId}_metadata.json")
            historyPath = os.path.join(
                self._tasksDir, f"{taskId}_history.json")

            if not os.path.exists(metadataPath) or not os.path.exists(historyPath):
                return None

            # Load metadata
            with open(metadataPath, "r", encoding="utf-8") as f:
                taskDict = json.load(f)

            # Load history
            with open(historyPath, "r", encoding="utf-8") as f:
                historyDict = json.load(f)

            # Reconstruct task
            task = TaskSession.fromDict(taskDict)
            task.history = AiChatHistory.fromDict(historyDict)

            self.taskLoaded.emit(taskId)
            logger.debug(f"Loaded task {taskId}")
            return task
        except Exception as e:
            logger.error(f"Failed to load task {taskId}: {e}")
            return None

    def listTasks(self) -> List[TaskSession]:
        """List all stored tasks (metadata only, no history).
        
        Returns:
            List of TaskSession objects (history not loaded)
        """
        self._ensureIndex()

        tasks = []
        for taskId in self._index.keys():
            try:
                metadataPath = os.path.join(
                    self._tasksDir, f"{taskId}_metadata.json")
                if os.path.exists(metadataPath):
                    with open(metadataPath, "r", encoding="utf-8") as f:
                        taskDict = json.load(f)
                    task = TaskSession.fromDict(taskDict)
                    tasks.append(task)
            except Exception as e:
                logger.warning(
                    f"Failed to load task metadata for {taskId}: {e}")

        # Sort by creation time (newest first)
        tasks.sort(key=lambda t: t.createdAt, reverse=True)
        return tasks

    def deleteTask(self, taskId: str) -> bool:
        """Delete a task and its artifacts.
        
        Args:
            taskId: Task ID to delete
            
        Returns:
            True if successful
        """
        self._ensureIndex()

        try:
            metadataPath = os.path.join(
                self._tasksDir, f"{taskId}_metadata.json")
            historyPath = os.path.join(
                self._tasksDir, f"{taskId}_history.json")

            for path in [metadataPath, historyPath]:
                if os.path.exists(path):
                    os.remove(path)

            if taskId in self._index:
                del self._index[taskId]
                self._saveIndex()

            logger.debug(f"Deleted task {taskId}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete task {taskId}: {e}")
            return False

    def getTasksByType(self, taskType: str) -> List[TaskSession]:
        """Get all tasks of a specific type.
        
        Args:
            taskType: Task type to filter by (e.g., "code_review")
            
        Returns:
            List of matching TaskSession objects
        """
        allTasks = self.listTasks()
        return [t for t in allTasks if t.taskType == taskType]

    def getTasksByStatus(self, status: str) -> List[TaskSession]:
        """Get all tasks with a specific status.
        
        Args:
            status: Status to filter by (e.g., "done", "failed")
            
        Returns:
            List of matching TaskSession objects
        """
        allTasks = self.listTasks()
        return [t for t in allTasks if t.status == status]
