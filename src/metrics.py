"""Prometheus metrics for RateMeAI pipeline observability."""
from __future__ import annotations

from prometheus_client import Counter, Histogram, Gauge

PIPELINE_DURATION = Histogram(
    "ratemeai_pipeline_duration_seconds",
    "End-to-end pipeline execution time",
    labelnames=["mode", "pipeline_type"],
    buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120),
)

REVE_CALLS = Counter(
    "ratemeai_reve_calls_total",
    "Number of Reve API calls",
    labelnames=["mode", "step", "provider"],
)

LLM_CALLS = Counter(
    "ratemeai_llm_calls_total",
    "Number of LLM API calls",
    labelnames=["purpose"],
)

IDENTITY_SCORE = Histogram(
    "ratemeai_identity_score",
    "Face identity similarity scores",
    buckets=(0.3, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0),
)

CREDITS_USED = Counter(
    "ratemeai_credits_used_total",
    "Total image credits consumed",
)

TASKS_COMPLETED = Counter(
    "ratemeai_tasks_completed_total",
    "Tasks that reached completed status",
    labelnames=["has_image"],
)

TASKS_FAILED = Counter(
    "ratemeai_tasks_failed_total",
    "Tasks that reached failed status",
    labelnames=["reason"],
)

TASKS_RECONCILED = Counter(
    "ratemeai_tasks_reconciled_total",
    "Tasks force-failed by the stuck-task reconciler",
)

PIPELINE_RETRIES = Counter(
    "ratemeai_pipeline_retries_total",
    "Transient pipeline errors that triggered a retry",
)

TASKS_IN_PROCESSING = Gauge(
    "ratemeai_tasks_in_processing",
    "Current number of tasks in processing state (updated by reconciler)",
)

COMPLETED_WITHOUT_IMAGE = Counter(
    "ratemeai_completed_without_image_total",
    "Tasks completed without a generated image",
    labelnames=["reason"],
)
