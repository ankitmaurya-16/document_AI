"""OpenTelemetry tracing. Active only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set;
otherwise a no-op. Auto-instruments Flask, requests, pymongo, and redis.
"""
from __future__ import annotations

import os

from logging_config import get_logger

log = get_logger("telemetry")

_initialized = False


def init_tracing(service_name: str = "docai-backend") -> None:
    """Idempotently configure OpenTelemetry. Safe to call multiple times."""
    global _initialized
    if _initialized:
        return

    endpoint = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    if not endpoint:
        log.info("telemetry.disabled", reason="no_endpoint")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.warning(
            "telemetry.missing_dependency",
            hint="pip install opentelemetry-distro opentelemetry-exporter-otlp",
        )
        return

    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "docai",
        "deployment.environment": os.getenv("APP_ENV", "development"),
    })
    provider = TracerProvider(resource=resource)

    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces"))
    )
    trace.set_tracer_provider(provider)

    _instrument_libraries()
    _initialized = True
    log.info("telemetry.initialized", endpoint=endpoint, service=service_name)


def instrument_flask(app) -> None:
    """Add request-level spans for the Flask app. Called from the factory."""
    if not _initialized:
        return
    try:
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        FlaskInstrumentor().instrument_app(app)
    except ImportError:
        log.warning("telemetry.flask_instrumentation_missing")


def _instrument_libraries() -> None:
    """Best-effort auto-instrumentation of common outbound integrations."""
    integrations = [
        ("opentelemetry.instrumentation.requests", "RequestsInstrumentor"),
        ("opentelemetry.instrumentation.pymongo", "PymongoInstrumentor"),
        ("opentelemetry.instrumentation.redis", "RedisInstrumentor"),
    ]
    for module_path, cls_name in integrations:
        try:
            module = __import__(module_path, fromlist=[cls_name])
            getattr(module, cls_name)().instrument()
        except Exception as e:
            log.debug("telemetry.skipped_library", lib=module_path, error=str(e))
