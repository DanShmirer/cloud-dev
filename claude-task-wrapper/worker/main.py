"""
Worker Service - Processes tasks from Redis queue
Main entry point for the worker container
Handles both regular tasks and environment-based tasks
"""
import os
import sys
import json
import signal
import asyncio
import logging
from typing import Optional

import redis.asyncio as redis
import httpx

from shared.models import (
    Task, TaskResult, TaskStatus,
    EnvironmentTask, EnvironmentTaskResult, EnvironmentType,
)
from shared.queue import RedisTaskQueue, RedisTaskStore, RedisSessionStore
from shared.workspace import WorkspaceManager
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


class Worker:
    """
    Task worker that processes Claude Code tasks from queue
    Follows Single Responsibility - only handles task processing loop
    """

    def __init__(
        self,
        redis_url: str,
        claude_binary: str = "claude",
        workspace_root: str = "/workspace",
        poll_timeout: int = 5,
        max_concurrent: int = 1,
    ):
        self._redis_url = redis_url
        self._claude_binary = claude_binary
        self._workspace_root = workspace_root
        self._poll_timeout = poll_timeout
        self._max_concurrent = max_concurrent
        self._running = False
        self._current_tasks: set = set()

        # Will be initialized in start()
        self._redis: Optional[redis.Redis] = None
        self._queue: Optional[RedisTaskQueue] = None
        self._store: Optional[RedisTaskStore] = None
        self._session_store: Optional[RedisSessionStore] = None
        self._registry: Optional[TaskHandlerRegistry] = None

    async def _init_connections(self) -> None:
        """Initialize Redis connections and handler registry"""
        logger.info(f"Connecting to Redis at {self._redis_url}")
        self._redis = redis.from_url(self._redis_url, decode_responses=False)

        # Test connection
        await self._redis.ping()
        logger.info("Redis connection established")

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

    async def _cleanup(self) -> None:
        """Cleanup connections"""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")

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

        # Update status to running
        await self._store.update_status(task.task_id, TaskStatus.RUNNING)

        # Execute task
        result = await handler.execute(task)

        # Save session if returned
        if result.session_id:
            await self._session_store.save_session(task.task_id, result.session_id)

        return result

    async def _send_callback(self, result: TaskResult, callback_url: str) -> None:
        """Send result to callback webhook"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    callback_url,
                    json=result.to_dict(),
                    timeout=30.0,
                )
                if response.status_code >= 400:
                    logger.warning(
                        f"Callback failed for task {result.task_id}: "
                        f"status={response.status_code}"
                    )
                else:
                    logger.info(f"Callback sent for task {result.task_id}")
        except Exception as e:
            logger.error(f"Callback error for task {result.task_id}: {e}")

    async def _worker_loop(self, worker_id: int) -> None:
        """Main worker loop - polls queue and processes tasks"""
        logger.info(f"Worker {worker_id} started")

        while self._running:
            try:
                # Poll for task with timeout
                task = await self._queue.dequeue(timeout=self._poll_timeout)

                if task is None:
                    # No task available, continue polling
                    continue

                # Check if task was cancelled
                existing = await self._store.get_task(task.task_id)
                if existing:
                    key = f"claude:tasks:task:{task.task_id}"
                    status = await self._redis.hget(key, "status")
                    status_str = status.decode() if isinstance(status, bytes) else status
                    if status_str == TaskStatus.CANCELLED.value:
                        logger.info(f"Task {task.task_id} was cancelled, skipping")
                        continue

                # Track current task
                self._current_tasks.add(task.task_id)

                try:
                    # Process task
                    result = await self._process_task(task)

                    # Store result
                    await self._store.save_result(result)

                    logger.info(
                        f"Task {task.task_id} completed with status {result.status.value}"
                    )

                    # Send callback if configured
                    if task.callback_url:
                        await self._send_callback(result, task.callback_url)

                finally:
                    self._current_tasks.discard(task.task_id)

            except asyncio.CancelledError:
                logger.info(f"Worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.exception(f"Worker {worker_id} error: {e}")
                # Continue processing other tasks
                await asyncio.sleep(1)

        logger.info(f"Worker {worker_id} stopped")

    async def start(self) -> None:
        """Start the worker"""
        self._running = True

        await self._init_connections()

        # Start worker tasks
        workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self._max_concurrent)
        ]

        logger.info(f"Started {self._max_concurrent} worker(s)")

        # Wait for all workers
        try:
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            logger.info("Workers cancelled")
        finally:
            await self._cleanup()

    def stop(self) -> None:
        """Signal workers to stop"""
        logger.info("Stopping worker...")
        self._running = False


class EnvironmentWorker:
    """
    Worker that processes environment-based tasks
    Executes full environment workflows with isolated workspaces
    """

    def __init__(
        self,
        redis_url: str,
        claude_binary: str = "claude",
        workspaces_root: str = "/workspaces",
        poll_timeout: int = 5,
        max_concurrent: int = 1,
    ):
        self._redis_url = redis_url
        self._claude_binary = claude_binary
        self._workspaces_root = workspaces_root
        self._poll_timeout = poll_timeout
        self._max_concurrent = max_concurrent
        self._running = False
        self._current_tasks: set = set()

        # Will be initialized in start()
        self._redis: Optional[redis.Redis] = None
        self._workspace_manager: Optional[WorkspaceManager] = None
        self._env_registry: Optional[EnvironmentRegistry] = None
        self._executor: Optional[EnvironmentExecutor] = None

    async def _init_connections(self) -> None:
        """Initialize connections and registries"""
        logger.info(f"Connecting to Redis at {self._redis_url}")
        self._redis = redis.from_url(self._redis_url, decode_responses=False)

        await self._redis.ping()
        logger.info("Redis connection established")

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

    async def _cleanup(self) -> None:
        """Cleanup connections"""
        if self._redis:
            await self._redis.close()
            logger.info("Redis connection closed")

    async def _dequeue_env_task(self, timeout: int = 5) -> Optional[EnvironmentTask]:
        """Get next environment task from queue"""
        queue_key = "claude:env_tasks:queue"

        result = await self._redis.bzpopmax(queue_key, timeout=timeout)
        if result:
            _, task_json, _ = result
            data = json.loads(task_json)
            return EnvironmentTask.from_dict(data)
        return None

    async def _update_task_status(self, task_id: str, status: str) -> None:
        """Update environment task status in Redis"""
        task_key = f"claude:env_tasks:{task_id}"
        await self._redis.hset(task_key, "status", status)

    async def _save_result(self, result: EnvironmentTaskResult) -> None:
        """Save environment task result"""
        result_key = f"claude:env_results:{result.task_id}"
        await self._redis.setex(
            result_key,
            86400 * 7,  # 7 days TTL
            json.dumps(result.to_dict()),
        )
        await self._update_task_status(result.task_id, result.status)

    async def _send_callback(
        self,
        result: EnvironmentTaskResult,
        callback_url: str,
    ) -> None:
        """Send result to callback webhook"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    callback_url,
                    json=result.to_dict(),
                    timeout=30.0,
                )
                if response.status_code >= 400:
                    logger.warning(
                        f"Callback failed for env task {result.task_id}: "
                        f"status={response.status_code}"
                    )
                else:
                    logger.info(f"Callback sent for env task {result.task_id}")
        except Exception as e:
            logger.error(f"Callback error for env task {result.task_id}: {e}")

    async def _process_env_task(self, task: EnvironmentTask) -> EnvironmentTaskResult:
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

    async def _worker_loop(self, worker_id: int) -> None:
        """Main worker loop for environment tasks"""
        logger.info(f"Environment worker {worker_id} started")

        while self._running:
            try:
                # Poll for environment task
                task = await self._dequeue_env_task(timeout=self._poll_timeout)

                if task is None:
                    continue

                # Check if cancelled
                task_key = f"claude:env_tasks:{task.task_id}"
                status = await self._redis.hget(task_key, "status")
                if status and status.decode() == "cancelled":
                    logger.info(f"Env task {task.task_id} was cancelled, skipping")
                    continue

                self._current_tasks.add(task.task_id)

                try:
                    # Update status
                    await self._update_task_status(task.task_id, "running")

                    # Process task
                    result = await self._process_env_task(task)

                    # Save result
                    await self._save_result(result)

                    logger.info(
                        f"Env task {task.task_id} completed with status {result.status}"
                    )

                    # Send callback if configured
                    if task.callback_url:
                        await self._send_callback(result, task.callback_url)

                finally:
                    self._current_tasks.discard(task.task_id)

            except asyncio.CancelledError:
                logger.info(f"Environment worker {worker_id} cancelled")
                break
            except Exception as e:
                logger.exception(f"Environment worker {worker_id} error: {e}")
                await asyncio.sleep(1)

        logger.info(f"Environment worker {worker_id} stopped")

    async def start(self) -> None:
        """Start the environment worker"""
        self._running = True

        await self._init_connections()

        workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self._max_concurrent)
        ]

        logger.info(f"Started {self._max_concurrent} environment worker(s)")

        try:
            await asyncio.gather(*workers)
        except asyncio.CancelledError:
            logger.info("Environment workers cancelled")
        finally:
            await self._cleanup()

    def stop(self) -> None:
        """Signal workers to stop"""
        logger.info("Stopping environment worker...")
        self._running = False


