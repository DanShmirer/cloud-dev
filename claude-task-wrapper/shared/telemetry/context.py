"""
Telemetry Context Management
Provides context propagation for task-related telemetry
"""
import contextvars
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime

from opentelemetry import trace
from opentelemetry.trace import SpanContext
from opentelemetry.propagate import extract, inject


# Context variable for current task
_current_task_context: contextvars.ContextVar[Optional["TaskTelemetryContext"]] = \
    contextvars.ContextVar("current_task_context", default=None)


@dataclass
class TaskTelemetryContext:
    """
    Context object containing telemetry information for a task.
    Used to propagate context through async operations.
    """
    task_id: str
    task_type: str
    started_at: datetime = field(default_factory=datetime.utcnow)

    # Optional identifiers
    session_id: Optional[str] = None
    repo_name: Optional[str] = None
    developer_id: Optional[str] = None
    environment_type: Optional[str] = None

    # Trace context for propagation
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    trace_parent: Optional[str] = None

    # Execution metrics
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0

    # Additional attributes
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_span_attributes(self) -> Dict[str, Any]:
        """Convert context to span attributes"""
        attrs = {
            "task.id": self.task_id,
            "task.type": self.task_type,
        }

        if self.session_id:
            attrs["session.id"] = self.session_id
        if self.repo_name:
            attrs["repo.name"] = self.repo_name
        if self.developer_id:
            attrs["developer.id"] = self.developer_id
        if self.environment_type:
            attrs["environment.type"] = self.environment_type
        if self.model:
            attrs["claude.model"] = self.model
        if self.input_tokens > 0:
            attrs["claude.input_tokens"] = self.input_tokens
        if self.output_tokens > 0:
            attrs["claude.output_tokens"] = self.output_tokens
        if self.total_cost_usd > 0:
            attrs["claude.cost_usd"] = self.total_cost_usd

        attrs.update(self.attributes)
        return attrs

    def to_hook_env(self) -> Dict[str, str]:
        """Convert context to environment variables for hooks"""
        env = {
            "OTEL_TASK_ID": self.task_id,
            "OTEL_TASK_TYPE": self.task_type,
        }

        if self.trace_id:
            env["OTEL_TRACE_ID"] = self.trace_id
        if self.span_id:
            env["OTEL_SPAN_ID"] = self.span_id
        if self.trace_parent:
            env["TRACEPARENT"] = self.trace_parent
        if self.session_id:
            env["OTEL_SESSION_ID"] = self.session_id
        if self.repo_name:
            env["OTEL_REPO_NAME"] = self.repo_name
        if self.developer_id:
            env["OTEL_DEVELOPER_ID"] = self.developer_id

        return env

    def update_from_span(self, span: trace.Span) -> None:
        """Update context with current span information"""
        ctx = span.get_span_context()
        if ctx.is_valid:
            self.trace_id = format(ctx.trace_id, '032x')
            self.span_id = format(ctx.span_id, '016x')
            # Create W3C Trace Context traceparent
            self.trace_parent = f"00-{self.trace_id}-{self.span_id}-01"

    def add_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        """Add token counts"""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def add_cost(self, cost_usd: float) -> None:
        """Add cost"""
        self.total_cost_usd += cost_usd


def create_task_context(
    task_id: str,
    task_type: str,
    **kwargs,
) -> TaskTelemetryContext:
    """
    Create a new task telemetry context and set it as current.

    Args:
        task_id: Unique task identifier
        task_type: Type of task (single, session, environment, etc.)
        **kwargs: Additional context attributes

    Returns:
        Created TaskTelemetryContext
    """
    context = TaskTelemetryContext(
        task_id=task_id,
        task_type=task_type,
        **kwargs,
    )
    _current_task_context.set(context)
    return context


def get_current_task_context() -> Optional[TaskTelemetryContext]:
    """Get the current task telemetry context"""
    return _current_task_context.get()


def clear_task_context() -> None:
    """Clear the current task context"""
    _current_task_context.set(None)


class TaskContextManager:
    """
    Context manager for task telemetry context.

    Usage:
        with TaskContextManager(task_id, task_type) as ctx:
            # ctx is automatically set as current
            do_work()
    """

    def __init__(self, task_id: str, task_type: str, **kwargs):
        self._context = TaskTelemetryContext(
            task_id=task_id,
            task_type=task_type,
            **kwargs,
        )
        self._token = None

    def __enter__(self) -> TaskTelemetryContext:
        self._token = _current_task_context.set(self._context)
        return self._context

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token:
            _current_task_context.reset(self._token)
        return False


def inject_context(carrier: Dict[str, str]) -> None:
    """Inject current trace context into carrier for propagation"""
    inject(carrier)


def extract_context(carrier: Dict[str, str]):
    """Extract trace context from carrier"""
    return extract(carrier)
