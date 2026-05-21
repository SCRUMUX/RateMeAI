"""Unit tests for product-tier handling in ``analysis_request``.

Post Nano-Banana cleanup the single live image model is
``gpt_image_2``. ``apply_ab_test_context_fields`` (the legacy alias
of :func:`apply_tier_context_fields`) accepts a backwards-compatible
``image_model`` kwarg but ignores it — every call resolves to
``image_model="gpt_image_2"``. ``image_quality`` is now tier-aware:

* ``standard`` → ``medium`` (≈ $0.06/img, 1 credit).
* ``premium``  → ``high`` + ``image_refine="clarity"``
  (≈ $0.24/img, 5 credits — see ``PREMIUM_CREDIT_COST``).

v1.75 change: Standard and Premium used to share ``medium`` quality
which made the visible output identical between the two tiers. The
``high`` quality switch is the actual reason Premium now looks
different. Premium also no longer silently downgrades to Standard
on refiner failure (the executor raises and the worker refunds all
5 credits via the failure-path block in ``workers/tasks.py``).
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
        """v1.75 — Premium now switches the FAL ``quality`` knob to
        ``high``. The previous v1.72 contract pinned ``medium`` which
        made the Standard / Premium output indistinguishable."""
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="gpt_image_2",
            settings=_settings(),
            tier="premium",
        )
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["image_quality"] == "high"
        assert ctx["image_refine"] == "clarity"
        assert ctx["tier"] == "premium"

    def test_premium_tier_ignores_legacy_image_model_arg(self):
        """Older clients may still post ``image_model=nano_banana_2``;
        the helper must collapse it to ``gpt_image_2`` and still flag
        the Clarity refiner + high quality."""
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="nano_banana_2",
            settings=_settings(),
            tier="premium",
        )
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["image_quality"] == "high"
        assert ctx["image_refine"] == "clarity"

    def test_premium_tier_respects_clarity_refiner_kill_switch(self):
        """When the Railway kill-switch is off, premium still pins
        ``image_quality=high`` (the base render is still upgraded)
        but ``image_refine`` is dropped so the executor doesn't call
        FAL clarity. Even with the kill-switch on the user is still
        charged 5 credits because the high-quality render is the
        more expensive part of the cost stack ($0.20 vs Clarity's
        $0.04 share)."""
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="gpt_image_2",
            settings=_settings(clarity_refiner_enabled=False),
            tier="premium",
        )
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["image_quality"] == "high"
        assert ctx["tier"] == "premium"
        assert "image_refine" not in ctx


class TestPremiumCreditCost:
    """v1.75 — Premium reserves 5 credits (1 base + 4 extra).
    These constants are the single source of truth shared with the
    analyze handler and the worker refund path."""

    def test_premium_credit_cost_is_five(self):
        assert PREMIUM_CREDIT_COST == 5

    def test_premium_extra_credit_reserve_is_four(self):
        assert PREMIUM_EXTRA_CREDIT_RESERVE == 4

    def test_premium_credit_cost_invariant(self):
        """Extra reserve plus the always-reserved first credit
        equals the user-visible premium cost."""
        assert PREMIUM_EXTRA_CREDIT_RESERVE + 1 == PREMIUM_CREDIT_COST


class TestTierIndependentOfAbFlag:
    def test_premium_tier_applies_when_ab_test_disabled(self):
        """v1.77 — tier routing must not depend on ``ab_test_enabled``.

        When the flag was False the helper returned early and Premium
        rendered identically to Standard — the bug this class guards."""
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
        assert ctx["image_refine"] == "clarity"


@pytest.mark.parametrize(
    "tier,expected_quality,expected_refine",
    [
        ("standard", "medium", None),
        ("premium", "high", "clarity"),
    ],
)
def test_tier_to_quality_refine_mapping_pins_contract(
    tier: str, expected_quality: str, expected_refine: str | None,
):
    """Parametrised pin so a future refactor that introduces a new
    refiner backend (CodeFormer / Aura-SR) or a new quality tier
    has to update this table consciously. v1.75 adds the
    ``expected_quality`` axis because the prior medium / medium
    overlap was the bug that made the Premium pill visually
    identical to Standard."""
    ctx: dict = {}
    apply_ab_test_context_fields(
        ctx,
        image_model="gpt_image_2",
        settings=_settings(),
        tier=tier,
    )
    assert ctx["image_quality"] == expected_quality
    assert ctx.get("image_refine") == expected_refine
