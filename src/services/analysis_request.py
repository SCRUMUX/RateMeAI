"""Shared analyze task context fields for web, bot, and internal (edge) callers."""

from __future__ import annotations

# Product tiers visible to the user. ``standard`` is the 1-credit
# baseline (gpt_image_2 medium); ``premium`` is the 2-credit tier that
# pins the same base render but adds a Clarity Upscaler post-pass for
# visible texture polish + a real resolution bump (see
# ``src/providers/image_gen/fal_clarity_upscaler.py`` and the executor
# ``_apply_clarity_refine``). The historic ``image_model`` A/B knob
# was retired together with the Nano Banana 2 backend — there is one
# image model in the pipeline (GPT Image 2 Edit) and the tier picks
# whether the Clarity post-pass runs.
PRODUCT_TIERS_ALLOWED = frozenset({"standard", "premium"})

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
    tier decides whether the Clarity Upscaler post-pass runs:

    * ``standard`` → ``image_model="gpt_image_2"``,
      ``image_quality="medium"``, no refiner.
    * ``premium``  → same base render, plus
      ``image_refine="clarity"`` so the executor runs the Clarity
      post-pass (resolution bump + texture polish, total cost stays
      ≤ $0.10/image).

    The historical A/B ``image_model`` knob was retired together with
    Nano Banana 2. Callers may still pass an ``image_model`` form
    field for backwards compatibility, but it is ignored here.
    """
    if not getattr(settings, "ab_test_enabled", False):
        return

    tier_norm = (tier or "").strip().lower()
    if tier_norm not in PRODUCT_TIERS_ALLOWED:
        tier_norm = "standard"
    ctx["tier"] = tier_norm
    ctx["image_model"] = "gpt_image_2"
    ctx["image_quality"] = "medium"

    if tier_norm == "premium" and bool(
        getattr(settings, "clarity_refiner_enabled", True)
    ):
        ctx["image_refine"] = "clarity"


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


def is_whitelisted_task_source_telegram(source: str) -> bool:
    """Return True if ``source`` should be stored on the task for analytics/compliance."""
    return (source or "").strip().lower() == "telegram_bot"
