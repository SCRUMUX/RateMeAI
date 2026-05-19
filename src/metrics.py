"""Prometheus metrics for RateMeAI pipeline observability."""

from __future__ import annotations


from prometheus_client import Counter, Gauge, Histogram

from src.config import settings

PIPELINE_DURATION = Histogram(
    "ratemeai_pipeline_duration_seconds",
    "End-to-end pipeline execution time",
    labelnames=["mode", "pipeline_type"],
    buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120),
)

# v1.20: renamed from ``REVE_CALLS`` / ``ratemeai_reve_calls_total``.
# v1.64: with the Reve provider retired the legacy alias is no longer
# used; the metric stays under its current name.
IMAGE_GEN_CALLS = Counter(
    "ratemeai_image_gen_calls_total",
    "Number of image-gen provider API calls (any backend)",
    labelnames=["mode", "step", "provider"],
)

FAL_CALLS = Counter(
    "ratemeai_fal_calls_total",
    "Number of FAL.ai (FLUX) API calls",
    labelnames=["mode", "step", "model"],
)

# 1.32.0 — v1 ``_build_mode_prompt`` fallback hits. Should be 0 in
# production (every supported style is registered as v2/v3). Non-zero
# means a style is missing from the v2/v3 registry OR the v2 builder
# threw and we silently fell back to legacy variation logic. Used to
# decide whether the v1 fallback can be removed in 1.33.1.
PROMPT_V1_FALLBACK = Counter(
    "ratemeai_prompt_v1_fallback_total",
    "Number of times the v1 _build_mode_prompt fallback was hit "
    "(post-v2 cutover this should be 0)",
    labelnames=["mode", "style"],
)


def estimate_image_gen_cost_usd(
    provider_name: str,
    *,
    image_size: dict | None = None,
) -> float:
    """Return the USD cost estimate for one image generation.

    Centralises the per-provider cost maths so the executor and any
    reporting surface produce consistent numbers.

    v1.64: with PuLID / Seedream / Reve retired the unified provider
    always lands on GPT Image 2 or Nano Banana 2; the per-quality
    table in ``_AB_COST_FIELDS`` is the source of truth — this helper
    only handles the legacy ``provider_name``-only signature still
    used in a few non-A/B code paths and conservatively returns the
    GPT-2 medium price.
    """
    name = (provider_name or "").lower()
    if "fal" in name and "nano" in name:
        return float(getattr(settings, "model_cost_nano_banana_2", 0.02))
    # Default (unified / gpt_image_2 / unknown) — GPT-2 medium.
    return float(getattr(settings, "model_cost_gpt_image_2_medium", 0.06))


# v1.21 A/B cost table — keyed by (model, quality). Consulted by the
# executor when ``context["image_model"]`` is set (additive A/B path).
_AB_COST_FIELDS: dict[str, dict[str, str]] = {
    "nano_banana_2": {
        "low": "model_cost_fal_nano_banana_low",
        "medium": "model_cost_fal_nano_banana_medium",
        "high": "model_cost_fal_nano_banana_high",
    },
    "gpt_image_2": {
        "low": "model_cost_gpt_image_2_low",
        "medium": "model_cost_gpt_image_2_medium",
        "high": "model_cost_gpt_image_2_high",
    },
}


def estimate_ab_image_gen_cost_usd(
    model_key: str,
    quality: str | None = None,
) -> float:
    """USD cost estimate for an A/B-path generation call.

    ``model_key`` is one of ``"nano_banana_2"`` / ``"gpt_image_2"``.
    ``quality`` is ``"low"`` / ``"medium"`` / ``"high"``. Unknown values
    collapse to the medium tier so the histogram always records a real
    number.
    """
    key = (model_key or "").strip().lower()
    q = (quality or "medium").strip().lower()
    tier_map = _AB_COST_FIELDS.get(key)
    if not tier_map:
        return 0.0
    field = tier_map.get(q) or tier_map["medium"]
    return float(getattr(settings, field, 0.0) or 0.0)


def ab_backend_label(
    model_key: str,
    quality: str | None = None,
) -> str:
    """Format a single Prometheus label value encoding model+quality.

    Keeps existing metrics (``IMAGE_GEN_CALLS.provider``,
    ``GENERATION_COST_USD.backend``) backwards-compatible: we do not
    add a new label dimension, we just use a distinctive value like
    ``"nano_banana_2:medium"``.
    """
    return f"{(model_key or 'unknown').strip().lower()}:{(quality or 'medium').strip().lower()}"


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
# Image-gen pipeline observability (v1.64 — FAL edit-only)
# ---------------------------------------------------------------------------

