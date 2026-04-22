"""Prometheus metrics for RateMeAI pipeline observability."""
from __future__ import annotations

import math

from prometheus_client import Counter, Gauge, Histogram

from src.config import settings

PIPELINE_DURATION = Histogram(
    "ratemeai_pipeline_duration_seconds",
    "End-to-end pipeline execution time",
    labelnames=["mode", "pipeline_type"],
    buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120),
)

# v1.20: renamed from ``REVE_CALLS`` / ``ratemeai_reve_calls_total``.
# The ``REVE_CALLS`` alias is preserved for one release to keep existing
# call sites (executor, advanced.execute_plan) importing the same symbol
# while Grafana / Prometheus configs migrate to the new metric name.
IMAGE_GEN_CALLS = Counter(
    "ratemeai_image_gen_calls_total",
    "Number of image-gen provider API calls (any backend)",
    labelnames=["mode", "step", "provider"],
)
REVE_CALLS = IMAGE_GEN_CALLS  # v1.20 alias, remove in v1.21

FAL_CALLS = Counter(
    "ratemeai_fal_calls_total",
    "Number of FAL.ai (FLUX) API calls",
    labelnames=["mode", "step", "model"],
)


def estimate_fal_flux2_cost_usd(width: int, height: int) -> float:
    """Compute per-image USD cost for ``fal-ai/flux-2-pro/edit``.

    FAL bills the first output megapixel at ``fal2_first_mp`` and every
    additional megapixel (rounded **up** to the next whole MP) at
    ``fal2_extra_mp``. The pricing page caps the model at 4 MP, but we
    don't clamp here — the provider rejects oversize requests anyway
    and we still want the metric to reflect what FAL will invoice.

    Example at defaults (0.03 + 0.015): 2 MP portrait ≈ $0.045,
    1 MP square (documents) = $0.030.
    """
    if width <= 0 or height <= 0:
        return settings.model_cost_fal_flux2_first_mp
    total_mp = (width * height) / 1_000_000.0
    rounded = max(1, math.ceil(total_mp))
    first = settings.model_cost_fal_flux2_first_mp
    extra = settings.model_cost_fal_flux2_extra_mp
    return round(first + max(0, rounded - 1) * extra, 4)


def estimate_image_gen_cost_usd(
    provider_name: str,
    *,
    image_size: dict | None = None,
) -> float:
    """Return the USD cost estimate for one image generation.

    Centralises the per-provider cost maths so the executor and any
    reporting surface produce consistent numbers. ``image_size`` is only
    consulted for FLUX.2 Pro Edit (everything else has flat pricing).
    """
    name = (provider_name or "").lower()
    if "falflux2" in name or "flux2" in name or "flux_2" in name:
        if image_size:
            return estimate_fal_flux2_cost_usd(
                int(image_size.get("width", 0) or 0),
                int(image_size.get("height", 0) or 0),
            )
        mp = max(1.0, float(settings.fal2_output_mp or 2.0))
        rounded = max(1, math.ceil(mp))
        first = settings.model_cost_fal_flux2_first_mp
        extra = settings.model_cost_fal_flux2_extra_mp
        return round(first + max(0, rounded - 1) * extra, 4)
    if "falflux" in name or name == "flux_kontext":
        return settings.model_cost_fal_flux
    if "replicate" in name:
        return settings.model_cost_replicate
    return settings.model_cost_reve

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

# Identity-match retry loop observability (v1.17). Fires once per task
# that triggered a retry. ``result`` is either ``success`` (retry lifted
# identity_match to or above the threshold) or ``still_fail`` (retry
# also came back below threshold). ``mode`` lets us segment retry quality
# per dating / cv / social / emoji.
IDENTITY_RETRY_TRIGGERED = Counter(
    "ratemeai_identity_retry_triggered_total",
    "Identity-match VLM retries by final outcome",
    labelnames=["mode", "result"],
)

# Number of image-gen attempts per task (1 = no retry, 2 = one retry, ...).
# Bucketed as discrete integers — we care about the rate of tasks that
# needed 2+ attempts, not any fine-grained distribution.
GENERATION_ATTEMPTS = Histogram(
    "ratemeai_generation_attempts",
    "Image-gen attempts per task before a result is accepted",
    labelnames=["mode"],
    buckets=(1, 2, 3, 4),
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

# ---------------------------------------------------------------------------
# v1.18 — hybrid image-gen pipeline observability
# ---------------------------------------------------------------------------

# Which backend actually served the request after StyleRouter routing.
# ``backend``: pulid | seedream | fallback.
# ``style_mode``: identity_scene | scene_preserve | unknown.
# Divergence between requested mode (derived from StyleSpec) and actual
# ``backend`` (e.g. a face-crop failure on identity_scene → fallback to
# seedream) is visible here.
IMAGE_GEN_BACKEND = Counter(
    "ratemeai_image_gen_backend_total",
    "Image-gen requests by chosen backend and requested style mode",
    labelnames=["backend", "style_mode"],
)

# Estimated per-image cost (USD) by backend. Primary budget signal for
# the v1.18 hybrid pipeline — canary rollout gates on the p95/mean of
# this histogram staying below $0.025.
GENERATION_COST_USD = Histogram(
    "ratemeai_generation_cost_usd",
    "Estimated USD cost per image generation by backend",
    labelnames=["backend"],
    buckets=(0.005, 0.010, 0.015, 0.020, 0.025, 0.030, 0.040, 0.060, 0.100),
)

# Face-crop failures that forced the router to fall back from
# identity_scene to scene_preserve. A climbing rate here indicates
# either degraded detector availability or a traffic shift toward
# photos without clear frontal faces.
PULID_FACE_CROP_FAILED = Counter(
    "ratemeai_pulid_face_crop_failed_total",
    "Face-crop failures on identity_scene requests (by reason)",
    labelnames=["reason"],
)

# Cases where the router swapped the requested generation_mode for
# another one (crop failure, provider missing, retry escalation).
# ``reason`` is a short code (face_crop_no_face, no_reference_image,
# provider_missing, retry_escalate, ...).
STYLE_MODE_OVERRIDE = Counter(
    "ratemeai_style_mode_override_total",
    "Router-initiated generation_mode overrides",
    labelnames=["from_mode", "to_mode", "reason"],
)
