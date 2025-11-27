"""
FastAPI API Gateway for Claude Task Wrapper
Provides REST endpoints for task submission and status tracking
Serves the web UI for interactive task management
"""
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, List

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from shared.models import (
    Task, TaskConfig, TaskType, TaskStatus, TaskPriority,
    EnvironmentType, EnvironmentTask,
)
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
    prompt: Optional[str] = None
    created_at: Optional[str] = None
    output: Optional[str] = None
    error: Optional[str] = None
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    duration_seconds: Optional[float] = None


class QueueStatsResponse(BaseModel):
    """Queue statistics response"""
    pending_tasks: int
    total_handlers: int


# Environment-based task models
class EnvironmentTaskRequest(BaseModel):
    """Request for environment-based task execution"""
    env_type: str = Field(..., description="Environment type (e.g., crash_analysis)")
    inputs: Dict[str, Any] = Field(..., description="Environment-specific inputs")
    additional_prompt: Optional[str] = Field(
        default=None,
        description="Additional instructions for the analysis",
    )
    priority: int = Field(default=5, ge=1, le=20, description="Task priority")
    callback_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for completion notification",
    )


class CrashAnalysisRequest(BaseModel):
    """Convenience model for crash analysis tasks"""
    repo_url: str = Field(..., description="Git repository URL")
    backtrace: str = Field(..., description="Crash backtrace/stack trace")
    commit_hash: Optional[str] = Field(
        default=None,
        description="Git commit hash where crash occurred",
    )
    branch: Optional[str] = Field(
        default=None,
        description="Git branch (if no commit_hash)",
    )
    logs: Optional[str] = Field(
        default=None,
        description="Application logs around crash time",
    )
    additional_context: Optional[str] = Field(
        default=None,
        description="Any additional context about the crash",
    )
    priority: int = Field(default=5, ge=1, le=20)
    callback_url: Optional[str] = None


class EnvironmentTaskResponse(BaseModel):
    """Response for environment task submission"""
    task_id: str
    env_type: str
    status: str
    message: str
    workspace_path: Optional[str] = None


class EnvironmentTaskStatusResponse(BaseModel):
    """Detailed status response for environment tasks"""
    task_id: str
    env_type: str
    status: str
    workspace_path: Optional[str] = None
    step_results: Optional[List[Dict[str, Any]]] = None
    final_analysis: Optional[str] = None
    error: Optional[str] = None
    total_duration_seconds: Optional[float] = None


class EnvironmentInfoResponse(BaseModel):
    """Information about an available environment"""
    type: str
    name: str
    description: str
    required_inputs: List[str]


# Import Dict and Any for type hints
from typing import Dict, Any


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

# Mount static files for UI
UI_DIR = Path(__file__).parent.parent / "ui"
if UI_DIR.exists():
    app.mount("/static/css", StaticFiles(directory=UI_DIR / "css"), name="css")
    app.mount("/static/js", StaticFiles(directory=UI_DIR / "js"), name="js")
    logger.info(f"Serving static UI from {UI_DIR}")


@app.get("/", include_in_schema=False)
async def serve_ui():
    """Serve the web UI"""
    index_path = UI_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Claude Task Wrapper API", "docs": "/docs"}


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
        created_at = task.created_at.isoformat() if task.created_at else None

        if result:
            responses.append(TaskStatusResponse(
                task_id=task.task_id,
                status=result.status.value,
                prompt=task.prompt,
                created_at=created_at,
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
                prompt=task.prompt,
                created_at=created_at,
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


# ============================================================================
# Environment-based Task Endpoints
# ============================================================================

@app.get("/environments", response_model=List[EnvironmentInfoResponse])
async def list_environments():
    """
    List all available execution environments
    """
    from environments import create_default_registry

    registry = create_default_registry()
    return [
        EnvironmentInfoResponse(**env)
        for env in registry.list_environments()
    ]


@app.get("/environments/{env_type}", response_model=EnvironmentInfoResponse)
async def get_environment_info(env_type: str):
    """
    Get details about a specific environment
    """
    from environments import create_default_registry

    registry = create_default_registry()
    try:
        env_type_enum = EnvironmentType(env_type)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown environment type: {env_type}",
        )

    env = registry.get(env_type_enum)
    if not env:
        raise HTTPException(
            status_code=404,
            detail=f"Environment not found: {env_type}",
        )

    return EnvironmentInfoResponse(
        type=env.env_type.value,
        name=env.name,
        description=env.description,
        required_inputs=env.required_inputs,
    )


@app.post("/environments/{env_type}/tasks", response_model=EnvironmentTaskResponse)
async def submit_environment_task(env_type: str, request: EnvironmentTaskRequest):
    """
    Submit a task to a specific environment
    """
    from environments import create_default_registry

    registry = create_default_registry()

    try:
        env_type_enum = EnvironmentType(env_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown environment type: {env_type}",
        )

    env = registry.get(env_type_enum)
    if not env:
        raise HTTPException(
            status_code=404,
            detail=f"Environment not found: {env_type}",
        )

    # Validate inputs
    valid, errors = env.validate_inputs(request.inputs)
    if not valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid inputs: {'; '.join(errors)}",
        )

    # Create environment task
    env_task = EnvironmentTask(
        env_type=env_type_enum,
        inputs=request.inputs,
        additional_prompt=request.additional_prompt,
        priority=request.priority,
        callback_url=request.callback_url,
    )

    # Store task in Redis
    import json
    task_key = f"claude:env_tasks:{env_task.task_id}"
    await redis_client.hset(task_key, mapping={
        "data": json.dumps(env_task.to_dict()),
        "status": "queued",
    })

    # Add to environment task queue
    queue_key = "claude:env_tasks:queue"
    score = request.priority * 1e12 + env_task.created_at.timestamp()
    await redis_client.zadd(queue_key, {json.dumps(env_task.to_dict()): score})

    logger.info(f"Environment task {env_task.task_id} queued for {env_type}")

    return EnvironmentTaskResponse(
        task_id=env_task.task_id,
        env_type=env_type,
        status="queued",
        message=f"Task queued for {env.name} environment",
    )


