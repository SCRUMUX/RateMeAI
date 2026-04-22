"""Activation rules and fallback behaviour for ``prerestore_if_needed``.

GFPGAN pre-clean is an optional, conservative stage. These tests pin:

* disabled feature flag ⇒ no-op, returns original bytes with
  ``skipped_reason="disabled"``;
* report-not-can_generate ⇒ clean-input path, no GFPGAN call;
* blur thresholds (face < 120 OR full < 150) ⇒ triggers GFPGAN;
* provider exception ⇒ returns original bytes with ``error`` populated
  (never propagates — pre-restoration is never load-bearing).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.face_prerestore import (
    BLUR_FACE_THRESHOLD,
    prerestore_if_needed,
    should_prerestore,
)
from src.services.input_quality import InputQualityReport


def _report(**overrides) -> InputQualityReport:
    defaults = dict(
        can_generate=True,
        face_area_ratio=0.20,
        face_center_offset=0.1,
        blur_face=200.0,
        blur_full=200.0,
        width=1024,
        height=1024,
        yaw=0.0,
        pitch=0.0,
        hair_bg_contrast=0.5,
        num_faces=1,
    )
    defaults.update(overrides)
    return InputQualityReport(**defaults)


# ------------------------------------------------------------------
# should_prerestore — pure decision logic
# ------------------------------------------------------------------


def test_should_prerestore_requires_feature_flag():
    r = _report(blur_face=50.0)  # clearly blurry
    assert should_prerestore(r, feature_enabled=False) is False
    assert should_prerestore(r, feature_enabled=True) is True


def test_should_prerestore_skips_rejected_input():
    r = _report(can_generate=False, blur_face=50.0)
    assert should_prerestore(r, feature_enabled=True) is False


def test_should_prerestore_skips_sharp_input():
    r = _report(blur_face=300.0, blur_full=300.0)
    assert should_prerestore(r, feature_enabled=True) is False


def test_should_prerestore_triggers_on_blurry_face():
    r = _report(blur_face=BLUR_FACE_THRESHOLD - 1.0, blur_full=300.0)
    assert should_prerestore(r, feature_enabled=True) is True


def test_should_prerestore_triggers_on_blurry_full():
    r = _report(blur_face=300.0, blur_full=100.0)
    assert should_prerestore(r, feature_enabled=True) is True


# ------------------------------------------------------------------
# prerestore_if_needed — end-to-end contract
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disabled_flag_returns_original_bytes():
    original = b"\xff\xd8\xff" + b"x" * 500
    out, info = await prerestore_if_needed(
        original, _report(blur_face=50.0), feature_enabled=False,
    )
    assert out is original
    assert info["applied"] is False
    assert info["skipped_reason"] == "disabled"


@pytest.mark.asyncio
async def test_blurry_input_runs_gfpgan_and_returns_restored_bytes():
    original = b"\xff\xd8\xff" + b"x" * 500
    restored = b"\xff\xd8\xff" + b"y" * 700
    fake = MagicMock()
    fake.restore = AsyncMock(return_value=restored)

    out, info = await prerestore_if_needed(
        original, _report(blur_face=50.0),
        restorer=fake, feature_enabled=True,
    )

    fake.restore.assert_awaited_once_with(original)
    assert out == restored
    assert info["applied"] is True
    assert info["error"] == ""


@pytest.mark.asyncio
async def test_clean_input_does_not_call_provider():
    original = b"\xff\xd8\xff" + b"x" * 500
    fake = MagicMock()
    fake.restore = AsyncMock(return_value=b"should-not-be-used")

    out, info = await prerestore_if_needed(
        original, _report(blur_face=300.0, blur_full=300.0),
        restorer=fake, feature_enabled=True,
    )

    fake.restore.assert_not_awaited()
    assert out is original
    assert info["applied"] is False
    assert info["skipped_reason"] == "clean_input"


@pytest.mark.asyncio
async def test_provider_failure_falls_back_to_original():
    original = b"\xff\xd8\xff" + b"x" * 500
    fake = MagicMock()
    fake.restore = AsyncMock(side_effect=RuntimeError("FAL down"))

    out, info = await prerestore_if_needed(
        original, _report(blur_face=50.0),
        restorer=fake, feature_enabled=True,
    )

    assert out is original
    assert info["applied"] is False
    assert "FAL down" in info["error"]


@pytest.mark.asyncio
async def test_empty_restorer_output_falls_back_to_original():
    original = b"\xff\xd8\xff" + b"x" * 500
    fake = MagicMock()
    fake.restore = AsyncMock(return_value=b"")

    out, info = await prerestore_if_needed(
        original, _report(blur_face=50.0),
        restorer=fake, feature_enabled=True,
    )

    assert out is original
    assert info["applied"] is False
    assert "empty" in info["error"]
