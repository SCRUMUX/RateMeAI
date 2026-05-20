"""v1.68 P2.7 — SSOT for (model, framing) → output-size request shape.

The SSOT table (``executor._OUTPUT_SIZE_BY_MODEL_FRAMING``) pins every
(model, framing) pair to the provider's NATIVE portrait pixel grid:

* ``gpt_image_2`` × any framing → ``image_size = {1024, 1536}`` (the
  model's native 2:3 portrait, no snap).
* ``nano_banana_2`` × any framing → ``aspect_ratio = "4:5"`` +
  ``resolution = "2K"`` (the model's native portrait enum).

Each pair also carries ``effective_aspect_ratio`` so the web / bot
can crop preview cards to the actual canvas the model produced.

These tests pin three contracts:

* :func:`_resolve_output_size_ssot` returns the right shape for the
  two supported models and three framings.
* It returns ``None`` for unknown models / framings (callers must
  fall back to the legacy path).
* No two entries claim different ``effective_aspect_ratio`` strings
  for the same model — the SSOT is genuinely single-valued.
"""

from __future__ import annotations

import pytest

from src.orchestrator.executor import (
    _OUTPUT_SIZE_BY_MODEL_FRAMING,
    _resolve_output_size_ssot,
)


_KNOWN_MODELS = ("gpt_image_2", "nano_banana_2")
_KNOWN_FRAMINGS = ("portrait", "half_body", "full_body")


def test_ssot_table_covers_every_known_pair():
    for model in _KNOWN_MODELS:
        for framing in _KNOWN_FRAMINGS:
            assert (model, framing) in _OUTPUT_SIZE_BY_MODEL_FRAMING, (
                f"({model!r}, {framing!r}) missing from "
                "_OUTPUT_SIZE_BY_MODEL_FRAMING — every supported pair "
                "needs a deterministic provider-side request shape."
            )


@pytest.mark.parametrize("framing", _KNOWN_FRAMINGS)
def test_gpt_image_2_returns_native_portrait_pixels(framing: str):
    """GPT Image 2 must ALWAYS receive 1024×1536 — that is its native
    2:3 portrait grid, so the provider does not silently snap to a
    different aspect.
    """
    entry = _resolve_output_size_ssot(model="gpt_image_2", framing=framing)
    assert entry is not None
    assert entry["image_size"] == {"width": 1024, "height": 1536}
    assert entry["effective_aspect_ratio"] == "2:3"


@pytest.mark.parametrize("framing", _KNOWN_FRAMINGS)
def test_nano_banana_2_returns_4_5_2k(framing: str):
    """NB2 must receive a concrete ``aspect_ratio`` enum (never
    ``auto``) plus a ``2K`` resolution. ``auto`` was the historical
    source of square-crop regressions on portrait references.
    """
    entry = _resolve_output_size_ssot(model="nano_banana_2", framing=framing)
    assert entry is not None
    assert entry["aspect_ratio"] == "4:5"
    assert entry["resolution"] == "2K"
    assert entry["effective_aspect_ratio"] == "4:5"


def test_unknown_model_returns_none():
    assert _resolve_output_size_ssot(model="legacy_unknown_model", framing="portrait") is None


def test_unknown_framing_returns_none():
    assert _resolve_output_size_ssot(model="gpt_image_2", framing="square") is None


def test_missing_args_return_none():
    assert _resolve_output_size_ssot(model=None, framing="portrait") is None
    assert _resolve_output_size_ssot(model="gpt_image_2", framing=None) is None


def test_effective_aspect_ratio_is_per_model_consistent():
    """All entries for the same model claim the same effective AR.
    A drift here would mean different framings of the same model
    produce different canvases, defeating the point of the SSOT.
    """
    per_model: dict[str, set[str]] = {}
    for (model, _framing), entry in _OUTPUT_SIZE_BY_MODEL_FRAMING.items():
        per_model.setdefault(model, set()).add(entry["effective_aspect_ratio"])
    for model, ars in per_model.items():
        assert len(ars) == 1, (
            f"model={model!r} has multiple effective_aspect_ratio "
            f"values across framings: {ars!r}. SSOT must be "
            "single-valued per model."
        )
