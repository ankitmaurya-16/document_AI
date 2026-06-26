"""Prometheus metrics: HTTP histograms via prometheus-flask-exporter plus a few
business counters (ingestion duration, cache hits, credit burn, external
retries). No-ops if prometheus-client isn't installed.
"""
from __future__ import annotations

from logging_config import get_logger

log = get_logger("metrics")

class _NoopMetric:
    def labels(self, **_kw):
        return self
    def inc(self, _amount: float = 1.0) -> None: ...
    def observe(self, _value: float) -> None: ...
    def set(self, _value: float) -> None: ...


try:
    from prometheus_client import Counter, Histogram

    INGESTION_DURATION = Histogram(
        "docai_ingestion_duration_seconds",
        "Time to chunk + embed + index a single ingestion job.",
        buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
    )
    CACHE_HIT = Counter(
        "docai_cache_hit_total",
        "Cache hits, labelled by layer (exact|semantic).",
        ["layer"],
    )
    CACHE_MISS = Counter(
        "docai_cache_miss_total",
        "Cache misses, labelled by layer.",
        ["layer"],
    )
    CREDIT_BURN = Counter(
        "docai_credit_burn_total",
        "Credits charged, labelled by route (chat|chat_upload).",
        ["route"],
    )
    EXTERNAL_RETRY = Counter(
        "docai_external_retry_total",
        "Retry attempts against external services (openai|stripe|qdrant|s3).",
        ["service"],
    )
except ImportError:
    INGESTION_DURATION = _NoopMetric()
    CACHE_HIT = _NoopMetric()
    CACHE_MISS = _NoopMetric()
    CREDIT_BURN = _NoopMetric()
    EXTERNAL_RETRY = _NoopMetric()
    log.info("metrics.client_missing", hint="pip install prometheus-client")


def init_metrics(app) -> None:
    """Wire the Prometheus exporter onto the Flask app at ``/metrics`` (idempotent)."""
    if getattr(app, "_docai_metrics_inited", False):
        return
    try:
        from prometheus_flask_exporter import PrometheusMetrics
    except ImportError:
        log.info("metrics.exporter_missing", hint="pip install prometheus-flask-exporter")
        return
    exporter = PrometheusMetrics(app, group_by="endpoint")
    try:
        exporter.info("docai_app_info", "DocAI backend build info", version="dev")
    except ValueError:
        pass  # info metric already registered in this process
    app._docai_metrics_inited = True
    log.info("metrics.initialized", path="/metrics")
