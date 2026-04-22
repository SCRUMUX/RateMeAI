"""Unit tests for :func:`crop_face_for_pulid` and fallback reasons."""
from __future__ import annotations

import io

from PIL import Image

from src.services.face_crop import (
    FaceCropReason,
    crop_face_for_pulid,
)
from src.services.input_quality import _MPFace


def _jpeg_bytes(size: int = 512, color=(180, 180, 180)) -> bytes:
    img = Image.new("RGB", (size, size), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _mock_face(x1: int, y1: int, x2: int, y2: int, score: float = 0.95) -> _MPFace:
    return _MPFace(
        bbox=(x1, y1, x2, y2),
        det_score=score,
        keypoints={},
    )


def test_empty_input_returns_invalid_image():
    result = crop_face_for_pulid(b"")
    assert result.image_bytes is None
    assert result.reason == FaceCropReason.INVALID_IMAGE


def test_undecodable_input_returns_invalid_image():
    result = crop_face_for_pulid(b"not a jpeg")
    assert result.image_bytes is None
    assert result.reason == FaceCropReason.INVALID_IMAGE


def test_no_face_detected_returns_no_face_reason(monkeypatch):
    monkeypatch.setattr(
        "src.services.face_crop._detect_faces",
        lambda arr: [],
    )
    result = crop_face_for_pulid(_jpeg_bytes(size=512))
    assert result.image_bytes is None
    assert result.reason == FaceCropReason.NO_FACE


def test_success_returns_square_jpeg_at_target_size(monkeypatch):
    face = _mock_face(100, 100, 300, 300)
    monkeypatch.setattr(
        "src.services.face_crop._detect_faces",
        lambda arr: [face],
    )
    out = crop_face_for_pulid(
        _jpeg_bytes(size=512),
        target_size=256,
    )
    assert out.image_bytes is not None
    assert out.reason == FaceCropReason.OK
    assert out.width == 256
    assert out.height == 256

    img = Image.open(io.BytesIO(out.image_bytes))
    assert img.size == (256, 256)
    assert img.format == "JPEG"


def test_tiny_image_with_tiny_face_returns_face_too_small(monkeypatch):
    face = _mock_face(0, 0, 32, 32)
    monkeypatch.setattr(
        "src.services.face_crop._detect_faces",
        lambda arr: [face],
    )
    out = crop_face_for_pulid(
        _jpeg_bytes(size=96),
        min_face_side_px=256,
    )
    assert out.image_bytes is None
    assert out.reason == FaceCropReason.FACE_TOO_SMALL


def test_picks_largest_face_when_multiple(monkeypatch):
    small = _mock_face(0, 0, 40, 40, score=0.99)
    large = _mock_face(100, 100, 400, 400, score=0.80)
    monkeypatch.setattr(
        "src.services.face_crop._detect_faces",
        lambda arr: [small, large],
    )
    out = crop_face_for_pulid(
        _jpeg_bytes(size=512),
        target_size=128,
    )
    assert out.image_bytes is not None
    assert out.face_area_ratio > 0.2  # large face dominates the frame


def test_degenerate_bbox_returns_no_face(monkeypatch):
    zero = _mock_face(10, 10, 10, 10)
    monkeypatch.setattr(
        "src.services.face_crop._detect_faces",
        lambda arr: [zero],
    )
    result = crop_face_for_pulid(_jpeg_bytes(size=512))
    assert result.image_bytes is None
    assert result.reason == FaceCropReason.NO_FACE
