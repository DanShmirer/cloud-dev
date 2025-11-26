"""
OpenTelemetry Configuration
Centralized configuration for all telemetry settings
"""
import os
from dataclasses import dataclass, field
from typing import Optional, Dict
from enum import Enum


class OTelProtocol(Enum):
    """OTLP export protocol options"""
    GRPC = "grpc"
    HTTP_PROTOBUF = "http/protobuf"
    HTTP_JSON = "http/json"


class ExporterType(Enum):
    """Exporter backend type"""
    OTLP = "otlp"
    CONSOLE = "console"
    NONE = "none"


@dataclass(frozen=True)
class TelemetryConfig:
    """
    OpenTelemetry configuration
    Loaded from environment variables with sensible defaults
    """
    # Service identification
    service_name: str = "claude-task-wrapper"
    service_version: str = "1.0.0"
    environment: str = "development"

    # OTLP Exporter settings
    otlp_endpoint: str = "http://otel-collector:4317"
    otlp_protocol: OTelProtocol = OTelProtocol.GRPC
    otlp_headers: Dict[str, str] = field(default_factory=dict)

    # Exporter type (otlp, console, none)
    exporter_type: ExporterType = ExporterType.OTLP

    # Sampling
    trace_sample_rate: float = 1.0  # 1.0 = 100% sampling

    # Resource attributes
    resource_attributes: Dict[str, str] = field(default_factory=dict)

    # Feature flags
    enable_traces: bool = True
    enable_metrics: bool = True
    enable_logs: bool = True

    # Claude Code specific
    claude_telemetry_enabled: bool = True

    # Batch settings
    batch_max_queue_size: int = 2048
    batch_max_export_batch_size: int = 512
    batch_export_timeout_millis: int = 30000

    @classmethod
    def from_env(cls) -> "TelemetryConfig":
        """Load configuration from environment variables"""
        # Parse OTLP headers from comma-separated key=value pairs
        headers_str = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers = {}
        if headers_str:
            for pair in headers_str.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    headers[key.strip()] = value.strip()

        # Parse resource attributes
        attrs_str = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
        resource_attrs = {}
        if attrs_str:
            for pair in attrs_str.split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    resource_attrs[key.strip()] = value.strip()

        # Determine protocol
        protocol_str = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
        try:
            protocol = OTelProtocol(protocol_str)
        except ValueError:
            protocol = OTelProtocol.GRPC

        # Determine exporter type
        exporter_str = os.getenv("OTEL_EXPORTER_TYPE", "otlp")
        try:
            exporter = ExporterType(exporter_str)
        except ValueError:
            exporter = ExporterType.OTLP

        return cls(
            service_name=os.getenv("OTEL_SERVICE_NAME", "claude-task-wrapper"),
            service_version=os.getenv("OTEL_SERVICE_VERSION", "1.0.0"),
            environment=os.getenv("OTEL_ENVIRONMENT", "development"),
            otlp_endpoint=os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT",
                "http://otel-collector:4317"
            ),
            otlp_protocol=protocol,
            otlp_headers=headers,
            exporter_type=exporter,
            trace_sample_rate=float(os.getenv("OTEL_TRACE_SAMPLE_RATE", "1.0")),
            resource_attributes=resource_attrs,
            enable_traces=os.getenv("OTEL_TRACES_ENABLED", "true").lower() == "true",
            enable_metrics=os.getenv("OTEL_METRICS_ENABLED", "true").lower() == "true",
            enable_logs=os.getenv("OTEL_LOGS_ENABLED", "true").lower() == "true",
            claude_telemetry_enabled=os.getenv(
                "CLAUDE_CODE_ENABLE_TELEMETRY", "1"
            ) == "1",
            batch_max_queue_size=int(os.getenv("OTEL_BSP_MAX_QUEUE_SIZE", "2048")),
            batch_max_export_batch_size=int(
                os.getenv("OTEL_BSP_MAX_EXPORT_BATCH_SIZE", "512")
            ),
            batch_export_timeout_millis=int(
                os.getenv("OTEL_BSP_EXPORT_TIMEOUT", "30000")
            ),
        )

    def get_resource_attributes(self) -> Dict[str, str]:
        """Get all resource attributes including defaults"""
        attrs = {
            "service.name": self.service_name,
            "service.version": self.service_version,
            "deployment.environment": self.environment,
        }
        attrs.update(self.resource_attributes)
        return attrs

    def to_env_dict(self) -> Dict[str, str]:
        """Convert config to environment variables dictionary"""
        env = {
            "OTEL_SERVICE_NAME": self.service_name,
            "OTEL_EXPORTER_OTLP_ENDPOINT": self.otlp_endpoint,
            "OTEL_EXPORTER_OTLP_PROTOCOL": self.otlp_protocol.value,
        }

        if self.otlp_headers:
            headers_str = ",".join(f"{k}={v}" for k, v in self.otlp_headers.items())
            env["OTEL_EXPORTER_OTLP_HEADERS"] = headers_str

        resource_attrs = self.get_resource_attributes()
        if resource_attrs:
            attrs_str = ",".join(f"{k}={v}" for k, v in resource_attrs.items())
            env["OTEL_RESOURCE_ATTRIBUTES"] = attrs_str

        if self.claude_telemetry_enabled:
            env["CLAUDE_CODE_ENABLE_TELEMETRY"] = "1"

        return env


# Singleton configuration
_config: Optional[TelemetryConfig] = None


def get_telemetry_config() -> TelemetryConfig:
    """Get or create telemetry configuration"""
    global _config
    if _config is None:
        _config = TelemetryConfig.from_env()
    return _config


def set_telemetry_config(config: TelemetryConfig) -> None:
    """Override telemetry configuration (for testing)"""
    global _config
    _config = config
