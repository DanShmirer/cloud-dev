"""
Worker Service - Processes tasks from Redis queue
Main entry point for the worker container
Handles both regular tasks and environment-based tasks
"""
import os
import json
import signal
import asyncio
import logging
from typing import Optional

from shared.models import (
    Task, TaskResult, TaskStatus,
    EnvironmentTask, EnvironmentTaskResult,
)
from shared.queue import RedisTaskQueue, RedisTaskStore, RedisSessionStore
from shared.workspace import WorkspaceManager
from shared.config import get_config, WorkerMode
from worker.base import BaseWorker
from worker.handlers import (
    TaskHandlerRegistry,
    ClaudeCodeHandler,
    ClaudeSessionHandler,
)
from environments import (
    create_default_registry,
    EnvironmentExecutor,
    EnvironmentRegistry,
)


# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Worker(BaseWorker[Task, TaskResult]):
    """
    Task worker that processes Claude Code tasks from queue.
    Extends BaseWorker with Task-specific implementations.
    """

    def __init__(
        self,
        redis_url: str,
        claude_binary: str = "claude",
        workspace_root: str = "/workspace",
        poll_timeout: int = 5,
        max_concurrent: int = 1,
    ):
        super().__init__(
            redis_url=redis_url,
            poll_timeout=poll_timeout,
            max_concurrent=max_concurrent,
            worker_name="Worker",
        )
        self._claude_binary = claude_binary
        self._workspace_root = workspace_root

        # Task-specific resources
        self._queue: Optional[RedisTaskQueue] = None
        self._store: Optional[RedisTaskStore] = None
        self._session_store: Optional[RedisSessionStore] = None
        self._registry: Optional[TaskHandlerRegistry] = None

    async def _init_resources(self) -> None:
        """Initialize task-specific resources"""
        # Initialize stores
        self._queue = RedisTaskQueue(self._redis)
        self._store = RedisTaskStore(self._redis)
        self._session_store = RedisSessionStore(self._redis)

        # Initialize handler registry with handlers
        self._registry = TaskHandlerRegistry()

        # Register handlers (order matters - later registered has priority)
        self._registry.register(ClaudeCodeHandler(
            claude_binary=self._claude_binary,
            workspace_root=self._workspace_root,
        ))
        self._registry.register(ClaudeSessionHandler(
            claude_binary=self._claude_binary,
            workspace_root=self._workspace_root,
        ))

        logger.info(f"Registered handlers: {self._registry.list_handlers()}")

    async def _cleanup_resources(self) -> None:
        """Cleanup task-specific resources"""
        # No additional cleanup needed for this worker
        pass

    async def _dequeue_task(self, timeout: int) -> Optional[Task]:
        """Dequeue next task from the queue"""
        return await self._queue.dequeue(timeout=timeout)

    async def _check_cancelled(self, task: Task) -> bool:
        """Check if task was cancelled before processing"""
        existing = await self._store.get_task(task.task_id)
        if existing:
            key = f"claude:tasks:task:{task.task_id}"
            status = await self._redis.hget(key, "status")
            status_str = status.decode() if isinstance(status, bytes) else status
            if status_str == TaskStatus.CANCELLED.value:
                return True
        return False

    async def _update_running_status(self, task: Task) -> None:
        """Update task status to running"""
        await self._store.update_status(task.task_id, TaskStatus.RUNNING)

    async def _process_task(self, task: Task) -> TaskResult:
        """Process a single task using appropriate handler"""
        handler = self._registry.get_handler(task)
        if not handler:
            logger.error(f"No handler found for task {task.task_id} (type: {task.task_type})")
            return TaskResult.failure(
                task_id=task.task_id,
                error=f"No handler available for task type: {task.task_type.value}",
            )

        logger.info(f"Processing task {task.task_id} with handler {handler.name}")

        # Execute task
        result = await handler.execute(task)

        # Save session if returned
        if result.session_id:
            await self._session_store.save_session(task.task_id, result.session_id)

        return result

    async def _save_result(self, result: TaskResult) -> None:
        """Save task result to storage"""
        await self._store.save_result(result)

    def _get_callback_url(self, task: Task) -> Optional[str]:
        """Get callback URL from task"""
        return task.callback_url

    def _get_task_id(self, task: Task) -> str:
        """Get task ID from task object"""
        return task.task_id

    def _get_result_status(self, result: TaskResult) -> str:
        """Get status string from result"""
        return result.status.value

    def _result_to_dict(self, result: TaskResult) -> dict:
        """Convert result to dictionary for callback"""
        return result.to_dict()


