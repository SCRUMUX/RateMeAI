"""Prometheus metrics for RateMeAI pipeline observability."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

PIPELINE_DURATION = Histogram(
    "ratemeai_pipeline_duration_seconds",
    "End-to-end pipeline execution time",
    labelnames=["mode", "pipeline_type"],
    buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120),
)

REVE_CALLS = Counter(
    "ratemeai_reve_calls_total",
    "Number of Reve API calls",
    labelnames=["mode", "step"],
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
