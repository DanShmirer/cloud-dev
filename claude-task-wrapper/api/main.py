"""
FastAPI API Gateway for Claude Task Wrapper
Provides REST endpoints for task submission and status tracking
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, List

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from shared.models import Task, TaskConfig, TaskType, TaskStatus, TaskPriority
from shared.queue import RedisTaskQueue, RedisTaskStore, RedisSessionStore


# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Pydantic models for API
class TaskConfigRequest(BaseModel):
    """Task configuration request model"""
    model: str = Field(default="sonnet", description="Claude model to use")
    allowed_tools: List[str] = Field(
        default=["Read", "Glob", "Grep"],
        description="List of allowed tools",
    )
    working_dir: str = Field(default="/workspace", description="Working directory")
    timeout_seconds: int = Field(default=300, ge=1, le=3600, description="Timeout in seconds")
    max_turns: int = Field(default=50, ge=1, le=200, description="Max conversation turns")
    verbose: bool = Field(default=False, description="Enable verbose output")


class TaskRequest(BaseModel):
    """Task submission request"""
    prompt: str = Field(..., min_length=1, description="Task prompt for Claude")
    task_type: str = Field(default="single", description="Task type: single or session")
    config: TaskConfigRequest = Field(default_factory=TaskConfigRequest)
    session_id: Optional[str] = Field(default=None, description="Session ID for continuation")
    callback_url: Optional[str] = Field(default=None, description="Webhook URL for completion")
    priority: int = Field(default=5, ge=1, le=20, description="Task priority (1-20)")


class TaskResponse(BaseModel):
    """Task submission response"""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """Task status response"""
    task_id: str
    status: str
    output: Optional[str] = None
    error: Optional[str] = None
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    duration_seconds: Optional[float] = None


class QueueStatsResponse(BaseModel):
    """Queue statistics response"""
    pending_tasks: int
    total_handlers: int


# Global state
redis_client: Optional[redis.Redis] = None
task_queue: Optional[RedisTaskQueue] = None
task_store: Optional[RedisTaskStore] = None
session_store: Optional[RedisSessionStore] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    global redis_client, task_queue, task_store, session_store

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    logger.info(f"Connecting to Redis at {redis_url}")

    redis_client = redis.from_url(redis_url, decode_responses=False)

    # Test connection
    await redis_client.ping()
    logger.info("Redis connection established")

    # Initialize stores
    task_queue = RedisTaskQueue(redis_client)
    task_store = RedisTaskStore(redis_client)
    session_store = RedisSessionStore(redis_client)

    yield

    # Cleanup
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")


# Create FastAPI app
app = FastAPI(
    title="Claude Task Wrapper API",
    description="API Gateway for injecting tasks into Claude Code CLI",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        await redis_client.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unhealthy: {str(e)}")


@app.post("/tasks", response_model=TaskResponse)
async def submit_task(request: TaskRequest):
    """
    Submit a new task to the queue
    Returns task ID for tracking
    """
    # Convert request to domain model
    config = TaskConfig(
        model=request.config.model,
        allowed_tools=request.config.allowed_tools,
        working_dir=request.config.working_dir,
        timeout_seconds=request.config.timeout_seconds,
        max_turns=request.config.max_turns,
        output_format="json",
        verbose=request.config.verbose,
    )

    task = Task(
        prompt=request.prompt,
        task_type=TaskType(request.task_type),
        config=config,
        priority=TaskPriority(request.priority) if request.priority in [p.value for p in TaskPriority] else TaskPriority.NORMAL,
        session_id=request.session_id,
        callback_url=request.callback_url,
    )

    # Save task metadata
    await task_store.save_task(task)

    # Enqueue for processing
    await task_queue.enqueue(task)

    logger.info(f"Task {task.task_id} enqueued with priority {task.priority.name}")

    return TaskResponse(
        task_id=task.task_id,
        status="queued",
        message=f"Task queued successfully with priority {task.priority.name}",
    )


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """
    Get task status and result
    """
    # Check for result first
    result = await task_store.get_result(task_id)
    if result:
        return TaskStatusResponse(
            task_id=task_id,
            status=result.status.value,
            output=result.output,
            error=result.error,
            session_id=result.session_id,
            cost_usd=result.cost_usd,
            duration_seconds=result.duration_seconds,
        )

    # Check task exists
    task = await task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Get current status from Redis
    key = f"claude:tasks:task:{task_id}"
    status = await redis_client.hget(key, "status")
    status_str = status.decode() if isinstance(status, bytes) else status if status else "pending"

    return TaskStatusResponse(
        task_id=task_id,
        status=status_str,
    )


@app.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
    """
    Cancel a pending task (cannot cancel running tasks)
    """
    task = await task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Check if already completed
    result = await task_store.get_result(task_id)
    if result:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task in status: {result.status.value}",
        )

    # Update status to cancelled
    await task_store.update_status(task_id, TaskStatus.CANCELLED)

    logger.info(f"Task {task_id} cancelled")
    return {"task_id": task_id, "status": "cancelled"}


@app.get("/tasks", response_model=List[TaskStatusResponse])
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    List tasks with optional status filter
    """
    task_status = TaskStatus(status) if status else None
    tasks = await task_store.list_tasks(status=task_status, limit=limit, offset=offset)

    responses = []
    for task in tasks:
        result = await task_store.get_result(task.task_id)
        if result:
            responses.append(TaskStatusResponse(
                task_id=task.task_id,
                status=result.status.value,
                output=result.output,
                error=result.error,
                session_id=result.session_id,
                cost_usd=result.cost_usd,
                duration_seconds=result.duration_seconds,
            ))
        else:
            responses.append(TaskStatusResponse(
                task_id=task.task_id,
                status=TaskStatus.PENDING.value,
            ))

    return responses


