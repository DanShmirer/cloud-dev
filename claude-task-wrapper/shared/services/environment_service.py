"""
Environment Service - Business logic for environment task operations
Following Single Responsibility and Dependency Inversion
"""
import json
import logging
from typing import Optional, List, Dict, Any

import redis.asyncio as redis

from shared.models import EnvironmentType, EnvironmentTask, EnvironmentTaskResult

logger = logging.getLogger(__name__)


class EnvironmentService:
    """
    Service layer for environment task operations
    Handles business logic separate from API concerns
    """

    # Redis key prefixes
    TASK_KEY_PREFIX = "claude:env_tasks"
    RESULT_KEY_PREFIX = "claude:env_results"
    QUEUE_KEY = "claude:env_tasks:queue"

    def __init__(
        self,
        redis_client: redis.Redis,
        result_ttl_seconds: int = 86400 * 7,  # 7 days
    ):
        self._redis = redis_client
        self._result_ttl = result_ttl_seconds

    def _task_key(self, task_id: str) -> str:
        return f"{self.TASK_KEY_PREFIX}:{task_id}"

    def _result_key(self, task_id: str) -> str:
        return f"{self.RESULT_KEY_PREFIX}:{task_id}"

    async def submit_task(
        self,
        env_type: EnvironmentType,
        inputs: Dict[str, Any],
        additional_prompt: Optional[str] = None,
        priority: int = 5,
        callback_url: Optional[str] = None,
    ) -> EnvironmentTask:
        """
        Submit a new environment task
        Returns the created task
        """
        task = EnvironmentTask(
            env_type=env_type,
            inputs=inputs,
            additional_prompt=additional_prompt,
            priority=priority,
            callback_url=callback_url,
        )

        # Store task metadata
        await self._redis.hset(
            self._task_key(task.task_id),
            mapping={
                "data": json.dumps(task.to_dict()),
                "status": "queued",
            },
        )

        # Add to priority queue
        score = priority * 1e12 + task.created_at.timestamp()
        await self._redis.zadd(
            self.QUEUE_KEY,
            {json.dumps(task.to_dict()): score},
        )

        logger.info(f"Environment task {task.task_id} submitted for {env_type.value}")

        return task

    async def get_task(self, task_id: str) -> Optional[EnvironmentTask]:
        """Get task by ID"""
        task_data = await self._redis.hget(self._task_key(task_id), "data")
        if not task_data:
            return None

        data = json.loads(task_data.decode() if isinstance(task_data, bytes) else task_data)
        return EnvironmentTask.from_dict(data)

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task status and result if available
        Returns dict with status info
        """
        task_data = await self._redis.hgetall(self._task_key(task_id))
        if not task_data:
            return None

        status = task_data.get(b"status", b"unknown").decode()
        data = json.loads(task_data.get(b"data", b"{}").decode())

        response = {
            "task_id": task_id,
            "env_type": data.get("env_type"),
            "status": status,
        }

        # Get result if available
        result_data = await self._redis.get(self._result_key(task_id))
        if result_data:
            result = json.loads(result_data.decode())
            response.update({
                "workspace_path": result.get("workspace_path"),
                "step_results": result.get("step_results"),
                "final_analysis": result.get("final_analysis"),
                "error": result.get("error"),
                "total_duration_seconds": result.get("total_duration_seconds"),
            })

        return response

    async def get_result(self, task_id: str) -> Optional[EnvironmentTaskResult]:
        """Get task result"""
        result_data = await self._redis.get(self._result_key(task_id))
        if not result_data:
            return None

        data = json.loads(result_data.decode())
        return EnvironmentTaskResult(
            task_id=data["task_id"],
            env_type=EnvironmentType(data["env_type"]),
            status=data["status"],
            workspace_path=data.get("workspace_path", ""),
            final_analysis=data.get("final_analysis"),
            error=data.get("error"),
            total_duration_seconds=data.get("total_duration_seconds", 0),
        )

    async def update_status(self, task_id: str, status: str) -> None:
        """Update task status"""
        await self._redis.hset(self._task_key(task_id), "status", status)

    async def save_result(self, result: EnvironmentTaskResult) -> None:
        """Save task result"""
        await self._redis.setex(
            self._result_key(result.task_id),
            self._result_ttl,
            json.dumps(result.to_dict()),
        )
        await self.update_status(result.task_id, result.status)

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a pending task
        Returns True if cancelled
        """
        task_data = await self._redis.hgetall(self._task_key(task_id))
        if not task_data:
            return False

        status = task_data.get(b"status", b"").decode()
        if status in ("completed", "failed"):
            return False

        await self.update_status(task_id, "cancelled")
        logger.info(f"Environment task {task_id} cancelled")
        return True

    async def list_tasks(
        self,
        env_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List environment tasks with optional filters"""
        cursor = 0
        tasks = []
        pattern = f"{self.TASK_KEY_PREFIX}:*"

        while len(tasks) < limit:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)

            for key in keys:
                if key.endswith(b":queue"):
                    continue

                task_data = await self._redis.hgetall(key)
                if not task_data:
                    continue

                data = json.loads(task_data.get(b"data", b"{}").decode())
                task_status = task_data.get(b"status", b"unknown").decode()

                # Filter by env_type
                if env_type and data.get("env_type") != env_type:
                    continue

                # Filter by status
                if status and task_status != status:
                    continue

                tasks.append({
                    "task_id": data.get("task_id"),
                    "env_type": data.get("env_type"),
                    "status": task_status,
                })

                if len(tasks) >= limit:
                    break

            if cursor == 0:
                break

        return tasks

    async def dequeue_task(self, timeout: int = 5) -> Optional[EnvironmentTask]:
        """Get next task from queue"""
        result = await self._redis.bzpopmax(self.QUEUE_KEY, timeout=timeout)
        if result:
            _, task_json, _ = result
            data = json.loads(task_json)
            return EnvironmentTask.from_dict(data)
        return None
