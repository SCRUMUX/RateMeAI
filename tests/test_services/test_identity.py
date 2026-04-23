"""Tests for IdentityService (MediaPipe-based face presence only).

Privacy note: as of the v1.10 privacy overhaul, IdentityService no longer
computes or stores face embeddings. It only exposes ``detect_face`` and
``face_bbox`` using MediaPipe FaceDetection. Identity preservation is
verified by the quality-gate VLM (see test_quality_gates.py).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.services.identity import IdentityService


class _FakeDetection:
    def __init__(self, score: float, bbox=(0.1, 0.1, 0.5, 0.5)):
        self.score = [score]
        ld = MagicMock()
        ld.relative_bounding_box.xmin = bbox[0]
        ld.relative_bounding_box.ymin = bbox[1]
        ld.relative_bounding_box.width = bbox[2]
        ld.relative_bounding_box.height = bbox[3]
        self.location_data = ld


@patch("src.services.identity._get_detector")
def test_detect_face_returns_true_when_detection_present(mock_get_detector):
    detector = MagicMock()
    detector.process.return_value = MagicMock(detections=[_FakeDetection(0.95)])
    mock_get_detector.return_value = detector

    svc = IdentityService()
    # 1x1 RGB PNG header is enough because we mock the detector
    import io
    from PIL import Image

    img = Image.new("RGB", (10, 10), "red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert svc.detect_face(buf.getvalue()) is True


@patch("src.services.identity._get_detector")
def test_detect_face_returns_false_when_no_detections(mock_get_detector):
    detector = MagicMock()
    detector.process.return_value = MagicMock(detections=[])
    mock_get_detector.return_value = detector

    svc = IdentityService()
    import io
    from PIL import Image

    img = Image.new("RGB", (10, 10), "red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert svc.detect_face(buf.getvalue()) is False


@patch("src.services.identity._get_detector")
def test_detect_face_false_when_detector_unavailable(mock_get_detector):
    mock_get_detector.return_value = None

    svc = IdentityService()
    assert svc.detect_face(b"any_bytes") is False


@patch("src.services.identity._get_detector")
def test_face_bbox_returns_coords_of_best_detection(mock_get_detector):
    detector = MagicMock()
    detector.process.return_value = MagicMock(
        detections=[
            _FakeDetection(0.5, bbox=(0.05, 0.05, 0.1, 0.1)),
            _FakeDetection(0.95, bbox=(0.2, 0.25, 0.4, 0.5)),
        ]
    )
    mock_get_detector.return_value = detector

    svc = IdentityService()
    import io
    from PIL import Image

    img = Image.new("RGB", (100, 100), "blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    bbox = svc.face_bbox(buf.getvalue())
    assert bbox is not None
    x1, y1, x2, y2 = bbox
    assert x1 == 20 and y1 == 25
    assert x2 == 60 and y2 == 75


@patch("src.services.identity._get_detector")
def test_face_bbox_returns_none_when_no_face(mock_get_detector):
    detector = MagicMock()
    detector.process.return_value = MagicMock(detections=[])
    mock_get_detector.return_value = detector

    svc = IdentityService()
    import io
    from PIL import Image

    img = Image.new("RGB", (100, 100), "blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert svc.face_bbox(buf.getvalue()) is None


def test_service_has_no_embedding_methods():
    """Regression: legacy biometric methods must be gone."""
    svc = IdentityService()
    assert not hasattr(svc, "compute_embedding")
    assert not hasattr(svc, "compare")
    assert not hasattr(svc, "verify")
