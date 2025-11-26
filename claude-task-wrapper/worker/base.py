"""
Base Worker - Abstract base class for task workers
Implements Template Method pattern to reduce duplication between Worker types
Following SOLID principles - specifically Open/Closed and DRY
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any, TypeVar, Generic

import redis.asyncio as redis
import httpx

from shared.config import AppConfig, get_config

logger = logging.getLogger(__name__)

# Type variables for task and result types
TTask = TypeVar("TTask")
TResult = TypeVar("TResult")


class BaseWorker(ABC, Generic[TTask, TResult]):
    """
    Abstract base worker implementing common worker loop logic.

    Subclasses implement the template methods for task-specific behavior:
    - _init_resources(): Initialize task-specific resources
    - _cleanup_resources(): Cleanup task-specific resources
    - _dequeue_task(): Get next task from queue
    - _check_cancelled(): Check if task was cancelled
    - _update_running_status(): Mark task as running
    - _process_task(): Process the task
    - _save_result(): Save the result
    - _get_callback_url(): Get callback URL from task
    - _get_task_id(): Get task ID from task/result
    """

    def __init__(
        self,
        redis_url: str,
        poll_timeout: int = 5,
        max_concurrent: int = 1,
        worker_name: str = "worker",
    ):
        self._redis_url = redis_url
        self._poll_timeout = poll_timeout
        self._max_concurrent = max_concurrent
        self._worker_name = worker_name
        self._running = False
        self._current_tasks: set = set()

        # Redis connection - initialized in start()
        self._redis: Optional[redis.Redis] = None

    async def _init_redis(self) -> None:
        """Initialize Redis connection"""
        logger.info(f"Connecting to Redis at {self._redis_url}")
        self._redis = redis.from_url(self._redis_url, decode_responses=False)

        # Test connection
        await self._redis.ping()
        logger.info("Redis connection established")

    async def _cleanup_redis(self) -> None:
        """Cleanup Redis connection"""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")

    @abstractmethod
    async def _init_resources(self) -> None:
        """Initialize task-specific resources (handlers, registries, etc.)"""
        pass

    @abstractmethod
    async def _cleanup_resources(self) -> None:
        """Cleanup task-specific resources"""
        pass

    @abstractmethod
    async def _dequeue_task(self, timeout: int) -> Optional[TTask]:
        """Dequeue next task from the queue"""
        pass

    @abstractmethod
    async def _check_cancelled(self, task: TTask) -> bool:
        """Check if task was cancelled before processing"""
        pass

    @abstractmethod
    async def _update_running_status(self, task: TTask) -> None:
        """Update task status to running"""
        pass

    @abstractmethod
    async def _process_task(self, task: TTask) -> TResult:
        """Process a single task and return result"""
        pass

    @abstractmethod
    async def _save_result(self, result: TResult) -> None:
        """Save task result to storage"""
        pass

    @abstractmethod
    def _get_callback_url(self, task: TTask) -> Optional[str]:
        """Get callback URL from task, if any"""
        pass

    @abstractmethod
    def _get_task_id(self, task: TTask) -> str:
        """Get task ID from task object"""
        pass

    @abstractmethod
    def _get_result_status(self, result: TResult) -> str:
        """Get status string from result for logging"""
        pass

    @abstractmethod
    def _result_to_dict(self, result: TResult) -> dict:
        """Convert result to dictionary for callback"""
        pass

    async def _send_callback(self, result: TResult, callback_url: str) -> None:
        """Send result to callback webhook"""
        task_id = self._get_task_id_from_result(result)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    callback_url,
                    json=self._result_to_dict(result),
                    timeout=30.0,
                )
                if response.status_code >= 400:
                    logger.warning(
                        f"Callback failed for {self._worker_name} task {task_id}: "
                        f"status={response.status_code}"
                    )
                else:
                    logger.info(f"Callback sent for {self._worker_name} task {task_id}")
        except Exception as e:
            logger.error(f"Callback error for {self._worker_name} task {task_id}: {e}")

    def _get_task_id_from_result(self, result: TResult) -> str:
        """Get task ID from result - override if different from task"""
        # Default implementation assumes result has task_id attribute
        return getattr(result, "task_id", "unknown")

    async def _worker_loop(self, worker_id: int) -> None:
        """
        Main worker loop - polls queue and processes tasks.
        This is the Template Method that orchestrates the workflow.
        """
        logger.info(f"{self._worker_name} {worker_id} started")

        while self._running:
            try:
                # Poll for task with timeout
                task = await self._dequeue_task(timeout=self._poll_timeout)

                if task is None:
                    # No task available, continue polling
                    continue

                # Check if task was cancelled
                if await self._check_cancelled(task):
                    task_id = self._get_task_id(task)
                    logger.info(f"Task {task_id} was cancelled, skipping")
                    continue

                # Track current task
                task_id = self._get_task_id(task)
                self._current_tasks.add(task_id)

                try:
                    # Update status to running
                    await self._update_running_status(task)

                    # Process task
                    result = await self._process_task(task)

                    # Save result
                    await self._save_result(result)

                    status = self._get_result_status(result)
                    logger.info(
                        f"Task {task_id} completed with status {status}"
                    )

                    # Send callback if configured
                    callback_url = self._get_callback_url(task)
                    if callback_url:
                        await self._send_callback(result, callback_url)

                finally:
                    self._current_tasks.discard(task_id)

            except asyncio.CancelledError:
                logger.info(f"{self._worker_name} {worker_id} cancelled")
                break
            except Exception as e:
                logger.exception(f"{self._worker_name} {worker_id} error: {e}")
                # Continue processing other tasks
                await asyncio.sleep(1)

        logger.info(f"{self._worker_name} {worker_id} stopped")

    async def start(self) -> None:
        """Start the worker"""
        self._running = True

        # Initialize connections
        await self._init_redis()
        await self._init_resources()

        # Start worker tasks
        workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self._max_concurrent)
        ]

        logger.info(f"Started {self._max_concurrent} {self._worker_name}(s)")

        # Wait for all workers
        try:
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            logger.info(f"{self._worker_name}s cancelled")
        finally:
            await self._cleanup_resources()
            await self._cleanup_redis()

    def stop(self) -> None:
        """Signal workers to stop"""
        logger.info(f"Stopping {self._worker_name}...")
        self._running = False

    @property
    def redis(self) -> Optional[redis.Redis]:
        """Access to Redis client for subclasses"""
        return self._redis

    @property
    def is_running(self) -> bool:
        """Check if worker is running"""
        return self._running

    @property
    def current_task_count(self) -> int:
        """Get number of currently processing tasks"""
        return len(self._current_tasks)