# Which backend actually served the request. ``backend`` is one of:
#   * ``gpt_image_2``     — FAL GPT Image 2 Edit (default)
#   * ``nano_banana_2``   — FAL Nano Banana 2 Edit (A/B alternative)
#
# v1.64: the ``style_mode`` label and the legacy ``pulid``/``seedream``/
# ``fallback`` backend values were removed when the StyleRouter and
# specialised providers were retired.
IMAGE_GEN_BACKEND = Counter(
    "ratemeai_image_gen_backend_total",
    "Image-gen requests by chosen backend",
    labelnames=["backend"],
)

# Estimated per-image cost (USD) by backend. Primary budget signal.
GENERATION_COST_USD = Histogram(
    "ratemeai_generation_cost_usd",
    "Estimated USD cost per image generation by backend",
    labelnames=["backend"],
    buckets=(0.005, 0.010, 0.015, 0.020, 0.025, 0.030, 0.040, 0.060, 0.100),
)


# ---------------------------------------------------------------------------
# Composition Safety Layer (CSL) — see src/services/composition_safety.py.
# ---------------------------------------------------------------------------

# Per-classification counter. ``source`` is ``heuristic`` (Phase 1
# face-bbox classifier) or ``pose`` (Phase 2 MediaPipe Pose, behind
# ``settings.body_landmarks_enabled``). Skewed source distribution
# (e.g. heuristic >> pose during rollout) is the signal we watch when
# enabling the Pose detector.
COMPOSITION_CLASS = Counter(
    "ratemeai_composition_class_total",
    "Composition class detected on pre-analyze, by classifier source",
    labelnames=["composition_class", "source"],
)

# Style-pick attempts blocked by the CSL policy. ``composition_class``
# is the upload's class, ``style`` is the key the user tried to pick.
# Used to: (a) measure the actual impact of CSL on the funnel, (b)
# spot styles whose ``needs_full_body`` flag is mis-curated.
COMPOSITION_BLOCK = Counter(
    "ratemeai_composition_block_total",
    "Style requests blocked by composition policy",
    labelnames=["composition_class", "style"],
)

# Advanced-override (Phase 3) usage. Increments once per generation
# request that successfully bypassed CSL because the user opted in via
# the advanced-settings modal. A high override rate vs. ``block``
# means users disagree with the policy — calibration signal.
COMPOSITION_OVERRIDE_USED = Counter(
    "ratemeai_composition_override_used_total",
    "Composition safety bypassed via advanced override",
    labelnames=["composition_class", "style"],
)

# CSL Phase 1.5 (v1.64) — reference image geometric padding.
# Increments once per ``ImageGenerationExecutor.single_pass`` whose
# gate decided to call :func:`reference_preprocess.pad_reference_for_framing`
# before handing bytes to the edit-model provider. ``framing`` is the
# target framing key, ``composition_class`` is the CSL class that
# triggered the gate. Rate of this metric vs. ``IMAGE_GEN_ATTEMPT_TOTAL``
# = share of generations protected by geometric pre-correction; should
# track the "tight-selfie" upload share.
REFERENCE_PADDED = Counter(
    "ratemeai_reference_padded_total",
    "Reference images geometrically padded before edit-model invocation",
    labelnames=["framing", "composition_class"],
)


# ---------------------------------------------------------------------------
# v1.68 — image-quality systemic fix observability.
# ---------------------------------------------------------------------------

# Tracks which version of the reference padding geometry actually ran.
# ``version`` is ``v1`` (legacy ``x,y,w,h`` interpretation, kept for
# rollback only) or ``v2`` (correct ``x1,y1,x2,y2`` interpretation).
# Rate of v1 vs v2 in production = primary "did the fix ship?" signal.
PADDING_GEOMETRY_VERSION = Counter(
    "ratemeai_padding_geometry_version_total",
    "Reference padding executions by geometry interpretation version",
    labelnames=["version", "framing"],
)

# Fires once per wire prompt where the lens descriptor ``85mm`` appears
# more than once. v1.68 expects this counter to stay at 0 in
# production — a non-zero rate means a future edit re-introduced
# a duplicate lens token (the audit found ``85mm short-telephoto``
# in both ``_COMPOSITION_NUMERICAL_HINT`` and ``PHOTOREAL_BLOCK``).
PROMPT_DUPLICATE_LENS_WARN = Counter(
    "ratemeai_prompt_duplicate_lens_total",
    "Wire prompts where the lens descriptor token repeated",
    labelnames=["mode", "framing"],
)

# Optional re-detect after :func:`pad_reference_for_framing`. Observes
# the achieved ratio (real face height / canvas height) so we can
# validate that the padded reference actually lands on the geometry
# target (~0.28 for portrait, ~0.15 for half_body, ~0.08 for full_body).
# Wide bucketing — we only care about staying inside the right band.
FACE_DETECTION_AFTER_PAD = Histogram(
    "ratemeai_face_detection_after_pad_ratio",
    "Face-height ratio measured on the padded reference (post-detect)",
    labelnames=["framing"],
    buckets=(0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.18, 0.22, 0.28, 0.35, 0.45),
)
