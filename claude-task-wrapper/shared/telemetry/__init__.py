"""
OpenTelemetry Telemetry Module
Provides unified instrumentation for metrics, traces, and logs
"""
from .config import TelemetryConfig, get_telemetry_config
from .provider import TelemetryProvider, get_telemetry_provider
from .instrumentation import (
    instrument_fastapi,
    instrument_redis,
    create_span,
    record_metric,
    get_tracer,
    get_meter,
)
from .context import (
    TaskTelemetryContext,
    create_task_context,
    get_current_task_context,
)

__all__ = [
    # Configuration
    "TelemetryConfig",
    "get_telemetry_config",
    # Provider
    "TelemetryProvider",
    "get_telemetry_provider",
    # Instrumentation
    "instrument_fastapi",
    "instrument_redis",
    "create_span",
    "record_metric",
    "get_tracer",
    "get_meter",
    # Context
    "TaskTelemetryContext",
    "create_task_context",
    "get_current_task_context",
]
