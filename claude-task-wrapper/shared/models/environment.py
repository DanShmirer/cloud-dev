"""
Environment Models - DTOs for environment-based task execution
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid


class EnvironmentType(Enum):
    """Available environment types"""
    CRASH_ANALYSIS = "crash_analysis"
    CODE_REVIEW = "code_review"
    REFACTORING = "refactoring"
    CUSTOM = "custom"


class WorkflowStepStatus(Enum):
    """Status of a workflow step"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class HookConfig:
    """Configuration for environment hooks"""
    pre_clone: Optional[str] = None       # Script to run before cloning
    post_clone: Optional[str] = None      # Script to run after cloning
    pre_analysis: Optional[str] = None    # Script to run before Claude analysis
    post_analysis: Optional[str] = None   # Script to run after Claude analysis
    on_error: Optional[str] = None        # Script to run on error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pre_clone": self.pre_clone,
            "post_clone": self.post_clone,
            "pre_analysis": self.pre_analysis,
            "post_analysis": self.post_analysis,
            "on_error": self.on_error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HookConfig":
        return cls(**{k: v for k, v in data.items() if v is not None})


@dataclass
class SubAgentConfig:
    """Configuration for sub-agents within an environment"""
    name: str
    prompt_template: str
    model: str = "sonnet"
    allowed_tools: List[str] = field(default_factory=list)
    max_turns: int = 20

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "prompt_template": self.prompt_template,
            "model": self.model,
            "allowed_tools": self.allowed_tools,
            "max_turns": self.max_turns,
        }


@dataclass
class WorkflowStep:
    """A single step in an environment workflow"""
    name: str
    description: str
    step_type: str  # "shell", "claude", "subagent"
    command: Optional[str] = None  # For shell steps
    prompt_template: Optional[str] = None  # For claude steps
    subagent: Optional[str] = None  # For subagent steps
    continue_on_error: bool = False
    timeout_seconds: int = 300

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "step_type": self.step_type,
            "command": self.command,
            "prompt_template": self.prompt_template,
            "subagent": self.subagent,
            "continue_on_error": self.continue_on_error,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class WorkflowStepResult:
    """Result of executing a workflow step"""
    step_name: str
    status: WorkflowStepStatus
    output: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_name": self.step_name,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class EnvironmentConfig:
    """Configuration for an environment"""
    env_type: EnvironmentType
    name: str
    description: str
    claude_md_path: str  # Path to CLAUDE.md template
    workflow_steps: List[WorkflowStep] = field(default_factory=list)
    hooks: HookConfig = field(default_factory=HookConfig)
    subagents: List[SubAgentConfig] = field(default_factory=list)
    default_model: str = "sonnet"
    default_allowed_tools: List[str] = field(default_factory=lambda: [
        "Read", "Glob", "Grep", "Bash", "Edit", "Write"
    ])
    required_inputs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "env_type": self.env_type.value,
            "name": self.name,
            "description": self.description,
            "claude_md_path": self.claude_md_path,
            "workflow_steps": [s.to_dict() for s in self.workflow_steps],
            "hooks": self.hooks.to_dict(),
            "subagents": [s.to_dict() for s in self.subagents],
            "default_model": self.default_model,
            "default_allowed_tools": self.default_allowed_tools,
            "required_inputs": self.required_inputs,
        }


@dataclass
class EnvironmentTask:
    """A task to be executed within an environment"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    env_type: EnvironmentType = EnvironmentType.CRASH_ANALYSIS
    inputs: Dict[str, Any] = field(default_factory=dict)
    additional_prompt: Optional[str] = None
    priority: int = 5
    callback_url: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "env_type": self.env_type.value,
            "inputs": self.inputs,
            "additional_prompt": self.additional_prompt,
            "priority": self.priority,
            "callback_url": self.callback_url,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnvironmentTask":
        return cls(
            task_id=data["task_id"],
            env_type=EnvironmentType(data["env_type"]),
            inputs=data.get("inputs", {}),
            additional_prompt=data.get("additional_prompt"),
            priority=data.get("priority", 5),
            callback_url=data.get("callback_url"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class EnvironmentTaskResult:
    """Result of an environment task execution"""
    task_id: str
    env_type: EnvironmentType
    status: str  # "completed", "failed", "partial"
    workspace_path: str
    step_results: List[WorkflowStepResult] = field(default_factory=list)
    final_analysis: Optional[str] = None
    error: Optional[str] = None
    total_duration_seconds: float = 0.0
    total_cost_usd: float = 0.0
    completed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "env_type": self.env_type.value,
            "status": self.status,
            "workspace_path": self.workspace_path,
            "step_results": [s.to_dict() for s in self.step_results],
            "final_analysis": self.final_analysis,
            "error": self.error,
            "total_duration_seconds": self.total_duration_seconds,
            "total_cost_usd": self.total_cost_usd,
            "completed_at": self.completed_at.isoformat(),
        }
