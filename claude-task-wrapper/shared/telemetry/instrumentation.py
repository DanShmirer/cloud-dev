"""
OpenTelemetry Instrumentation Helpers
Provides convenient decorators and functions for instrumenting code
"""
import logging
import functools
from typing import Optional, Dict, Any, Callable
from contextlib import contextmanager

from opentelemetry import trace, metrics
from opentelemetry.trace import Span, Status, StatusCode
from opentelemetry.semconv.trace import SpanAttributes

from .provider import get_telemetry_provider

logger = logging.getLogger(__name__)


def get_tracer(name: str = "claude-task-wrapper") -> trace.Tracer:
    """Get a tracer instance"""
    return get_telemetry_provider().get_tracer(name)


def get_meter(name: str = "claude-task-wrapper") -> metrics.Meter:
    """Get a meter instance"""
    return get_telemetry_provider().get_meter(name)


@contextmanager
def create_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    tracer_name: str = "claude-task-wrapper",
):
    """
    Context manager for creating spans with automatic error handling.

    Usage:
        with create_span("my_operation", {"key": "value"}) as span:
            # do work
            span.set_attribute("result", "success")
    """
    tracer = get_tracer(tracer_name)

    with tracer.start_as_current_span(
        name,
        kind=kind,
        attributes=attributes or {},
    ) as span:
        try:
            yield span
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def traced(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
):
    """
    Decorator for tracing functions.

    Usage:
        @traced("my_function")
        async def my_function(arg1, arg2):
            ...
    """
    def decorator(func: Callable):
        span_name = name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            with create_span(span_name, attributes, kind) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with create_span(span_name, attributes, kind) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Import asyncio for function type checking
import asyncio


def record_metric(
    metric_name: str,
    value: float,
    attributes: Optional[Dict[str, str]] = None,
    metric_type: str = "counter",
    unit: str = "",
    description: str = "",
) -> None:
    """
    Record a metric value.

    Args:
        metric_name: Name of the metric
        value: Metric value
        attributes: Labels/attributes for the metric
        metric_type: Type of metric (counter, gauge, histogram)
        unit: Unit of measurement
        description: Metric description
    """
    meter = get_meter()

    if metric_type == "counter":
        counter = meter.create_counter(
            metric_name,
            unit=unit,
            description=description,
        )
        counter.add(int(value), attributes or {})
    elif metric_type == "gauge":
        # OpenTelemetry uses ObservableGauge, store value for callback
        _gauge_values[metric_name] = (value, attributes or {})
    elif metric_type == "histogram":
        histogram = meter.create_histogram(
            metric_name,
            unit=unit,
            description=description,
        )
        histogram.record(value, attributes or {})


# Store for gauge values
_gauge_values: Dict[str, tuple] = {}


def instrument_fastapi(app) -> None:
    """
    Instrument FastAPI application with OpenTelemetry.

    Adds automatic tracing for all HTTP endpoints.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # Initialize provider first
        provider = get_telemetry_provider()
        if not provider.is_initialized:
            provider.initialize()

        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumentation enabled")
    except ImportError:
        logger.warning(
            "FastAPI instrumentation not available. "
            "Install opentelemetry-instrumentation-fastapi"
        )
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}")


def instrument_redis(redis_client) -> None:
    """
    Instrument Redis client with OpenTelemetry.

    Adds automatic tracing for Redis operations.
    """
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        # Initialize provider first
        provider = get_telemetry_provider()
        if not provider.is_initialized:
            provider.initialize()

        RedisInstrumentor().instrument()
        logger.info("Redis instrumentation enabled")
    except ImportError:
        logger.warning(
            "Redis instrumentation not available. "
            "Install opentelemetry-instrumentation-redis"
        )
    except Exception as e:
        logger.error(f"Failed to instrument Redis: {e}")


def instrument_httpx() -> None:
    """
    Instrument HTTPX client with OpenTelemetry.
    """
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        provider = get_telemetry_provider()
        if not provider.is_initialized:
            provider.initialize()

        HTTPXClientInstrumentor().instrument()
        logger.info("HTTPX instrumentation enabled")
    except ImportError:
        logger.warning(
            "HTTPX instrumentation not available. "
            "Install opentelemetry-instrumentation-httpx"
        )
    except Exception as e:
        logger.error(f"Failed to instrument HTTPX: {e}")


# Task-specific metrics
class TaskMetrics:
    """
    Helper class for recording task-related metrics
    """

    def __init__(self):
        self._meter = None
        self._task_counter = None
        self._task_duration = None
        self._task_errors = None
        self._queue_length = None

    def _ensure_initialized(self):
        if self._meter is None:
            self._meter = get_meter("claude-task-wrapper.tasks")

            self._task_counter = self._meter.create_counter(
                "claude.tasks.total",
                unit="1",
                description="Total number of tasks processed",
            )

            self._task_duration = self._meter.create_histogram(
                "claude.tasks.duration",
                unit="s",
                description="Task execution duration in seconds",
            )

            self._task_errors = self._meter.create_counter(
                "claude.tasks.errors",
                unit="1",
                description="Total number of task errors",
            )

    def record_task_started(
        self,
        task_id: str,
        task_type: str,
        handler_name: str,
    ) -> None:
        """Record that a task has started"""
        self._ensure_initialized()
        self._task_counter.add(1, {
            "task.type": task_type,
            "handler.name": handler_name,
            "task.status": "started",
        })

    def record_task_completed(
        self,
        task_id: str,
        task_type: str,
        handler_name: str,
        duration_seconds: float,
        success: bool,
    ) -> None:
        """Record task completion metrics"""
        self._ensure_initialized()

        status = "success" if success else "failed"
        attrs = {
            "task.type": task_type,
            "handler.name": handler_name,
            "task.status": status,
        }

        self._task_counter.add(1, {**attrs, "task.status": "completed"})
        self._task_duration.record(duration_seconds, attrs)

        if not success:
            self._task_errors.add(1, attrs)


# Singleton metrics instance
_task_metrics: Optional[TaskMetrics] = None


def get_task_metrics() -> TaskMetrics:
    """Get or create task metrics instance"""
    global _task_metrics
    if _task_metrics is None:
        _task_metrics = TaskMetrics()
    return _task_metrics
