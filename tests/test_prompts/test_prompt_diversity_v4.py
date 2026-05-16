"""Stage 6 (prompt-pipeline-v4) — diversity invariants.

The whole point of the v4 overhaul is that 10 users picking the same
style get 10 distinguishable photos. The slot sampler can only deliver
that if every channel pool has enough entries — Stage 5 of the
migration tops up the pools in ``data/styles.json``.

These tests guard the contract end-to-end:

* For every "high-traffic" landmark style we sample ``build_composition_v3``
  with 10 different seeds and assert at least 8 of the resulting
  prompts are unique (allow up to two collisions because the sampler
  is per-channel uniform — small pools may roll the same pair twice
  by chance, especially when the user did not pass any hints).
* The final wrapped GPT-Image-2 prompt for each seed contains the v4
  invariants (``IDENTITY_PRESERVE_BLOCK`` substring, ``PASTED_ON_GUARD``
  substring) — i.e. diversity does NOT come at the cost of dropping
  the identity anchors.

We use the actual catalog (``data/styles.json``) so the test fails if a
future PR shrinks the pool below the diversity threshold.
"""

from __future__ import annotations

import pytest

from src.config import settings
from src.prompts import image_gen as ig
from src.prompts.composition_builder import build_composition_v3
from src.prompts.image_gen import STYLE_REGISTRY
from src.prompts.model_wrappers import wrap_for_gpt_image_2
from src.services.style_loader_v3 import register_v3_styles_from_json


# Styles the v4 plan explicitly calls out as "10 users → 10 distinct
# photos" targets. They live as ``schema_version: 3`` rows in
# ``data/styles.json`` and have rich enough ambient pools after the
# Stage 5 migration to roll uniquely on every seed.
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
def _register_v3(monkeypatch):
    """Register every v3-tagged entry from ``data/styles.json`` so the
    builder finds the high-traffic styles. The loader honours
    ``style_schema_v3_enabled`` — we flip it on for the duration of the
    test so the JSON catalog actually populates ``STYLE_REGISTRY._v3_by_key``."""
    monkeypatch.setattr(settings, "style_schema_v3_enabled", True, raising=False)
    snapshot = dict(STYLE_REGISTRY._v3_by_key)
    STYLE_REGISTRY._v3_by_key.clear()
    register_v3_styles_from_json()
    yield
    STYLE_REGISTRY._v3_by_key.clear()
    STYLE_REGISTRY._v3_by_key.update(snapshot)


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
    """The plan: "10 users picking the same style → 10 different
    photos". Pool sizes after Stage 5 give 8 (lighting) × 5 (weather)
    × 5 (time_of_day) × 4 (season) = 800 combinations on outdoor
    landmarks — uniqueness on 10 random samples should be near-perfect.
    We tolerate up to two collisions to keep the test stable against
    occasional double-rolls of the same combination on the same seed
    pair (allowed: 8 distinct out of 10).
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
def test_ten_seeds_all_carry_v4_anchors(style):
    """Diversity must not come at the cost of dropping the identity
    or pasted-on anchors. Every sample prompt MUST embed both."""
    spec = STYLE_REGISTRY.get_v3("dating", style)
    if spec is None:
        pytest.skip(f"v3 spec not registered: dating/{style}")

    for s in range(10):
        prompt = _build_prompt(style, mode="dating", seed=s)
        assert ig.PASTED_ON_GUARD in prompt, (
            f"{style!r} seed={s}: PASTED_ON_GUARD missing\n{prompt!r}"
        )
        # The IDENTITY_PRESERVE_BLOCK substring is the canonical "facial
        # features, bone structure, skin tone, hair" sequence — assert
        # the leading token to keep the test resilient to minor wording
        # tweaks while still pinning the preserve-first guarantee.
        assert "facial features, bone structure" in prompt.lower(), (
            f"{style!r} seed={s}: IDENTITY_PRESERVE_BLOCK missing\n{prompt!r}"
        )


def test_v4_prompt_total_length_drops_vs_v1_baseline(monkeypatch):
    """Stage 1+2 of the v4 overhaul replaces the legacy ~1100-char
    fixed tail with ~530 chars (PHOTOREAL_BLOCK + PASTED_ON_GUARD)
    plus a hoisted IDENTITY_PRESERVE_BLOCK. Total fixed boilerplate
    drops by ~30%. Compare the same wrapped prompt under v4-on vs
    v4-off (rollback path) to make sure the new layout actually
    delivers a shorter prompt — that's the headroom we use to fit
    longer scene + clothing pools per Stage 5."""
    spec = STYLE_REGISTRY.get_v3("dating", "paris_eiffel")
    if spec is None:
        pytest.skip("paris_eiffel v3 spec not registered")

    def _build(*, v4_on: bool) -> str:
        monkeypatch.setattr(
            settings, "prompt_pipeline_v4_enabled", v4_on, raising=False
        )
        ir = build_composition_v3(
            spec,
            mode="dating",
            change_instruction=ig._dating_social_change_instruction(
                "dating", "paris_eiffel"
            ),
            input_hints={},
            seed=0,
            gender="male",
        )
        return wrap_for_gpt_image_2(ir)

    v4_prompt = _build(v4_on=True)
    v1_prompt = _build(v4_on=False)

    assert len(v4_prompt) < len(v1_prompt), (
        f"v4 prompt is not shorter: v4={len(v4_prompt)} v1={len(v1_prompt)}"
    )
    # We aim for at least 25% reduction; tolerate small drift since
    # the change_instruction and scene description sit outside the tail.
    reduction = (len(v1_prompt) - len(v4_prompt)) / len(v1_prompt)
    assert reduction >= 0.20, (
        f"v4 prompt only {reduction:.0%} shorter than v1 baseline; "
        f"expected ≥20%. v4={len(v4_prompt)} v1={len(v1_prompt)}"
    )
