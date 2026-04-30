"""Sampler — ``available_channels`` gating (1.29.0).

These tests pin the contract added in 1.29.0: when a style declares
``available_channels``, the sampler only rolls values for the listed
channels. Channels outside the whitelist always resolve to the empty
string, regardless of pool contents and user hints.

When ``available_channels`` is empty (un-curated style), the sampler
falls back to the legacy heuristic — channel is enabled iff its
ambient pool is non-empty — so the migration is fully backwards-
compatible with the 126 styles already on disk.
"""

from __future__ import annotations

from src.prompts.slot_sampler import sample
from src.prompts.style_schema_v2 import (
    BackgroundLockLevel,
    ClothingSlot,
    QualityBlock,
)
from src.prompts.style_schema_v3 import (
    AmbientPools,
    StyleSpecV3,
)


def _spec(
    *,
    available_channels: tuple[str, ...] = (),
    location_type: str = "",
    lighting: tuple[str, ...] = ("warm", "cool"),
    weather: tuple[str, ...] = ("clear", "overcast"),
    time_of_day: tuple[str, ...] = ("morning", "evening"),
    season: tuple[str, ...] = ("spring", "summer", "autumn", "winter"),
) -> StyleSpecV3:
    return StyleSpecV3(
        key="t",
        mode="social",
        trigger_pool=("round wall mirror in frame",),
        scene_anchor="apartment interior",
        background_lock=BackgroundLockLevel.SEMI,
        ambient=AmbientPools(
            lighting=lighting,
            weather=weather,
            time_of_day=time_of_day,
            season=season,
        ),
        clothing=ClothingSlot(
            default={"male": "x", "female": "x", "neutral": "x"},
            allowed=(),
        ),
        quality_identity=QualityBlock(base="", per_model_tail={}),
        available_channels=available_channels,
        location_type=location_type,
    )


# ---------------------------------------------------------------------------
# Curated style — explicit allowlist disables un-listed channels
# ---------------------------------------------------------------------------


def test_indoor_style_with_no_season_keeps_pool_unrolled():
    """The user's headline complaint: ``mirror_aesthetic`` is indoor,
    its season pool was [spring, autumn], but the modal still showed
    season. With ``available_channels=("lighting", "time_of_day")``
    the sampler must NOT roll season even though the pool is non-empty.
    """
    spec = _spec(
        available_channels=("lighting", "time_of_day"),
        location_type="indoor",
        season=("spring", "autumn"),
    )
    resolved = sample(spec, {}, seed=42)
    assert resolved.lighting in spec.ambient.lighting
    assert resolved.time_of_day in spec.ambient.time_of_day
    assert resolved.season == ""
    assert resolved.weather == ""


def test_user_hint_for_disabled_channel_is_ignored_at_sampler_level():
    """If a channel is gated off, the sampler outputs empty even when
    the caller sneaks a hint past the modal. Defense-in-depth — the
    UI hides the control but a malicious / outdated client could
    still attempt to set it."""
    spec = _spec(available_channels=("lighting",), location_type="indoor")
    resolved = sample(spec, {"season": "winter"}, seed=1)
    assert resolved.season == ""


def test_explicit_channel_in_allowlist_still_rolls():
    spec = _spec(
        available_channels=("lighting", "weather", "time_of_day", "season"),
        location_type="outdoor",
    )
    resolved = sample(spec, {}, seed=7)
    assert resolved.lighting in spec.ambient.lighting
    assert resolved.weather in spec.ambient.weather
    assert resolved.time_of_day in spec.ambient.time_of_day
    assert resolved.season in spec.ambient.season


# ---------------------------------------------------------------------------
# Un-curated style — fallback to "non-empty pool = enabled"
# ---------------------------------------------------------------------------


def test_empty_available_channels_falls_back_to_pool_heuristic():
    """When the operator hasn't curated the style, channels with a
    non-empty pool keep being rolled — preserves 1.28.0 behaviour
    for the 126 styles already on disk."""
    spec = _spec(
        available_channels=(),
        location_type="",
        lighting=("warm", "cool"),
        weather=(),
        time_of_day=("morning",),
        season=(),
    )
    resolved = sample(spec, {}, seed=3)
    assert resolved.lighting != ""
    assert resolved.weather == ""  # empty pool → empty
    assert resolved.time_of_day != ""
    assert resolved.season == ""


# ---------------------------------------------------------------------------
# is_channel_enabled — direct unit
# ---------------------------------------------------------------------------


def test_is_channel_enabled_curated_only_returns_for_listed():
    spec = _spec(available_channels=("lighting",), location_type="indoor")
    assert spec.is_channel_enabled("lighting") is True
    assert spec.is_channel_enabled("season") is False
    assert spec.is_channel_enabled("weather") is False


def test_is_channel_enabled_uncurated_uses_pool_heuristic():
    spec = _spec(
        available_channels=(),
        lighting=("warm",),
        weather=(),
    )
    assert spec.is_channel_enabled("lighting") is True
    assert spec.is_channel_enabled("weather") is False
