"""
Task Service - Business logic for task operations
Following Single Responsibility and Dependency Inversion
Separates business logic from API layer
"""
import logging
from typing import Optional, List

from shared.models import (
    Task, TaskResult, TaskConfig, TaskType, TaskStatus, TaskPriority,
)
from shared.queue import ITaskQueue, ITaskStore, ISessionStore

logger = logging.getLogger(__name__)


class TaskService:
    """
    Service layer for task operations
    Handles business logic separate from API concerns
    Depends on abstractions (interfaces) for DI
    """

    def __init__(
        self,
        task_queue: ITaskQueue,
        task_store: ITaskStore,
        session_store: ISessionStore,
    ):
        self._queue = task_queue
        self._store = task_store
        self._session_store = session_store

    async def submit_task(
        self,
        prompt: str,
        task_type: TaskType = TaskType.SINGLE,
        config: Optional[TaskConfig] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        session_id: Optional[str] = None,
        callback_url: Optional[str] = None,
    ) -> Task:
        """
        Submit a new task for processing
        Returns the created task
        """
        if config is None:
            config = TaskConfig()

        task = Task(
            prompt=prompt,
            task_type=task_type,
            config=config,
            priority=priority,
            session_id=session_id,
            callback_url=callback_url,
        )

        # Save task metadata
        await self._store.save_task(task)

        # Enqueue for processing
        await self._queue.enqueue(task)

        logger.info(f"Task {task.task_id} submitted with priority {priority.name}")

        return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        return await self._store.get_task(task_id)

    async def get_task_status(self, task_id: str) -> dict:
        """
        Get task status and result if available
        Returns dict with status info
        """
        # Check for result first
        result = await self._store.get_result(task_id)
        if result:
            return {
                "task_id": task_id,
                "status": result.status.value,
                "output": result.output,
                "error": result.error,
                "session_id": result.session_id,
                "cost_usd": result.cost_usd,
                "duration_seconds": result.duration_seconds,
            }

        # Check task exists
        task = await self._store.get_task(task_id)
        if not task:
            return None

        return {
            "task_id": task_id,
            "status": TaskStatus.PENDING.value,
        }

    async def get_result(self, task_id: str) -> Optional[TaskResult]:
        """Get task result"""
        return await self._store.get_result(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task
        Returns True if cancelled, False if not possible
        """
        # Check task exists
        task = await self._store.get_task(task_id)
        if not task:
            return False

        # Check if already completed
        result = await self._store.get_result(task_id)
        if result:
            return False

        # Update status to cancelled
        await self._store.update_status(task_id, TaskStatus.CANCELLED)
        logger.info(f"Task {task_id} cancelled")

        return True

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Task]:
        """List tasks with optional status filter"""
        return await self._store.list_tasks(
            status=status,
            limit=limit,
            offset=offset,
        )

    async def continue_session(
        self,
        previous_task_id: str,
        prompt: str,
        config: Optional[TaskConfig] = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        callback_url: Optional[str] = None,
    ) -> Optional[Task]:
        """
        Continue an existing session with a new prompt
        Returns new task or None if session not found
        """
        # Get previous result
        result = await self._store.get_result(previous_task_id)
        if not result or not result.session_id:
            return None

        # Create continuation task
        return await self.submit_task(
            prompt=prompt,
            task_type=TaskType.SESSION,
            config=config,
            priority=priority,
            session_id=result.session_id,
            callback_url=callback_url,
        )

    async def get_queue_stats(self) -> dict:
        """Get queue statistics"""
        pending = await self._queue.get_queue_length()
        return {
            "pending_tasks": pending,
        }

    async def clear_queue(self) -> int:
        """Clear all pending tasks"""
        count = await self._queue.clear()
        logger.warning(f"Queue cleared: {count} tasks removed")
        return count
