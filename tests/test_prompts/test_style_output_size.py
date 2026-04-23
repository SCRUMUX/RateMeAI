"""Output-size contract per style (v1.16 FLUX.2 Pro Edit migration).

Every registered style must declare an ``output_aspect`` so the
executor can resolve a concrete ``image_size`` for the provider.
Document styles land in ``square_hd`` (1 MP, strict composition
matters, detail secondary); everything else lands in ``portrait_4_3``
(2 MP portrait, target ~1280x1600 for face sharpness on full-body
scenes).
"""

from __future__ import annotations

import pytest

from src.prompts.image_gen import (
    STYLE_REGISTRY,
    _DOCUMENT_STYLE_KEYS,
    resolve_output_size,
)
from src.prompts.style_spec import detect_output_aspect


_ALL_SPECS = [
    (mode, key, spec)
    for (mode, key), spec in STYLE_REGISTRY._by_key.items()  # type: ignore[attr-defined]
]


@pytest.mark.parametrize(("mode", "key", "spec"), _ALL_SPECS)
def test_every_registered_style_has_output_aspect(mode, key, spec):
    """No silent ``None`` — every spec must carry an explicit aspect."""
    assert hasattr(spec, "output_aspect"), (
        f"StyleSpec({mode}:{key}) missing output_aspect field"
    )
    assert spec.output_aspect in {
        "portrait_4_3",
        "portrait_16_9",
        "square_hd",
        "landscape_4_3",
        "landscape_16_9",
    }, f"StyleSpec({mode}:{key}) has unsupported output_aspect={spec.output_aspect}"


def test_document_styles_use_square_hd():
    """Every registered document style must end up on ``square_hd``.

    A handful of entries in ``_DOCUMENT_STYLE_KEYS`` are allow-listed
    for the prompt builder but not (yet) registered as first-class
    CV styles (driver_license / visa_schengen). We skip those — the
    whitelist is the wider set; the registry is the subset we ship.
    """
    checked = 0
    for style_key in _DOCUMENT_STYLE_KEYS:
        spec = STYLE_REGISTRY.get("cv", style_key)
        if spec is None:
            continue
        assert spec.output_aspect == "square_hd", (
            f"document style {style_key!r} must be square_hd, got {spec.output_aspect}"
        )
        checked += 1
    assert checked >= 4, (
        f"expected ≥4 registered document styles to verify, got {checked}"
    )


def test_full_body_styles_use_portrait_4_3():
    """needs_full_body scenes (yoga/beach/running/...) → 2 MP portrait.

    This is the core of the Flux2 migration: face ends up at ≈400–500 px
    on its long side, which is where the identity-match improvement
    comes from.
    """
    full_body_specs = [
        (mode, key, spec)
        for mode, key, spec in _ALL_SPECS
        if getattr(spec, "needs_full_body", False)
    ]
    assert full_body_specs, "no needs_full_body styles found — registry broken?"
    for mode, key, spec in full_body_specs:
        assert spec.output_aspect == "portrait_4_3", (
            f"full-body style {mode}:{key} must be portrait_4_3, "
            f"got {spec.output_aspect}"
        )


def test_resolve_output_size_returns_custom_dict_for_portrait_styles():
    # v1.19: identity_scene (PuLID) styles run at ~1 MP to avoid
    # duplicate-subject artefacts on the 2 MP portrait path. The
    # default generation_mode for non-document dating styles is
    # identity_scene, so beach_sunset now resolves to 896x1152.
    spec = STYLE_REGISTRY.get("dating", "beach_sunset")
    if spec is None or not getattr(spec, "needs_full_body", False):
        pytest.skip("beach_sunset not registered as full-body style")
    size = resolve_output_size(spec)
    assert size == {"width": 896, "height": 1152}
    mp = (size["width"] * size["height"]) / 1_000_000
    assert 0.95 <= mp <= 1.1, f"expected ~1 MP for PuLID, got {mp:.2f}"


def test_resolve_output_size_scene_preserve_stays_at_2mp():
    # scene_preserve (Seedream) can handle 2 MP without the PuLID
    # duplicate-subject failure mode — keep the existing 1280x1600
    # output there so we don't lose delivery resolution.
    spec = STYLE_REGISTRY.get("dating", "beach_sunset")
    if spec is None or not getattr(spec, "needs_full_body", False):
        pytest.skip("beach_sunset not registered as full-body style")
    size = resolve_output_size(spec, generation_mode="scene_preserve")
    assert size == {"width": 1280, "height": 1600}


def test_resolve_output_size_returns_1mp_for_documents():
    spec = STYLE_REGISTRY.get("cv", "photo_3x4")
    if spec is None:
        pytest.skip("photo_3x4 not registered")
    size = resolve_output_size(spec)
    assert size == {"width": 1024, "height": 1024}
    mp = (size["width"] * size["height"]) / 1_000_000
    assert 0.95 <= mp <= 1.1, f"expected ~1 MP for documents, got {mp:.2f}"


def test_resolve_output_size_none_spec_returns_none():
    assert resolve_output_size(None) is None


def test_detect_output_aspect_defaults():
    assert detect_output_aspect("photo_3x4", "cv") == "square_hd"
    assert detect_output_aspect("yoga_outdoor", "dating") == "portrait_4_3"
    assert detect_output_aspect("studio_elegant", "dating") == "portrait_4_3"