async def main():
    """Main entry point - runs both regular and environment workers"""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    claude_binary = os.getenv("CLAUDE_BINARY", "claude")
    workspace_root = os.getenv("WORKSPACE_ROOT", "/workspace")
    workspaces_root = os.getenv("WORKSPACES_ROOT", "/workspaces")
    max_concurrent = int(os.getenv("MAX_CONCURRENT_TASKS", "1"))
    worker_mode = os.getenv("WORKER_MODE", "all")  # "all", "regular", "environment"

    workers = []

    # Create regular task worker
    if worker_mode in ("all", "regular"):
        regular_worker = Worker(
            redis_url=redis_url,
            claude_binary=claude_binary,
            workspace_root=workspace_root,
            max_concurrent=max_concurrent,
        )
        workers.append(("regular", regular_worker))

    # Create environment task worker
    if worker_mode in ("all", "environment"):
        env_worker = EnvironmentWorker(
            redis_url=redis_url,
            claude_binary=claude_binary,
            workspaces_root=workspaces_root,
            max_concurrent=max_concurrent,
        )
        workers.append(("environment", env_worker))

    if not workers:
        logger.error(f"Invalid WORKER_MODE: {worker_mode}")
        return

    # Handle shutdown signals
    loop = asyncio.get_event_loop()

    def signal_handler():
        for name, worker in workers:
            worker.stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    logger.info(f"Starting workers in mode: {worker_mode}")

    # Start all workers concurrently
    await asyncio.gather(*[
        worker.start() for name, worker in workers
    ])

    logger.info("All workers shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
