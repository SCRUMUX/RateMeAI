"""Tests for SegmentationService (mediapipe and InsightFace mocked)."""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from src.services.segmentation import SegmentationService


def _make_image_bytes(w=200, h=200) -> bytes:
    img = Image.new("RGB", (w, h), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_fake_selfie_result(h=200, w=200):
    result = MagicMock()
    result.segmentation_mask = np.ones((h, w), dtype=np.float32) * 0.8
    return result


@patch("src.services.segmentation._face_bbox_mask")
@patch("src.services.segmentation._get_selfie_segmentor")
def test_segment_returns_all_masks(mock_seg, mock_face):
    mock_seg_instance = MagicMock()
    mock_seg_instance.process.return_value = _make_fake_selfie_result()
    mock_seg.return_value = mock_seg_instance

    face_mask = Image.new("L", (200, 200), 200)
    mock_face.return_value = face_mask

    svc = SegmentationService()
    masks = svc._segment_sync(_make_image_bytes())

    assert "face" in masks
    assert "body" in masks
    assert "background" in masks
    assert "clothing" in masks
    assert "full" in masks

    for name, mask in masks.items():
        assert isinstance(mask, Image.Image)
        assert mask.mode == "L"
        assert mask.size == (200, 200)


@patch("src.services.segmentation._face_bbox_mask", return_value=None)
@patch("src.services.segmentation._get_selfie_segmentor")
def test_segment_without_face_detection(mock_seg, mock_face):
    mock_seg_instance = MagicMock()
    mock_seg_instance.process.return_value = _make_fake_selfie_result()
    mock_seg.return_value = mock_seg_instance

    svc = SegmentationService()
    masks = svc._segment_sync(_make_image_bytes())

    assert masks["face"].getextrema() == (0, 0)
    assert masks["clothing"] is not None


@patch("src.services.segmentation._face_bbox_mask")
@patch("src.services.segmentation._get_selfie_segmentor")
def test_full_mask_is_all_white(mock_seg, mock_face):
    mock_seg_instance = MagicMock()
    mock_seg_instance.process.return_value = _make_fake_selfie_result()
    mock_seg.return_value = mock_seg_instance
    mock_face.return_value = Image.new("L", (200, 200), 0)

    svc = SegmentationService()
    masks = svc._segment_sync(_make_image_bytes())

    full_arr = np.array(masks["full"])
    assert full_arr.min() == 255 and full_arr.max() == 255