@app.post("/environments/crash_analysis/tasks", response_model=EnvironmentTaskResponse)
async def submit_crash_analysis(request: CrashAnalysisRequest):
    """
    Convenience endpoint for crash analysis tasks
    """
    # Build inputs from the specific request
    inputs = {
        "repo_url": request.repo_url,
        "backtrace": request.backtrace,
    }
    if request.commit_hash:
        inputs["commit_hash"] = request.commit_hash
    if request.branch:
        inputs["branch"] = request.branch
    if request.logs:
        inputs["logs"] = request.logs

    # Create environment task request
    env_request = EnvironmentTaskRequest(
        env_type="crash_analysis",
        inputs=inputs,
        additional_prompt=request.additional_context,
        priority=request.priority,
        callback_url=request.callback_url,
    )

    return await submit_environment_task("crash_analysis", env_request)


@app.get(
    "/environments/{env_type}/tasks/{task_id}",
    response_model=EnvironmentTaskStatusResponse,
)
async def get_environment_task_status(env_type: str, task_id: str):
    """
    Get status and results of an environment task
    """
    import json

    # Get task from Redis
    task_key = f"claude:env_tasks:{task_id}"
    task_data = await redis_client.hgetall(task_key)

    if not task_data:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found",
        )

    status = task_data.get(b"status", b"unknown").decode()
    data = json.loads(task_data.get(b"data", b"{}").decode())

    # Get result if available
    result_key = f"claude:env_results:{task_id}"
    result_data = await redis_client.get(result_key)

    response = EnvironmentTaskStatusResponse(
        task_id=task_id,
        env_type=data.get("env_type", env_type),
        status=status,
    )

    if result_data:
        result = json.loads(result_data.decode())
        response.workspace_path = result.get("workspace_path")
        response.step_results = result.get("step_results")
        response.final_analysis = result.get("final_analysis")
        response.error = result.get("error")
        response.total_duration_seconds = result.get("total_duration_seconds")

    return response


@app.get("/environments/{env_type}/tasks", response_model=List[EnvironmentTaskStatusResponse])
async def list_environment_tasks(
    env_type: str,
    status: Optional[str] = None,
    limit: int = 50,
):
    """
    List tasks for a specific environment
    """
    import json

    # Scan for environment tasks
    cursor = 0
    tasks = []
    pattern = "claude:env_tasks:*"

    while len(tasks) < limit:
        cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)

        for key in keys:
            if key.endswith(b":queue"):
                continue

            task_data = await redis_client.hgetall(key)
            if not task_data:
                continue

            data = json.loads(task_data.get(b"data", b"{}").decode())
            task_status = task_data.get(b"status", b"unknown").decode()

            # Filter by env_type
            if data.get("env_type") != env_type:
                continue

            # Filter by status if specified
            if status and task_status != status:
                continue

            tasks.append(EnvironmentTaskStatusResponse(
                task_id=data.get("task_id", key.decode().split(":")[-1]),
                env_type=data.get("env_type", env_type),
                status=task_status,
            ))

            if len(tasks) >= limit:
                break

        if cursor == 0:
            break

    return tasks


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
