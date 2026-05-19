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

The input image is the bundled 256×256 StyleGAN portrait used by
the existing ``/diagnostics/image-gen-probe`` CI workflow (see
:mod:`src.api.v1._fixtures.probe_face`). Reusing it keeps the test
suite hermetic — no external assets, no real-person privacy
concerns, and the same face MediaPipe is exercised on in production
diagnostics.
"""

from __future__ import annotations

import io

import pytest

mp = pytest.importorskip("mediapipe", reason="MediaPipe not installed")
np = pytest.importorskip("numpy", reason="numpy not installed")
from PIL import Image  # noqa: E402

from src.api.v1._fixtures.probe_face import probe_face_jpeg  # noqa: E402
from src.services.reference_preprocess import (  # noqa: E402
    _FRAMING_GEOMETRY,
    pad_reference_for_framing,
)


# ---------------------------------------------------------------------------
# Test fixture — the bundled 256×256 StyleGAN portrait.
# ---------------------------------------------------------------------------
#
# Reusing :func:`probe_face_jpeg` from the existing diagnostics
# fixture keeps the test suite hermetic (no external assets, no
# real-person privacy concerns — the image is a CC0
# ``thispersondoesnotexist`` sample) and consistent with the rest of
# the CI probe matrix. We do NOT hard-code a source bbox — instead
# we first run MediaPipe on the raw fixture to extract its bbox,
# pad with that, then re-detect on the padded output. This makes
# the test resilient to any future bbox-tightening change in the
# detector itself.


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


# Per-framing tolerances. The portrait / half_body cases are tight
# because the rescaled face is large enough that detector
# uncertainty is sub-pixel. The full_body case rescales the source
# face down to ~128 px on a 1600 px canvas; at that size MediaPipe's
# bounding box can drift by a few percent of canvas height even on
# the same face — so we use a looser bound there. The full_body
# pathway is also covered by the synthetic pixel-sampling test in
# ``test_pad_reference_geometry.py`` which checks the same geometry
# without depending on detector behaviour at small scales.
_TOLERANCE_BY_FRAMING: dict[str, tuple[float, float]] = {
    # framing → (cy_ratio_max_delta, height_ratio_max_delta)
    "portrait":  (0.05, 0.04),
    "half_body": (0.07, 0.05),
    "full_body": (0.20, 0.10),
}


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_padded_face_lands_at_target_geometry(framing: str):
    """End-to-end snapshot: feed a known input, pad it, re-detect,
    and assert the resulting face sits where ``_FRAMING_GEOMETRY``
    says it should — within a per-framing tolerance band.
    """
    raw = probe_face_jpeg()
    source_bbox = _detect_face_bbox_mediapipe(raw)
    padded = pad_reference_for_framing(
        raw,
        face_bbox=source_bbox,
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

    cy_tol, h_tol = _TOLERANCE_BY_FRAMING[framing]
    assert cy_ratio_delta < cy_tol, (
        f"framing={framing!r}: detected face centre Y "
        f"{detected_cy / canvas_h:.3f} differs from target "
        f"{target['face_center_y_ratio']:.3f} by {cy_ratio_delta:.3f} "
        f"(tolerance {cy_tol:.3f}); padder geometry has drifted."
    )
    assert h_ratio_delta < h_tol, (
        f"framing={framing!r}: detected face height ratio "
        f"{detected_h / canvas_h:.3f} differs from target "
        f"{target['face_height_ratio']:.3f} by {h_ratio_delta:.3f} "
        f"(tolerance {h_tol:.3f}); padder height-scaling has drifted."
    )
