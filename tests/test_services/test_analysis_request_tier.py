"""v1.72 — unit tests for product tier handling in analysis_request.

Pins the contract that ``apply_ab_test_context_fields`` writes the
correct ``image_model`` / ``image_quality`` / ``image_refine`` keys
into ``ctx`` for each (tier, requested_model) combination. The
premium tier MUST force ``gpt_image_2`` regardless of the requested
model so a Nano Banana 2 render cannot slip through with a
2-credit reservation.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.services.analysis_request import (
    AB_MODELS_ALLOWED,
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


class TestAbAllowlists:
    def test_ab_models_allowlist_pins_two_models(self):
        assert AB_MODELS_ALLOWED == frozenset(
            {"nano_banana_2", "gpt_image_2"}
        )

    def test_product_tiers_allowlist_pins_two_tiers(self):
        assert PRODUCT_TIERS_ALLOWED == frozenset(
            {"standard", "premium"}
        )


class TestStandardTier:
    def test_standard_tier_honours_requested_model(self):
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="nano_banana_2",
            settings=_settings(),
            tier="standard",
        )
        assert ctx["image_model"] == "nano_banana_2"
        assert ctx["image_quality"] == "medium"
        assert ctx["tier"] == "standard"
        assert "image_refine" not in ctx

    def test_standard_tier_falls_back_to_default_model(self):
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
    def test_premium_tier_pins_gpt_image_2_medium(self):
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="gpt_image_2",
            settings=_settings(),
            tier="premium",
        )
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["image_quality"] == "medium"
        assert ctx["image_refine"] == "clarity"
        assert ctx["tier"] == "premium"

    def test_premium_tier_overrides_nano_banana_request(self):
        """A user-supplied ``image_model=nano_banana_2`` MUST be ignored on
        the premium tier — otherwise the 2-credit reservation could be
        billed against a Nano Banana render, which is the exact
        regression the v1.72 product cleanup eliminates."""
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="nano_banana_2",
            settings=_settings(),
            tier="premium",
        )
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["image_refine"] == "clarity"

    def test_premium_tier_respects_clarity_refiner_kill_switch(self):
        """When the Railway kill-switch is off, premium still resolves to
        gpt_image_2 medium but ``image_refine`` is dropped so the
        executor doesn't try to call FAL clarity. The orchestrator
        treats a missing refine signal as the standard tier and the
        worker refund logic kicks in on the credit side (premium
        users get 1 credit refunded for a premium upgrade that didn't
        run)."""
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="gpt_image_2",
            settings=_settings(clarity_refiner_enabled=False),
            tier="premium",
        )
        assert ctx["image_model"] == "gpt_image_2"
        assert ctx["tier"] == "premium"
        assert "image_refine" not in ctx


class TestAbDisabled:
    def test_disabled_ab_short_circuits(self):
        """When ``settings.ab_test_enabled`` is False the helper is a
        no-op — the orchestrator falls back to the default hybrid
        StyleRouter and tier metadata is irrelevant."""
        ctx: dict = {}
        apply_ab_test_context_fields(
            ctx,
            image_model="gpt_image_2",
            settings=_settings(ab_test_enabled=False),
            tier="premium",
        )
        assert ctx == {}


@pytest.mark.parametrize(
    "tier,expected_refine",
    [
        ("standard", None),
        ("premium", "clarity"),
    ],
)
def test_tier_to_refine_mapping_pins_contract(
    tier: str, expected_refine: str | None,
):
    """Parametrised pin so a future refactor that introduces a new
    refiner backend (e.g. CodeFormer or Aura-SR) has to update this
    table consciously."""
    ctx: dict = {}
    apply_ab_test_context_fields(
        ctx,
        image_model="gpt_image_2",
        settings=_settings(),
        tier=tier,
    )
    assert ctx.get("image_refine") == expected_refine
