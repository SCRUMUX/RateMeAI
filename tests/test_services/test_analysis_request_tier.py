"""Unit tests for product-tier handling in ``analysis_request``.

Post Nano-Banana cleanup the single live image model is
``gpt_image_2``. ``apply_ab_test_context_fields`` (the legacy alias
of :func:`apply_tier_context_fields`) accepts a backwards-compatible
``image_model`` kwarg but ignores it — every call resolves to
``image_model="gpt_image_2"``. ``image_quality`` is now tier-aware:

* ``standard`` → ``medium`` (≈ $0.06/img, 1 credit).
* ``premium``  → ``high`` only (≈ $0.20/img, 5 credits — no Clarity).

v1.79: Premium no longer sets ``image_refine=clarity`` — same pipeline
as Standard, only the FAL quality knob changes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.services.analysis_request import (
    AB_MODELS_ALLOWED,
    PREMIUM_CREDIT_COST,
    PREMIUM_EXTRA_CREDIT_RESERVE,
    PRODUCT_TIERS_ALLOWED,
    apply_ab_test_context_fields,
)


def _settings(**overrides):
    """Build a minimal settings stub for the helper."""
    base = {
        "ab_test_enabled": True,
        "ab_default_model": "gpt_image_2",
        "clarity_refiner_enabled": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestAllowlists:
    def test_ab_models_allowlist_collapsed_to_gpt_image_2(self):
        assert AB_MODELS_ALLOWED == frozenset({"gpt_image_2"})

    def test_product_tiers_allowlist_pins_two_tiers(self):
        assert PRODUCT_TIERS_ALLOWED == frozenset({"standard", "premium"})


class TestStandardTier:
    def test_standard_tier_ignores_legacy_image_model(self):
        """Even if an older client posts ``image_model=nano_banana_2``
        the helper must resolve to ``gpt_image_2`` — there is one
        live image model in the pipeline."""
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="nano_banana_2",
            settings=_settings(),
            tier="standard",
        )
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["image_quality"] == "medium"
        assert ctx["tier"] == "standard"
        assert "image_refine" not in ctx

    def test_standard_tier_with_empty_image_model(self):
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="",
            settings=_settings(ab_default_model="gpt_image_2"),
            tier="standard",
        )
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["tier"] == "standard"
        assert "image_refine" not in ctx

    def test_empty_tier_defaults_to_standard(self):
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="gpt_image_2",
            settings=_settings(),
        )
        assert ctx["tier"] == "standard"
        assert ctx["image_model"] == "gpt_image_2"
        assert "image_refine" not in ctx

    def test_unknown_tier_falls_back_to_standard(self):
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="gpt_image_2",
            settings=_settings(),
            tier="bogus",
        )
        assert ctx["tier"] == "standard"
        assert "image_refine" not in ctx


class TestPremiumTier:
    def test_premium_tier_pins_gpt_image_2_high(self):
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="gpt_image_2",
            settings=_settings(),
            tier="premium",
        )
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["image_quality"] == "high"
        assert ctx["tier"] == "premium"
        assert "image_refine" not in ctx

    def test_premium_tier_ignores_legacy_image_model_arg(self):
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="nano_banana_2",
            settings=_settings(),
            tier="premium",
        )
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["image_quality"] == "high"
        assert "image_refine" not in ctx

    def test_premium_tier_never_sets_clarity_refine(self):
        """v1.79 — Clarity is not part of the product tier even when
        the global kill-switch is on."""
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="gpt_image_2",
            settings=_settings(clarity_refiner_enabled=True),
            tier="premium",
        )
        assert ctx["image_quality"] == "high"
        assert "image_refine" not in ctx


class TestPremiumCreditCost:
    """v1.75 — Premium reserves 5 credits (1 base + 4 extra)."""

    def test_premium_credit_cost_is_five(self):
        assert PREMIUM_CREDIT_COST == 5

    def test_premium_extra_credit_reserve_is_four(self):
        assert PREMIUM_EXTRA_CREDIT_RESERVE == 4

    def test_premium_credit_cost_invariant(self):
        assert PREMIUM_EXTRA_CREDIT_RESERVE + 1 == PREMIUM_CREDIT_COST


class TestTierIndependentOfAbFlag:
    def test_premium_tier_applies_when_ab_test_disabled(self):
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="gpt_image_2",
            settings=_settings(ab_test_enabled=False),
            tier="premium",
        )
        assert ctx["tier"] == "premium"
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["image_quality"] == "high"
        assert "image_refine" not in ctx


@pytest.mark.parametrize(
    "tier,expected_quality",
    [
        ("standard", "medium"),
        ("premium", "high"),
    ],
)
def test_tier_to_quality_mapping_pins_contract(
    tier: str, expected_quality: str,
):
    ctx: dict = {}
    apply_ab_test_context_fields(
        ctx,
        image_model="gpt_image_2",
        settings=_settings(),
        tier=tier,
    )
    assert ctx["image_quality"] == expected_quality
    assert "image_refine" not in ctx
