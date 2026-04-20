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
    with patch.object(iq, "_detect_faces", return_value=[]):
        rep = iq.analyze_input_quality(_sharp_noise_bytes(800, 800))
    assert rep.can_generate is False
    assert any(i.code == IssueCode.NO_FACE for i in rep.blocking)


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
