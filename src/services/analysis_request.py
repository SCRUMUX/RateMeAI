"""Shared analyze task context fields for web, bot, and internal (edge) callers."""

from __future__ import annotations

AB_MODELS_ALLOWED = frozenset({"nano_banana_2", "gpt_image_2"})

# v1.72 — product tiers visible to the user. ``standard`` is the
# 1-credit baseline (gpt_image_2 medium); ``premium`` is the 2-credit
# tier that pins the same base render but adds a Clarity refiner
# post-pass for visible texture polish (see
# ``src/providers/image_gen/fal_clarity_upscaler.py``). The legacy
# ``image_model`` knob is still honoured for backwards compatibility
# with internal A/B telemetry (Nano Banana 2 stays selectable from
# the admin / Railway env), but the public web UI exposes only the
# two product tiers.
PRODUCT_TIERS_ALLOWED = frozenset({"standard", "premium"})


def apply_ab_test_context_fields(
    ctx: dict,
    *,
    image_model: str,
    settings,
    tier: str | None = None,
) -> None:
    """Populate ``ctx`` with the A/B image-model + product-tier fields.

    v1.72 added the optional ``tier`` parameter. When ``tier ==
    "premium"`` the function pins ``image_model = "gpt_image_2"``,
    ``image_quality = "medium"`` and sets ``image_refine = "clarity"``
    so the executor knows to run the Clarity refiner post-pass on the
    main render. The premium tier intentionally ignores ``image_model``
    overrides — we do not want a user paying for premium and getting
    a Nano Banana render instead of the GPT Image 2 + Clarity stack.

    Standard tier (or ``tier`` left empty) preserves the v1.22
    behaviour: honour the client-requested ``image_model`` (within
    the A/B whitelist) at ``image_quality = "medium"``, no refiner.
    """
    if not getattr(settings, "ab_test_enabled", False):
        return

    tier_norm = (tier or "").strip().lower()
    if tier_norm not in PRODUCT_TIERS_ALLOWED:
        tier_norm = "standard"
    ctx["tier"] = tier_norm

    if tier_norm == "premium":
        # Premium pins the model + quality + refiner. Honouring a
        # client-supplied ``image_model`` here would let a Nano-Banana
        # render slip through with a 2-credit reservation, which is
        # the exact billing inversion the v1.72 UI cleanup is trying
        # to remove.
        ctx["image_model"] = "gpt_image_2"
        ctx["image_quality"] = "medium"
        if bool(getattr(settings, "clarity_refiner_enabled", True)):
            ctx["image_refine"] = "clarity"
        return

    im = (image_model or "").strip().lower()
    if im not in AB_MODELS_ALLOWED:
        im = getattr(settings, "ab_default_model", "gpt_image_2")
        if im not in AB_MODELS_ALLOWED:
            im = "gpt_image_2"
    ctx["image_model"] = im
    # Production-optimal tier: see api/v1/analyze.py — ignore client tier hints.
    ctx["image_quality"] = "medium"


def is_whitelisted_task_source_telegram(source: str) -> bool:
    """Return True if ``source`` should be stored on the task for analytics/compliance."""
    return (source or "").strip().lower() == "telegram_bot"
