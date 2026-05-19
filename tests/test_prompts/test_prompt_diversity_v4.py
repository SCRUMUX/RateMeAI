"""v4.1 (May 2026) — diversity invariants on the single prompt path.

The whole point of the v4 overhaul is that 10 users picking the same
style get 10 distinguishable photos. The v3 slot sampler delivers
that — provided every channel pool has enough entries (Stage 5 of the
2026-05 migration topped up the pools in ``data/styles.json``).

These tests guard the contract end-to-end:

* For every "high-traffic" landmark style we sample
  ``build_composition_v3`` with 10 different seeds and assert at least
  8 of the resulting prompts are unique. Up to two collisions are
  tolerated because the sampler is per-channel uniform — small pools
  may roll the same pair twice by chance.
* The final wrapped GPT-Image-2 prompt for each seed contains the
  v4.1 invariants (``IDENTITY_PRESERVE_BLOCK`` substring,
  ``PHOTOREAL_BLOCK`` substring, narrative scene line, ``Wardrobe:``
  prefix) — i.e. diversity does NOT come at the cost of dropping the
  identity anchors.

We use the actual catalog (``data/styles.json``) so the test fails if a
future PR shrinks the pool below the diversity threshold.
"""

from __future__ import annotations

import pytest

from src.prompts import image_gen as ig
from src.prompts.composition_builder import build_composition_v3
from src.prompts.image_gen import STYLE_REGISTRY
from src.prompts.model_wrappers import wrap_for_gpt_image_2
from src.services.style_loader_v2 import register_v2_styles_from_json
from src.services.style_loader_v3 import register_v3_styles_from_json


HIGH_TRAFFIC_STYLES: tuple[str, ...] = (
    "paris_eiffel",
    "barcelona_sagrada",
    "rome_colosseum",
    "london_big_ben",
    "nyc_times_square",
    "dubai_burj_khalifa",
    "nyc_brooklyn_bridge",
    "sf_golden_gate",
    "sydney_opera",
    "venice_san_marco",
)


@pytest.fixture(autouse=True)
def _register_styles():
    """Register every v2 + v3 entry from ``data/styles.json``.

    v4.1 dropped the ``style_schema_v3_enabled`` flag — both loaders
    are always-on. The v3 loader auto-promotes v2 specs without a
    native v3 sibling so every photo style ends up reachable via
    :func:`STYLE_REGISTRY.get_v3`.
    """
    snapshot_v2 = dict(STYLE_REGISTRY._v2_by_key)
    snapshot_v3 = dict(STYLE_REGISTRY._v3_by_key)
    snapshot_promoted = set(STYLE_REGISTRY._v3_promoted)

    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v3_promoted.clear()

    register_v2_styles_from_json()
    register_v3_styles_from_json()
    yield

    STYLE_REGISTRY._v2_by_key.clear()
    STYLE_REGISTRY._v2_by_key.update(snapshot_v2)
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v3_by_key.update(snapshot_v3)
    STYLE_REGISTRY._v3_promoted.clear()
    STYLE_REGISTRY._v3_promoted.update(snapshot_promoted)


def _build_prompt(style: str, *, mode: str, seed: int) -> str:
    spec = STYLE_REGISTRY.get_v3(mode, style)
    if spec is None:
        pytest.skip(f"v3 spec not registered: {mode}/{style}")
    ir = build_composition_v3(
        spec,
        mode=mode,
        change_instruction=ig._dating_social_change_instruction(mode, style),
        input_hints={},
        seed=seed,
        gender="male",
    )
    return wrap_for_gpt_image_2(ir)


@pytest.mark.parametrize("style", HIGH_TRAFFIC_STYLES)
def test_ten_seeds_yield_at_least_eight_unique_prompts(style):
    """10 users picking the same style → 10 different photos.

    Pool sizes after Stage 5 give 8 (lighting) × 5 (weather) × 5
    (time_of_day) × 4 (season) = 800 combinations on outdoor
    landmarks — uniqueness on 10 random samples should be near-perfect.
    We tolerate up to two collisions to keep the test stable against
    occasional double-rolls of the same combination on the same seed
    pair.
    """
    spec = STYLE_REGISTRY.get_v3("dating", style)
    if spec is None:
        pytest.skip(f"v3 spec not registered: dating/{style}")

    prompts = [_build_prompt(style, mode="dating", seed=s) for s in range(10)]
    unique = len(set(prompts))
    assert unique >= 8, (
        f"{style!r}: only {unique} unique prompts out of 10 — "
        f"slot pools may be too small. Sample diff:\n"
        f"  seed 0: {prompts[0][:200]!r}\n"
        f"  seed 1: {prompts[1][:200]!r}"
    )


@pytest.mark.parametrize("style", HIGH_TRAFFIC_STYLES)
def test_ten_seeds_all_carry_v4_1_anchors(style):
    """Diversity must not come at the cost of dropping identity or
    photoreal anchors. Every sample prompt MUST embed both v4.1
    blocks plus the narrative wardrobe label.
    """
    spec = STYLE_REGISTRY.get_v3("dating", style)
    if spec is None:
        pytest.skip(f"v3 spec not registered: dating/{style}")

    for s in range(10):
        prompt = _build_prompt(style, mode="dating", seed=s)
        # Identity anchors live in IDENTITY_PRESERVE_BLOCK. v1.67
        # softened the wording from "identical face shape, eye shape
        # and colour" to "preserve the same person's facial features:
        # eye shape and colour …" — the geometric "face shape" anchor
        # was dropped because edit-models read it as a constraint on
        # the head/torso ratio.
        assert "preserve the same person's facial features" in prompt, (
            f"{style!r} seed={s}: IDENTITY_PRESERVE_BLOCK missing\n{prompt!r}"
        )
        assert "eye shape and colour" in prompt, (
            f"{style!r} seed={s}: identity textural anchors missing\n"
            f"{prompt!r}"
        )
        # v1.70 — PHOTOREAL_BLOCK no longer carries a lens descriptor.
        # We assert on the skin-texture anchor instead, which is the
        # canonical surviving signal.
        assert "Authentic skin texture" in prompt, (
            f"{style!r} seed={s}: PHOTOREAL_BLOCK skin-texture anchor "
            f"missing\n{prompt!r}"
        )
        assert "85mm" not in prompt, (
            f"{style!r} seed={s}: v1.69 lens descriptor leaked back "
            "in — v1.70 removed lens spec entirely.\n"
            f"{prompt!r}"
        )
        # Wardrobe: prefix is the v4.1 replacement for "Subject is
        # wearing X" — locks the narrative-style wardrobe label.
        assert "Wardrobe:" in prompt, (
            f"{style!r} seed={s}: 'Wardrobe:' label missing\n{prompt!r}"
        )
