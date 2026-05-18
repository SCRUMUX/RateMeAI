"""Tests for pre-flight input quality gate (InsightFace + mediapipe + Laplacian)."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from src.services import input_quality as iq
from src.services.photo_requirements import IssueCode


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _rgb_bytes(w: int = 800, h: int = 800, color=(128, 128, 128)) -> bytes:
    img = Image.new("RGB", (w, h), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _sharp_noise_bytes(w: int = 800, h: int = 800) -> bytes:
    arr = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _mock_face(bbox=(300, 300, 500, 500), det=0.9, pose=(0.0, 0.0, 0.0)):
    face = MagicMock()
    face.bbox = np.array(bbox, dtype=np.float32)
    face.det_score = det
    face.pose = np.array(pose, dtype=np.float32)
    return face


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


def test_invalid_image_blocks():
    rep = iq.analyze_input_quality(b"not an image")
    assert rep.can_generate is False
    assert any(i.code == IssueCode.INVALID_IMAGE for i in rep.blocking)


def test_low_resolution_blocks():
    with patch.object(iq, "_detect_faces", return_value=[_mock_face()]):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(300, 300))
    assert rep.can_generate is False
    assert any(i.code == IssueCode.LOW_RESOLUTION for i in rep.blocking)


def test_no_face_blocks():
    # MediaPipe *did* load and simply found no face → hard block.
    with (
        patch.object(iq, "_detect_faces", return_value=[]),
        patch.object(iq, "_mp_available", True),
    ):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    assert rep.can_generate is False
    assert any(i.code == IssueCode.NO_FACE for i in rep.blocking)


def test_no_face_fail_soft_when_mediapipe_unavailable():
    """B2 fail-soft: if MediaPipe itself can't load, we must not hard-block
    every user with NO_FACE. The VLM quality gate re-checks identity after
    generation, so a degraded detector only costs us a pre-flight filter."""
    with (
        patch.object(iq, "_detect_faces", return_value=[]),
        patch.object(iq, "_mp_available", False),
    ):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    assert rep.can_generate is True, "must not hard-block when MP is unavailable"
    assert not rep.blocking
    assert any(i.code == IssueCode.FACE_DETECTOR_UNAVAILABLE for i in rep.soft_warnings)


def test_tiny_face_blocks():
    # Face occupies ~2% of the frame → below min_face_area_ratio=0.04
    face = _mock_face(bbox=(390, 390, 490, 490))
    with patch.object(iq, "_detect_faces", return_value=[face]):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    assert rep.can_generate is False
    assert any(i.code == IssueCode.FACE_TOO_SMALL for i in rep.blocking)


def test_multiple_faces_blocks():
    primary = _mock_face(bbox=(100, 100, 400, 400), det=0.95)
    secondary = _mock_face(bbox=(500, 100, 780, 400), det=0.90)
    with patch.object(iq, "_detect_faces", return_value=[primary, secondary]):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    assert rep.can_generate is False
    assert any(i.code == IssueCode.MULTIPLE_FACES for i in rep.blocking)


def test_blurry_full_blocks():
    # Flat grey image → Laplacian variance ~ 0 → blur_full < 60
    with patch.object(iq, "_detect_faces", return_value=[_mock_face()]):
        rep = iq.analyze_input_quality(_rgb_bytes(800, 800))
    assert rep.can_generate is False
    assert any(i.code == IssueCode.BLURRY_PHOTO for i in rep.blocking)


# ---------------------------------------------------------------------------
# Soft warnings
# ---------------------------------------------------------------------------


def test_non_frontal_soft_warning():
    face = _mock_face(bbox=(200, 200, 600, 600), pose=(0.0, 45.0, 0.0))  # yaw=45°
    with patch.object(iq, "_detect_faces", return_value=[face]):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    assert rep.can_generate is True
    assert any(i.code == IssueCode.NOT_FRONTAL for i in rep.soft_warnings)


def test_off_center_soft_warning():
    # Face near right edge of frame.
    face = _mock_face(bbox=(600, 200, 790, 390))
    with patch.object(iq, "_detect_faces", return_value=[face]):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    # offset > 0.35 → FACE_OFF_CENTER
    assert any(i.code == IssueCode.FACE_OFF_CENTER for i in rep.soft_warnings)


def test_small_face_soft_warning():
    # Face occupies ~6% of frame — between block (4%) and warn (10%) thresholds.
    # ~200x200 face in 800x800 frame = 0.0625
    face = _mock_face(bbox=(300, 300, 500, 500))
    with patch.object(iq, "_detect_faces", return_value=[face]):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    assert rep.can_generate is True
    assert any(i.code == IssueCode.FACE_SMALL_WARN for i in rep.soft_warnings)


def test_clean_face_no_issues():
    # Large centered face on noisy (sharp) background, frontal pose.
    face = _mock_face(bbox=(100, 100, 700, 700))
    with patch.object(iq, "_detect_faces", return_value=[face]):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    assert rep.can_generate is True
    assert rep.blocking == []


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------


def test_to_public_dict_shape():
    rep = iq.InputQualityReport(
        can_generate=True,
        issues=[
            iq.InputQualityIssue("face_small_warn", "warn", "msg", "hint"),
        ],
    )
    data = rep.to_public_dict()
    assert data["can_generate"] is True
    assert len(data["soft_warnings"]) == 1
    assert data["soft_warnings"][0]["code"] == "face_small_warn"
    assert data["blocking_issues"] == []


def test_to_prompt_hints_roundtrip():
    rep = iq.InputQualityReport(
        can_generate=True,
        face_area_ratio=0.08,
        yaw=30.0,
        hair_bg_contrast=0.05,
    )
    h = rep.to_prompt_hints()
    assert h["face_area_ratio"] == 0.08
    assert h["yaw"] == 30.0
    assert h["hair_bg_contrast"] == 0.05


# ---------------------------------------------------------------------------
# Composition Safety Layer (CSL) integration
# ---------------------------------------------------------------------------


def test_face_closeup_is_classified_and_exposed_publicly():
    # Very large centered face → CSL heuristic should classify as FACE_CLOSEUP.
    face = _mock_face(bbox=(100, 100, 700, 700))  # 600×600 in 800×800 frame
    with patch.object(iq, "_detect_faces", return_value=[face]):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    assert rep.composition_class == "face_closeup"
    assert rep.allowed_framings == ["portrait"]

    public = rep.to_public_dict()
    assert public["composition_class"] == "face_closeup"
    assert public["allowed_framings"] == ["portrait"]


def test_half_body_input_unlocks_full_body_framing():
    # Small-ish face high in a tall frame → plenty of body room below.
    # face_h = 200, image_h = 1200, fy2 = 400 → space_below ≈ 4.0 face-heights.
    face = _mock_face(bbox=(200, 200, 600, 400))
    with patch.object(iq, "_detect_faces", return_value=[face]):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 1200))
    # The exact class depends on calibration but it must NOT collapse to
    # face_closeup and MUST permit at least portrait + half_body.
    assert rep.composition_class != "face_closeup"
    assert "portrait" in rep.allowed_framings
    assert "half_body" in rep.allowed_framings


def test_invalid_input_falls_back_to_unknown_composition():
    rep = iq.analyze_input_quality(b"not an image")
    assert rep.composition_class == "unknown"
    # Fail-closed safe: UNKNOWN must restrict the user to portrait only.
    assert rep.allowed_framings == ["portrait"]


def test_no_face_keeps_composition_unknown():
    with (
        patch.object(iq, "_detect_faces", return_value=[]),
        patch.object(iq, "_mp_available", True),
    ):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    assert rep.composition_class == "unknown"
    assert rep.allowed_framings == ["portrait"]


class _FakeSpec:
    def __init__(self, *, needs_full_body: bool = False, needs_torso: bool = False) -> None:
        self.needs_full_body = needs_full_body
        self.needs_torso = needs_torso


class _FakeRegistry:
    def __init__(self, spec) -> None:
        self._spec = spec

    def get(self, _mode: str, _key: str):
        return self._spec


def test_check_style_reference_compat_blocks_full_body_on_face_closeup(monkeypatch):
    spec = _FakeSpec(needs_full_body=True, needs_torso=True)
    monkeypatch.setattr(
        "src.prompts.image_gen.STYLE_REGISTRY",
        _FakeRegistry(spec),
        raising=True,
    )
    issue = iq.check_style_reference_compat(
        face_area_ratio=0.5,
        mode="dating",
        style_key="any_full_body_style",
        composition_class="face_closeup",
    )
    assert issue is not None
    assert issue.code == IssueCode.STYLE_FORBIDDEN_FOR_COMPOSITION
    assert issue.severity == "block"


def test_check_style_reference_compat_warns_for_torso_on_face_closeup(monkeypatch):
    spec = _FakeSpec(needs_full_body=False, needs_torso=True)
    monkeypatch.setattr(
        "src.prompts.image_gen.STYLE_REGISTRY",
        _FakeRegistry(spec),
        raising=True,
    )
    issue = iq.check_style_reference_compat(
        face_area_ratio=0.5,
        mode="dating",
        style_key="torso_style",
        composition_class="face_closeup",
    )
    assert issue is not None
    assert issue.code == IssueCode.STYLE_RISKY_FOR_COMPOSITION
    assert issue.severity == "warn"


def test_check_style_reference_compat_allows_full_body_for_full_body_input(monkeypatch):
    spec = _FakeSpec(needs_full_body=True, needs_torso=True)
    monkeypatch.setattr(
        "src.prompts.image_gen.STYLE_REGISTRY",
        _FakeRegistry(spec),
        raising=True,
    )
    issue = iq.check_style_reference_compat(
        face_area_ratio=0.05,
        mode="dating",
        style_key="any_full_body_style",
        composition_class="full_body",
    )
    assert issue is None


def test_check_style_reference_compat_falls_back_to_face_ratio_heuristic(monkeypatch):
    """When composition_class is not provided (legacy callers), the
    original face_area_ratio heuristic must still catch tight closeups
    on full-body styles."""
    spec = _FakeSpec(needs_full_body=True, needs_torso=False)
    monkeypatch.setattr(
        "src.prompts.image_gen.STYLE_REGISTRY",
        _FakeRegistry(spec),
        raising=True,
    )
    issue = iq.check_style_reference_compat(
        face_area_ratio=iq.FACE_TOO_TIGHT_FOR_BODY_THRESHOLD + 0.05,
        mode="dating",
        style_key="any_full_body_style",
        composition_class=None,
    )
    assert issue is not None
    assert issue.code == IssueCode.FACE_TOO_TIGHT_FOR_BODY_SHOT
    assert issue.severity == "warn"


def test_check_style_reference_compat_unknown_class_is_fail_closed(monkeypatch):
    """Sanity: explicitly passing ``composition_class='unknown'`` must
    fail-closed (block full-body styles) — the CSL design treats UNKNOWN
    as the same risk class as FACE_CLOSEUP."""
    spec = _FakeSpec(needs_full_body=True, needs_torso=True)
    monkeypatch.setattr(
        "src.prompts.image_gen.STYLE_REGISTRY",
        _FakeRegistry(spec),
        raising=True,
    )
    issue = iq.check_style_reference_compat(
        face_area_ratio=0.05,
        mode="dating",
        style_key="any_full_body_style",
        composition_class="unknown",
    )
    assert issue is not None
    assert issue.code == IssueCode.STYLE_FORBIDDEN_FOR_COMPOSITION
    assert issue.severity == "block"