@app.get("/queue/stats", response_model=QueueStatsResponse)
async def get_queue_stats():
    """
    Get queue statistics
    """
    pending = await task_queue.get_queue_length()
    return QueueStatsResponse(
        pending_tasks=pending,
        total_handlers=2,  # Single + Session handlers
    )


@app.post("/queue/clear")
async def clear_queue():
    """
    Clear all pending tasks from queue (admin operation)
    """
    count = await task_queue.clear()
    logger.warning(f"Queue cleared: {count} tasks removed")
    return {"cleared": count}


# Session management endpoints
@app.post("/sessions/{task_id}/continue", response_model=TaskResponse)
async def continue_session(task_id: str, request: TaskRequest):
    """
    Continue an existing session with a new prompt
    """
    # Get session ID from previous result
    result = await task_store.get_result(task_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No result found for task {task_id}",
        )

    if not result.session_id:
        raise HTTPException(
            status_code=400,
            detail="Previous task did not return a session ID",
        )

    # Create continuation task
    config = TaskConfig(
        model=request.config.model,
        allowed_tools=request.config.allowed_tools,
        working_dir=request.config.working_dir,
        timeout_seconds=request.config.timeout_seconds,
        max_turns=request.config.max_turns,
        output_format="json",
        verbose=request.config.verbose,
    )

    task = Task(
        prompt=request.prompt,
        task_type=TaskType.SESSION,
        config=config,
        session_id=result.session_id,  # Use previous session
        callback_url=request.callback_url,
        priority=TaskPriority(request.priority) if request.priority in [p.value for p in TaskPriority] else TaskPriority.NORMAL,
    )

    await task_store.save_task(task)
    await task_queue.enqueue(task)

    logger.info(f"Session continuation task {task.task_id} enqueued (session: {result.session_id})")

    return TaskResponse(
        task_id=task.task_id,
        status="queued",
        message=f"Session continuation queued (session: {result.session_id[:8]}...)",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