class EnvironmentWorker(BaseWorker[EnvironmentTask, EnvironmentTaskResult]):
    """
    Worker that processes environment-based tasks.
    Extends BaseWorker with environment-specific implementations.
    """

    def __init__(
        self,
        redis_url: str,
        claude_binary: str = "claude",
        workspaces_root: str = "/workspaces",
        poll_timeout: int = 5,
        max_concurrent: int = 1,
    ):
        super().__init__(
            redis_url=redis_url,
            poll_timeout=poll_timeout,
            max_concurrent=max_concurrent,
            worker_name="EnvironmentWorker",
        )
        self._claude_binary = claude_binary
        self._workspaces_root = workspaces_root

        # Environment-specific resources
        self._workspace_manager: Optional[WorkspaceManager] = None
        self._env_registry: Optional[EnvironmentRegistry] = None
        self._executor: Optional[EnvironmentExecutor] = None

    async def _init_resources(self) -> None:
        """Initialize environment-specific resources"""
        # Initialize workspace manager
        self._workspace_manager = WorkspaceManager(
            base_path=self._workspaces_root,
            cleanup_after_hours=24,
        )

        # Initialize environment registry
        self._env_registry = create_default_registry()

        # Initialize executor
        self._executor = EnvironmentExecutor(
            workspace_manager=self._workspace_manager,
            claude_binary=self._claude_binary,
        )

        logger.info(f"Available environments: {[e.value for e in self._env_registry.get_all_types()]}")

    async def _cleanup_resources(self) -> None:
        """Cleanup environment-specific resources"""
        # No additional cleanup needed
        pass

    async def _dequeue_task(self, timeout: int) -> Optional[EnvironmentTask]:
        """Get next environment task from queue"""
        queue_key = "claude:env_tasks:queue"

        result = await self._redis.bzpopmax(queue_key, timeout=timeout)
        if result:
            _, task_json, _ = result
            data = json.loads(task_json)
            return EnvironmentTask.from_dict(data)
        return None

    async def _check_cancelled(self, task: EnvironmentTask) -> bool:
        """Check if environment task was cancelled"""
        task_key = f"claude:env_tasks:{task.task_id}"
        status = await self._redis.hget(task_key, "status")
        if status and status.decode() == "cancelled":
            return True
        return False

    async def _update_running_status(self, task: EnvironmentTask) -> None:
        """Update environment task status to running"""
        task_key = f"claude:env_tasks:{task.task_id}"
        await self._redis.hset(task_key, "status", "running")

    async def _process_task(self, task: EnvironmentTask) -> EnvironmentTaskResult:
        """Process an environment task"""
        env = self._env_registry.get(task.env_type)
        if not env:
            return EnvironmentTaskResult(
                task_id=task.task_id,
                env_type=task.env_type,
                status="failed",
                workspace_path="",
                error=f"Unknown environment type: {task.env_type.value}",
            )

        logger.info(f"Processing env task {task.task_id} with {env.name}")

        # Execute environment workflow
        result = await self._executor.execute(env, task)

        return result

    async def _save_result(self, result: EnvironmentTaskResult) -> None:
        """Save environment task result"""
        result_key = f"claude:env_results:{result.task_id}"
        await self._redis.setex(
            result_key,
            86400 * 7,  # 7 days TTL
            json.dumps(result.to_dict()),
        )
        # Also update task status
        task_key = f"claude:env_tasks:{result.task_id}"
        await self._redis.hset(task_key, "status", result.status)

    def _get_callback_url(self, task: EnvironmentTask) -> Optional[str]:
        """Get callback URL from environment task"""
        return task.callback_url

    def _get_task_id(self, task: EnvironmentTask) -> str:
        """Get task ID from environment task"""
        return task.task_id

    def _get_result_status(self, result: EnvironmentTaskResult) -> str:
        """Get status string from environment result"""
        return result.status

    def _result_to_dict(self, result: EnvironmentTaskResult) -> dict:
        """Convert environment result to dictionary for callback"""
        return result.to_dict()


async def main():
    """Main entry point - runs both regular and environment workers"""
    # Load centralized configuration
    config = get_config()

    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        return

    workers = []

    # Create regular task worker
    if config.worker.mode in (WorkerMode.ALL, WorkerMode.REGULAR):
        regular_worker = Worker(
            redis_url=config.redis.url,
            claude_binary=config.claude.binary_path,
            workspace_root=config.worker.workspace_root,
            poll_timeout=config.worker.poll_timeout_seconds,
            max_concurrent=config.worker.max_concurrent_tasks,
        )
        workers.append(("regular", regular_worker))

    # Create environment task worker
    if config.worker.mode in (WorkerMode.ALL, WorkerMode.ENVIRONMENT):
        env_worker = EnvironmentWorker(
            redis_url=config.redis.url,
            claude_binary=config.claude.binary_path,
            workspaces_root=config.worker.workspaces_root,
            poll_timeout=config.worker.poll_timeout_seconds,
            max_concurrent=config.worker.max_concurrent_tasks,
        )
        workers.append(("environment", env_worker))

    if not workers:
        logger.error(f"Invalid WORKER_MODE: {config.worker.mode}")
        return

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def signal_handler():
        for name, worker in workers:
            worker.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    logger.info(f"Starting workers in mode: {config.worker.mode.value}")

    # Start all workers concurrently
    await asyncio.gather(*[
        worker.start() for name, worker in workers
    ])

    logger.info("All workers shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
