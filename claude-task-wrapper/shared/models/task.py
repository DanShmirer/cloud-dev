"""
Task and Result Data Transfer Objects (DTOs)
Following Single Responsibility Principle - each class handles one concern
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid


class TaskType(Enum):
    """Type of Claude Code task execution"""
    SINGLE = "single"           # One-shot prompt execution
    SESSION = "session"         # Multi-turn conversation with resume


class TaskStatus(Enum):
    """Task lifecycle states"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels for queue ordering"""
    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


@dataclass
class TaskConfig:
    """Configuration for Claude Code execution"""
    model: str = "sonnet"
    allowed_tools: List[str] = field(default_factory=lambda: ["Read", "Glob", "Grep"])
    working_dir: str = "/workspace"
    timeout_seconds: int = 300
    max_turns: int = 50
    output_format: str = "json"
    verbose: bool = False

    def to_cli_args(self) -> List[str]:
        """Convert config to Claude CLI arguments"""
        args = [
            "--model", self.model,
            "--output-format", self.output_format,
            "--max-turns", str(self.max_turns),
        ]
        if self.allowed_tools:
            args.extend(["--allowed-tools", ",".join(self.allowed_tools)])
        if self.verbose:
            args.append("--verbose")
        return args


@dataclass
class Task:
    """
    Represents a task to be executed by Claude Code
    Immutable after creation (dataclass frozen would enforce this)
    """
    prompt: str
    task_type: TaskType = TaskType.SINGLE
    config: TaskConfig = field(default_factory=TaskConfig)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    priority: TaskPriority = TaskPriority.NORMAL
    session_id: Optional[str] = None
    callback_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize task for queue storage"""
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "task_type": self.task_type.value,
            "config": {
                "model": self.config.model,
                "allowed_tools": self.config.allowed_tools,
                "working_dir": self.config.working_dir,
                "timeout_seconds": self.config.timeout_seconds,
                "max_turns": self.config.max_turns,
                "output_format": self.config.output_format,
                "verbose": self.config.verbose,
            },
            "priority": self.priority.value,
            "session_id": self.session_id,
            "callback_url": self.callback_url,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Deserialize task from queue storage"""
        config = TaskConfig(
            model=data["config"].get("model", "sonnet"),
            allowed_tools=data["config"].get("allowed_tools", []),
            working_dir=data["config"].get("working_dir", "/workspace"),
            timeout_seconds=data["config"].get("timeout_seconds", 300),
            max_turns=data["config"].get("max_turns", 50),
            output_format=data["config"].get("output_format", "json"),
            verbose=data["config"].get("verbose", False),
        )
        return cls(
            task_id=data["task_id"],
            prompt=data["prompt"],
            task_type=TaskType(data["task_type"]),
            config=config,
            priority=TaskPriority(data["priority"]),
            session_id=data.get("session_id"),
            callback_url=data.get("callback_url"),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class TaskResult:
    """
    Result of a Claude Code task execution
    Follows Single Responsibility - only handles result data
    """
    task_id: str
    status: TaskStatus
    output: Optional[str] = None
    error: Optional[str] = None
    session_id: Optional[str] = None  # For session continuation
    cost_usd: Optional[float] = None
    duration_seconds: Optional[float] = None
    raw_response: Optional[Dict[str, Any]] = None
    completed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result for storage"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "session_id": self.session_id,
            "cost_usd": self.cost_usd,
            "duration_seconds": self.duration_seconds,
            "raw_response": self.raw_response,
            "completed_at": self.completed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskResult":
        """Deserialize result from storage"""
        return cls(
            task_id=data["task_id"],
            status=TaskStatus(data["status"]),
            output=data.get("output"),
            error=data.get("error"),
            session_id=data.get("session_id"),
            cost_usd=data.get("cost_usd"),
            duration_seconds=data.get("duration_seconds"),
            raw_response=data.get("raw_response"),
            completed_at=datetime.fromisoformat(data["completed_at"]),
        )

    @classmethod
    def success(cls, task_id: str, output: str, **kwargs) -> "TaskResult":
        """Factory method for successful result"""
        return cls(task_id=task_id, status=TaskStatus.COMPLETED, output=output, **kwargs)

    @classmethod
    def failure(cls, task_id: str, error: str, **kwargs) -> "TaskResult":
        """Factory method for failed result"""
        return cls(task_id=task_id, status=TaskStatus.FAILED, error=error, **kwargs)
