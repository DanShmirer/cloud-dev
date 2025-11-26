"""
Queue Interface - Following Interface Segregation & Dependency Inversion Principles
Defines abstract interfaces that concrete implementations must follow
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from shared.models import Task, TaskResult, TaskStatus


class ITaskQueue(ABC):
    """
    Abstract interface for task queue operations
    Following Interface Segregation - only queue-related methods
    """

    @abstractmethod
    async def enqueue(self, task: Task) -> str:
        """Add task to queue, returns task_id"""
        pass

    @abstractmethod
    async def dequeue(self, timeout: Optional[int] = None) -> Optional[Task]:
        """Get next task from queue (blocking with optional timeout)"""
        pass

    @abstractmethod
    async def get_queue_length(self) -> int:
        """Get number of pending tasks"""
        pass

    @abstractmethod
    async def clear(self) -> int:
        """Clear all pending tasks, returns count cleared"""
        pass


class ITaskStore(ABC):
    """
    Abstract interface for task status and result storage
    Separate from queue to follow Interface Segregation
    """

    @abstractmethod
    async def save_task(self, task: Task) -> None:
        """Persist task metadata"""
        pass

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve task by ID"""
        pass

    @abstractmethod
    async def update_status(self, task_id: str, status: TaskStatus) -> None:
        """Update task status"""
        pass

    @abstractmethod
    async def save_result(self, result: TaskResult) -> None:
        """Store task execution result"""
        pass

    @abstractmethod
    async def get_result(self, task_id: str) -> Optional[TaskResult]:
        """Retrieve task result by task ID"""
        pass

    @abstractmethod
    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Task]:
        """List tasks with optional status filter"""
        pass


class ISessionStore(ABC):
    """
    Interface for managing Claude Code session continuations
    Separate interface for session-specific operations
    """

    @abstractmethod
    async def save_session(self, task_id: str, session_id: str) -> None:
        """Store session ID for task continuation"""
        pass

    @abstractmethod
    async def get_session(self, task_id: str) -> Optional[str]:
        """Retrieve session ID for task"""
        pass

    @abstractmethod
    async def delete_session(self, task_id: str) -> None:
        """Remove session mapping"""
        pass
