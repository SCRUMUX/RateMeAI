"""v1.68 P3.11 — snapshot test of pad_reference_for_framing with
MediaPipe re-detection.

The plan calls for an end-to-end regression guard: given a known
input image and bbox, run the padder, then re-run MediaPipe face
detection on the padded output and assert the resulting face is
within tight tolerance of the target geometry described in
``_FRAMING_GEOMETRY``.

Why we re-run MediaPipe here and not just probe pixels:
the existing :mod:`tests.test_services.test_pad_reference_geometry`
already probes pixels for a synthetic colour-rectangle face. That
catches *geometric* regressions but not *detection-grade*
regressions — i.e. a future change that subtly distorts the face
crop in a way pixel sampling does not catch could still degrade
real MediaPipe detection in production. Re-detection closes that
loop.

MediaPipe is part of the production requirements (see
``requirements.txt``), so this test runs on CI. Local Windows
installs that don't carry MediaPipe simply skip the test —
``pytest.importorskip`` rather than a hard fail keeps the local
dev loop fast.

The synthetic face used here is the same colour-rectangle / blurred
background construction as in ``test_pad_reference_geometry.py`` —
MediaPipe's BlazeFace short-range model picks up the skin-coloured
rectangle reliably enough at 640×640 to be a valid stand-in for a
photographic face, without dragging a binary JPEG fixture into the
repo.
"""

from __future__ import annotations

import io

import pytest

mp = pytest.importorskip("mediapipe", reason="MediaPipe not installed")
np = pytest.importorskip("numpy", reason="numpy not installed")
from PIL import Image, ImageFilter  # noqa: E402

from src.services.reference_preprocess import (  # noqa: E402
    _FRAMING_GEOMETRY,
    pad_reference_for_framing,
)


# ---------------------------------------------------------------------------
# Synthetic input.
# ---------------------------------------------------------------------------


def _build_synthetic_face_image(
    *,
    width: int = 640,
    height: int = 640,
    face_bbox: tuple[int, int, int, int],
    face_colour: tuple[int, int, int] = (212, 175, 145),
) -> bytes:
    """Return a JPEG containing a skin-coloured rectangle on a blurred
    pastel background. The rectangle is what MediaPipe detects.
    """
    img = Image.new("RGB", (width, height), color=(180, 195, 220))
    img = img.filter(ImageFilter.GaussianBlur(radius=8.0))

    pixels = img.load()
    x1, y1, x2, y2 = face_bbox
    for x in range(x1, x2):
        for y in range(y1, y2):
            if 0 <= x < width and 0 <= y < height:
                pixels[x, y] = face_colour

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _detect_face_bbox_mediapipe(raw: bytes) -> tuple[int, int, int, int]:
    """Run MediaPipe face detection on raw JPEG bytes; return the
    bounding box in ``(x1, y1, x2, y2)`` format (same convention as
    :func:`src.services.input_quality.analyze_input_quality`).

    Returns the highest-confidence face. Raises if no face is
    detected — the test skip should already handle the "no
    MediaPipe" case; "MediaPipe is here but didn't pick up the
    synthetic face" is a genuine failure.
    """
    arr = np.array(Image.open(io.BytesIO(raw)).convert("RGB"))
    h, w = arr.shape[:2]

    detector = mp.solutions.face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=0.5
    )
    try:
        result = detector.process(arr)
    finally:
        detector.close()
    if not result.detections:
        raise AssertionError(
            "MediaPipe did not detect the synthetic face on the padded "
            "output. Either the padder corrupted it beyond recognition, "
            "or MediaPipe is failing silently."
        )
    best = max(
        result.detections,
        key=lambda d: d.score[0] if d.score else 0.0,
    )
    rb = best.location_data.relative_bounding_box
    x1 = max(0, int(rb.xmin * w))
    y1 = max(0, int(rb.ymin * h))
    x2 = min(w, int((rb.xmin + rb.width) * w))
    y2 = min(h, int((rb.ymin + rb.height) * h))
    return x1, y1, x2, y2


# ---------------------------------------------------------------------------
# Snapshot tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_padded_face_lands_at_target_geometry(framing: str):
    """End-to-end snapshot: feed a known input, pad it, re-detect,
    and assert the resulting face sits where ``_FRAMING_GEOMETRY``
    says it should.

    Tolerances:
      * Face centre Y-position: ±5% of canvas height. MediaPipe
        BlazeFace's bbox is slightly tighter than the original
        rectangle, so a strict 2% bound would be flaky.
      * Face height ratio: ±0.04 absolute. Same reason — BlazeFace
        crops the chin a bit.
    """
    raw = _build_synthetic_face_image(face_bbox=(220, 240, 420, 440))
    padded = pad_reference_for_framing(
        raw,
        face_bbox=(220, 240, 420, 440),
        framing=framing,
    )
    detected = _detect_face_bbox_mediapipe(padded)
    img = Image.open(io.BytesIO(padded))
    canvas_w, canvas_h = img.size

    fx1, fy1, fx2, fy2 = detected
    detected_cy = (fy1 + fy2) / 2.0
    detected_h = fy2 - fy1

    target = _FRAMING_GEOMETRY[framing]
    expected_cy = canvas_h * target["face_center_y_ratio"]

    cy_ratio_delta = abs(detected_cy - expected_cy) / canvas_h
    h_ratio_delta = abs((detected_h / canvas_h) - target["face_height_ratio"])

    assert cy_ratio_delta < 0.05, (
        f"framing={framing!r}: detected face centre Y "
        f"{detected_cy / canvas_h:.3f} differs from target "
        f"{target['face_center_y_ratio']:.3f} by {cy_ratio_delta:.3f}; "
        "padder geometry has drifted."
    )
    assert h_ratio_delta < 0.04, (
        f"framing={framing!r}: detected face height ratio "
        f"{detected_h / canvas_h:.3f} differs from target "
        f"{target['face_height_ratio']:.3f} by {h_ratio_delta:.3f}; "
        "padder height-scaling has drifted."
    )
