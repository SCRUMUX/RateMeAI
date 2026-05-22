"""Shared analyze task context fields for web, bot, and internal (edge) callers."""

from __future__ import annotations

# Product tiers visible to the user. ``standard`` is the 1-credit
# baseline (gpt_image_2 *medium*); ``premium`` is the 5-credit tier
# that pins gpt_image_2 *high* quality on the same prompt + pipeline
# as Standard — no Clarity refiner post-pass (v1.79).
#
# Cost ceiling (FAL):
#   * Standard ≈ $0.06 / img (gpt_image_2 medium).
#   * Premium  ≈ $0.20 / img (gpt_image_2 high only).
#
# There is no cross-tier downgrade: if Premium fails (gpt_image_2
# returns empty, etc.) the user is shown an error and refunded all
# 5 credits; we never silently deliver a Standard render in place
# of a Premium one (see ``src/workers/tasks.py``).
PRODUCT_TIERS_ALLOWED = frozenset({"standard", "premium"})

# Number of image-credits a Premium request reserves (1 base + 4
# extra). ``apply_tier_context_fields`` itself does not touch credits
# — the reservation lives in ``src/api/v1/analyze.py``; this constant
# is the single source of truth so the analyze handler, the worker
# refund path, and the unit tests stay in sync. Keep numeric (not a
# settings knob) so the value cannot drift between app / worker /
# bot Railway services at deploy time.
PREMIUM_CREDIT_COST = 5
# Credits reserved on top of the always-reserved first credit. The
# analyze handler calls ``reserve_additional_credit(amount=PREMIUM_EXTRA_CREDIT_RESERVE)``
# only when ``tier=premium`` — the standard tier path is unchanged.
PREMIUM_EXTRA_CREDIT_RESERVE = PREMIUM_CREDIT_COST - 1  # = 4

# Backwards-compat shim. The image-model A/B layer was retired in the
# Nano Banana cleanup; old call sites and tests may still import
# ``AB_MODELS_ALLOWED``. We expose the single live model as a frozenset
# so any membership check that survived the migration still resolves
# truthy without re-introducing Nano Banana into the validator.
AB_MODELS_ALLOWED = frozenset({"gpt_image_2"})


def apply_tier_context_fields(
    ctx: dict,
    *,
    settings,
    tier: str | None = None,
) -> None:
    """Populate ``ctx`` with the product-tier image-gen fields.

    There is one image model in the pipeline (GPT Image 2 Edit). The
    tier only switches the FAL ``quality`` knob; prompt and executor
    path are identical to Standard:

    * ``standard`` → ``image_model="gpt_image_2"``,
      ``image_quality="medium"``. ≈ $0.06 / img.
    * ``premium``  → ``image_quality="high"`` (same pipeline, no
      ``image_refine`` / Clarity). ≈ $0.20 / img. Charged 5 credits;
      see ``PREMIUM_CREDIT_COST``.

    The historical A/B ``image_model`` knob was retired together with
    Nano Banana 2. Callers may still pass an ``image_model`` form
    field for backwards compatibility, but it is ignored here.

    v1.77 — tier routing is a permanent product surface, not an A/B
    experiment. ``settings.ab_test_enabled`` no longer gates this
    helper (when it was False, Premium and Standard both skipped
    tier fields and rendered identically). The flag may still exist
    for legacy metrics elsewhere but must not block tier → quality.
    """
    tier_norm = (tier or "").strip().lower()
    if tier_norm not in PRODUCT_TIERS_ALLOWED:
        tier_norm = "standard"
    ctx["tier"] = tier_norm
    ctx["image_model"] = "gpt_image_2"

    if tier_norm == "premium":
        # v1.79 — Premium = FAL ``quality=high`` only (same prompt /
        # pipeline as Standard). Clarity refiner retired from the
        # product tier to avoid SD-upscale artefacts.
        ctx["image_quality"] = "high"
    else:
        ctx["image_quality"] = "medium"


def apply_ab_test_context_fields(
    ctx: dict,
    *,
    image_model: str | None = None,
    settings,
    tier: str | None = None,
) -> None:
    """Backwards-compatible alias for :func:`apply_tier_context_fields`.

    ``image_model`` is accepted but ignored — there is only one image
    model in the pipeline now. The argument is kept so external
    callers (edge proxy, older bot builds, ARQ tasks queued before
    the migration) do not break on the kwarg signature.
    """
    _ = image_model  # explicitly unused after the Nano Banana cleanup.
    apply_tier_context_fields(ctx, settings=settings, tier=tier)


def is_gpt_image_gen_context_active(ctx: dict | None) -> bool:
    """Return True when ``ctx`` carries GPT Image 2 tier routing fields.

    Used by the pipeline and executor to decide whether to engage the
    edit-model path (quality knob) instead
    of the legacy hybrid StyleRouter. After v1.77 this is true for
    every analyze request that went through
    :func:`apply_tier_context_fields`, regardless of
    ``settings.ab_test_enabled``.
    """
    if not ctx:
        return False
    if (ctx.get("image_model") or "").strip():
        return True
    tier = (ctx.get("tier") or "").strip().lower()
    return tier in PRODUCT_TIERS_ALLOWED


def is_whitelisted_task_source_telegram(source: str) -> bool:
    """Return True if ``source`` should be stored on the task for analytics/compliance."""
    return (source or "").strip().lower() == "telegram_bot"
