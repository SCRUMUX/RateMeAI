"""SSOT for framing → output-size request shape.

Pre-cleanup this table was keyed by ``(model, framing)`` because Nano
Banana 2 needed an ``aspect_ratio`` enum + ``resolution`` tier
instead of a raw ``{width, height}``. After Nano Banana was retired
the table collapsed to ``framing → image_size``:

* portrait / half_body / full_body → ``image_size = {1024, 1536}``
  (GPT Image 2's native 2:3 portrait, no snap), ``effective_aspect_ratio = "2:3"``.

The SSOT lookup still accepts a (now ignored) ``model`` kwarg so
older call sites do not need to rename their parameters.
"""

from __future__ import annotations

import pytest

from src.orchestrator.executor import (
    _OUTPUT_SIZE_BY_FRAMING,
    _resolve_output_size_ssot,
)


_KNOWN_FRAMINGS = ("portrait", "half_body", "full_body")


def test_ssot_table_covers_every_known_framing():
    for framing in _KNOWN_FRAMINGS:
        assert framing in _OUTPUT_SIZE_BY_FRAMING, (
            f"{framing!r} missing from _OUTPUT_SIZE_BY_FRAMING — "
            "every supported framing needs a deterministic "
            "provider-side request shape."
        )


@pytest.mark.parametrize("framing", _KNOWN_FRAMINGS)
def test_resolver_returns_native_portrait_pixels(framing: str):
    """GPT Image 2 must ALWAYS receive 1024×1536 — that is its native
    2:3 portrait grid, so the provider does not silently snap to a
    different aspect.
    """
    entry = _resolve_output_size_ssot(framing=framing)
    assert entry is not None
    assert entry["image_size"] == {"width": 1024, "height": 1536}
    assert entry["effective_aspect_ratio"] == "2:3"


@pytest.mark.parametrize("framing", _KNOWN_FRAMINGS)
def test_resolver_ignores_legacy_model_kwarg(framing: str):
    """The historical ``model`` key is accepted for backwards
    compatibility and must not change the resolved shape — there is
    one image model in the pipeline."""
    base = _resolve_output_size_ssot(framing=framing)
    for legacy_model in ("gpt_image_2", "nano_banana_2", "anything"):
        entry = _resolve_output_size_ssot(model=legacy_model, framing=framing)
        assert entry == base


def test_unknown_framing_returns_none():
    assert _resolve_output_size_ssot(framing="square") is None


def test_missing_args_return_none():
    assert _resolve_output_size_ssot(framing=None) is None


def test_effective_aspect_ratio_is_consistent():
    """All entries claim the same effective AR — a drift would mean
    different framings produce different canvases, defeating the
    point of the SSOT.
    """
    ars = {entry["effective_aspect_ratio"] for entry in _OUTPUT_SIZE_BY_FRAMING.values()}
    assert ars == {"2:3"}, (
        f"effective_aspect_ratio drift across framings: {ars!r}. "
        "SSOT must be single-valued."
    )
