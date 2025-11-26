"""
OpenTelemetry Provider
Initializes and manages OpenTelemetry SDK components
"""
import logging
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
    ConsoleMetricExporter,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

# For HTTP protocol support
try:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter as OTLPSpanExporterHTTP,
    )
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter as OTLPMetricExporterHTTP,
    )
    HTTP_EXPORTERS_AVAILABLE = True
except ImportError:
    HTTP_EXPORTERS_AVAILABLE = False

from .config import TelemetryConfig, OTelProtocol, ExporterType, get_telemetry_config

logger = logging.getLogger(__name__)


class TelemetryProvider:
    """
    Manages OpenTelemetry SDK initialization and lifecycle.
    Provides centralized access to tracers and meters.
    """

    def __init__(self, config: Optional[TelemetryConfig] = None):
        self._config = config or get_telemetry_config()
        self._tracer_provider: Optional[TracerProvider] = None
        self._meter_provider: Optional[MeterProvider] = None
        self._initialized = False

    @property
    def config(self) -> TelemetryConfig:
        return self._config

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        """Initialize OpenTelemetry SDK with configured exporters"""
        if self._initialized:
            logger.warning("Telemetry already initialized, skipping")
            return

        # Create resource with service attributes
        resource = Resource.create(self._config.get_resource_attributes())

        # Initialize tracing
        if self._config.enable_traces:
            self._init_tracing(resource)

        # Initialize metrics
        if self._config.enable_metrics:
            self._init_metrics(resource)

        self._initialized = True
        logger.info(
            f"OpenTelemetry initialized for service '{self._config.service_name}' "
            f"in environment '{self._config.environment}'"
        )

    def _init_tracing(self, resource: Resource) -> None:
        """Initialize tracing with appropriate exporter"""
        sampler = TraceIdRatioBased(self._config.trace_sample_rate)

        self._tracer_provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # Add span processor based on exporter type
        if self._config.exporter_type == ExporterType.CONSOLE:
            processor = BatchSpanProcessor(ConsoleSpanExporter())
        elif self._config.exporter_type == ExporterType.OTLP:
            exporter = self._create_span_exporter()
            processor = BatchSpanProcessor(
                exporter,
                max_queue_size=self._config.batch_max_queue_size,
                max_export_batch_size=self._config.batch_max_export_batch_size,
                export_timeout_millis=self._config.batch_export_timeout_millis,
            )
        else:
            # No-op processor
            processor = None

        if processor:
            self._tracer_provider.add_span_processor(processor)

        # Set as global tracer provider
        trace.set_tracer_provider(self._tracer_provider)
        logger.info(f"Tracing initialized with {self._config.exporter_type.value} exporter")

    def _init_metrics(self, resource: Resource) -> None:
        """Initialize metrics with appropriate exporter"""
        if self._config.exporter_type == ExporterType.CONSOLE:
            reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
        elif self._config.exporter_type == ExporterType.OTLP:
            exporter = self._create_metric_exporter()
            reader = PeriodicExportingMetricReader(
                exporter,
                export_interval_millis=60000,  # 1 minute
            )
        else:
            reader = None

        if reader:
            self._meter_provider = MeterProvider(
                resource=resource,
                metric_readers=[reader],
            )
            metrics.set_meter_provider(self._meter_provider)
            logger.info(f"Metrics initialized with {self._config.exporter_type.value} exporter")

    def _create_span_exporter(self):
        """Create span exporter based on protocol"""
        if self._config.otlp_protocol == OTelProtocol.GRPC:
            return OTLPSpanExporter(
                endpoint=self._config.otlp_endpoint,
                headers=self._config.otlp_headers or None,
            )
        elif HTTP_EXPORTERS_AVAILABLE:
            # HTTP protocol
            endpoint = self._config.otlp_endpoint
            if not endpoint.endswith("/v1/traces"):
                endpoint = f"{endpoint}/v1/traces"
            return OTLPSpanExporterHTTP(
                endpoint=endpoint,
                headers=self._config.otlp_headers or None,
            )
        else:
            logger.warning("HTTP exporters not available, falling back to gRPC")
            return OTLPSpanExporter(
                endpoint=self._config.otlp_endpoint,
                headers=self._config.otlp_headers or None,
            )

    def _create_metric_exporter(self):
        """Create metric exporter based on protocol"""
        if self._config.otlp_protocol == OTelProtocol.GRPC:
            return OTLPMetricExporter(
                endpoint=self._config.otlp_endpoint,
                headers=self._config.otlp_headers or None,
            )
        elif HTTP_EXPORTERS_AVAILABLE:
            endpoint = self._config.otlp_endpoint
            if not endpoint.endswith("/v1/metrics"):
                endpoint = f"{endpoint}/v1/metrics"
            return OTLPMetricExporterHTTP(
                endpoint=endpoint,
                headers=self._config.otlp_headers or None,
            )
        else:
            logger.warning("HTTP exporters not available, falling back to gRPC")
            return OTLPMetricExporter(
                endpoint=self._config.otlp_endpoint,
                headers=self._config.otlp_headers or None,
            )

    def get_tracer(self, name: str) -> trace.Tracer:
        """Get a tracer instance"""
        if not self._initialized:
            self.initialize()
        return trace.get_tracer(name, self._config.service_version)

    def get_meter(self, name: str) -> metrics.Meter:
        """Get a meter instance"""
        if not self._initialized:
            self.initialize()
        return metrics.get_meter(name, self._config.service_version)

    def shutdown(self) -> None:
        """Shutdown telemetry providers gracefully"""
        if self._tracer_provider:
            self._tracer_provider.shutdown()

        if self._meter_provider:
            self._meter_provider.shutdown()

        self._initialized = False
        logger.info("OpenTelemetry shutdown complete")


# Singleton provider
_provider: Optional[TelemetryProvider] = None


def get_telemetry_provider() -> TelemetryProvider:
    """Get or create the telemetry provider singleton"""
    global _provider
    if _provider is None:
        _provider = TelemetryProvider()
    return _provider


def set_telemetry_provider(provider: TelemetryProvider) -> None:
    """Override telemetry provider (for testing)"""
    global _provider
    _provider = provider
