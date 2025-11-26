"""
Redis Implementation of Queue Interfaces
Following Dependency Inversion - implements abstract interfaces
Following Open/Closed - can be extended without modifying base classes
"""
import json
import asyncio
from datetime import datetime
from typing import Optional, List

import redis.asyncio as redis

from shared.models import Task, TaskResult, TaskStatus
from .base import ITaskQueue, ITaskStore, ISessionStore


class RedisTaskQueue(ITaskQueue):
    """
    Redis-based task queue implementation using sorted sets for priority
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        queue_name: str = "claude:tasks:queue",
    ):
        self._redis = redis_client
        self._queue_name = queue_name

    async def enqueue(self, task: Task) -> str:
        """Add task to priority queue using sorted set"""
        # Score = priority * 1e12 + timestamp (for FIFO within same priority)
        score = task.priority.value * 1e12 + datetime.utcnow().timestamp()
        await self._redis.zadd(
            self._queue_name,
            {json.dumps(task.to_dict()): score},
        )
        return task.task_id

    async def dequeue(self, timeout: Optional[int] = None) -> Optional[Task]:
        """
        Get highest priority task from queue
        Uses BZPOPMAX for blocking behavior if timeout specified
        """
        if timeout:
            # Blocking pop with timeout
            result = await self._redis.bzpopmax(self._queue_name, timeout=timeout)
            if result:
                _, task_json, _ = result
                return Task.from_dict(json.loads(task_json))
            return None
        else:
            # Non-blocking: get and remove highest score item
            result = await self._redis.zpopmax(self._queue_name, count=1)
            if result:
                task_json, _ = result[0]
                return Task.from_dict(json.loads(task_json))
            return None

    async def get_queue_length(self) -> int:
        """Get number of pending tasks"""
        return await self._redis.zcard(self._queue_name)

    async def clear(self) -> int:
        """Clear all pending tasks"""
        length = await self.get_queue_length()
        await self._redis.delete(self._queue_name)
        return length


class RedisTaskStore(ITaskStore):
    """
    Redis-based task metadata and result storage
    Uses hashes for efficient field access
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        prefix: str = "claude:tasks",
        result_ttl: int = 86400 * 7,  # 7 days default TTL for results
    ):
        self._redis = redis_client
        self._prefix = prefix
        self._result_ttl = result_ttl

    def _task_key(self, task_id: str) -> str:
        return f"{self._prefix}:task:{task_id}"

    def _result_key(self, task_id: str) -> str:
        return f"{self._prefix}:result:{task_id}"

    def _status_set_key(self, status: TaskStatus) -> str:
        return f"{self._prefix}:status:{status.value}"

    async def save_task(self, task: Task) -> None:
        """Persist task metadata with status tracking"""
        key = self._task_key(task.task_id)
        await self._redis.hset(key, mapping={
            "data": json.dumps(task.to_dict()),
            "status": TaskStatus.PENDING.value,
        })
        # Add to status set for filtering
        await self._redis.sadd(
            self._status_set_key(TaskStatus.PENDING),
            task.task_id,
        )

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve task by ID"""
        data = await self._redis.hget(self._task_key(task_id), "data")
        if data:
            return Task.from_dict(json.loads(data))
        return None

    async def update_status(self, task_id: str, status: TaskStatus) -> None:
        """Update task status and move between status sets"""
        key = self._task_key(task_id)
        old_status = await self._redis.hget(key, "status")

        if old_status:
            # Remove from old status set
            await self._redis.srem(
                self._status_set_key(TaskStatus(old_status.decode() if isinstance(old_status, bytes) else old_status)),
                task_id,
            )

        # Update status and add to new set
        await self._redis.hset(key, "status", status.value)
        await self._redis.sadd(self._status_set_key(status), task_id)

    async def save_result(self, result: TaskResult) -> None:
        """Store task execution result with TTL"""
        key = self._result_key(result.task_id)
        await self._redis.setex(
            key,
            self._result_ttl,
            json.dumps(result.to_dict()),
        )
        # Update task status
        await self.update_status(result.task_id, result.status)

    async def get_result(self, task_id: str) -> Optional[TaskResult]:
        """Retrieve task result by task ID"""
        data = await self._redis.get(self._result_key(task_id))
        if data:
            return TaskResult.from_dict(json.loads(data))
        return None

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Task]:
        """List tasks with optional status filter"""
        if status:
            # Get task IDs from status set
            task_ids = await self._redis.smembers(self._status_set_key(status))
            task_ids = list(task_ids)[offset:offset + limit]
        else:
            # Get all tasks (scan pattern)
            cursor = 0
            task_ids = []
            pattern = f"{self._prefix}:task:*"
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                task_ids.extend([k.split(":")[-1] for k in keys])
                if cursor == 0:
                    break
            task_ids = task_ids[offset:offset + limit]

        # Fetch task data
        tasks = []
        for task_id in task_ids:
            task_id_str = task_id.decode() if isinstance(task_id, bytes) else task_id
            task = await self.get_task(task_id_str)
            if task:
                tasks.append(task)
        return tasks


class RedisSessionStore(ISessionStore):
    """
    Redis-based session ID storage for multi-turn conversations
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        prefix: str = "claude:sessions",
        session_ttl: int = 86400,  # 24 hours default TTL
    ):
        self._redis = redis_client
        self._prefix = prefix
        self._session_ttl = session_ttl

    def _session_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}"

    async def save_session(self, task_id: str, session_id: str) -> None:
        """Store session ID with TTL"""
        await self._redis.setex(
            self._session_key(task_id),
            self._session_ttl,
            session_id,
        )

    async def get_session(self, task_id: str) -> Optional[str]:
        """Retrieve session ID"""
        session_id = await self._redis.get(self._session_key(task_id))
        if session_id:
            return session_id.decode() if isinstance(session_id, bytes) else session_id
        return None

    async def delete_session(self, task_id: str) -> None:
        """Remove session mapping"""
        await self._redis.delete(self._session_key(task_id))


async def create_redis_stores(
    redis_url: str = "redis://localhost:6379",
) -> tuple[RedisTaskQueue, RedisTaskStore, RedisSessionStore]:
    """Factory function to create all Redis stores"""
    client = redis.from_url(redis_url, decode_responses=False)
    return (
        RedisTaskQueue(client),
        RedisTaskStore(client),
        RedisSessionStore(client),
    )
