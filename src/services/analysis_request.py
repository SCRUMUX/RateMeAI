"""Shared analyze task context fields for web, bot, and internal (edge) callers."""

from __future__ import annotations

AB_MODELS_ALLOWED = frozenset({"nano_banana_2", "gpt_image_2"})


def apply_ab_test_context_fields(
    ctx: dict,
    *,
    image_model: str,
    settings,
) -> None:
    """When A/B is enabled, set ``image_model`` and locked ``image_quality`` on ``ctx``."""
    if not getattr(settings, "ab_test_enabled", False):
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
