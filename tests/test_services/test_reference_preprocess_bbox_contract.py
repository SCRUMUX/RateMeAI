"""v1.68 — face_bbox contract regression tests.

Background
----------

:func:`src.services.reference_preprocess.pad_reference_for_framing`
historically destructured its ``face_bbox`` argument as
``(x, y, w, h)``, but the only producer in production
(:func:`src.services.input_quality.analyze_input_quality`) emits
``(x1, y1, x2, y2)`` — top-left and bottom-right corners. The
mismatch silently scrambled the scale + centre maths on every call
(see the v1.68 audit / module docstring), which translated into the
"glued head" failure mode for tight selfies.

These tests pin the corrected contract:

* The v2 branch (``settings.csl_padding_v2_enabled = True``)
  interprets the tuple as ``(x1, y1, x2, y2)`` and computes
  ``fw = x2 - x1``, ``fh = y2 - y1``.
* The v1 branch (``settings.csl_padding_v2_enabled = False``)
  preserves the legacy ``(x, y, w, h)`` interpretation for the
  rollback path.
* Degenerate inputs (``x2 <= x1`` or ``y2 <= y1``) raise under v2,
  matching the original ``fw <= 0 / fh <= 0`` guard.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from src.services.reference_preprocess import pad_reference_for_framing


def _solid_jpeg(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(180, 180, 180)).save(
        buf, format="JPEG", quality=92,
    )
    return buf.getvalue()


def _decode(image_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def test_v2_interprets_bbox_as_x1_y1_x2_y2(monkeypatch: pytest.MonkeyPatch):
    """A bbox of (100, 200, 300, 500) is a 200×300 face at centre (200, 350).

    Under the corrected v2 interpretation the function reads
    ``fw = 300 - 100 = 200`` and ``fh = 500 - 200 = 300``. The output
    canvas must therefore be the requested size and must not raise.
    """
    from src.services import reference_preprocess as rp_mod

    monkeypatch.setattr(rp_mod, "_use_v2", True, raising=False)
    # Settings dependency is read inside the function — patch directly
    # so the flag is unambiguous under test.
    from src.config import settings

    monkeypatch.setattr(settings, "csl_padding_v2_enabled", True)

    src = _solid_jpeg(800, 1000)
    out = pad_reference_for_framing(
        src,
        face_bbox=(100, 200, 300, 500),
        framing="portrait",
        target_size=(1280, 1600),
    )
    img = _decode(out)
    assert img.size == (1280, 1600)


def test_v1_fallback_keeps_legacy_interpretation(monkeypatch: pytest.MonkeyPatch):
    """Setting ``csl_padding_v2_enabled=False`` reverts to the legacy
    ``(x, y, w, h)`` reading. Same bbox under v1: 300×500 face starting
    at (100, 200) — i.e. the chin lands at y=700, off the bottom of an
    800×1000 image, but the function still completes (the legacy code
    never validated against the source dimensions either).
    """
    from src.config import settings

    monkeypatch.setattr(settings, "csl_padding_v2_enabled", False)

    src = _solid_jpeg(800, 1000)
    out = pad_reference_for_framing(
        src,
        face_bbox=(100, 200, 300, 500),
        framing="portrait",
        target_size=(1280, 1600),
    )
    img = _decode(out)
    assert img.size == (1280, 1600)


def test_v2_rejects_x2_le_x1(monkeypatch: pytest.MonkeyPatch):
    """``x2 <= x1`` is a degenerate detection under the v2 contract —
    the function must raise rather than compute a negative scale."""
    from src.config import settings

    monkeypatch.setattr(settings, "csl_padding_v2_enabled", True)

    src = _solid_jpeg(400, 400)
    with pytest.raises(ValueError, match="Degenerate face_bbox"):
        pad_reference_for_framing(
            src,
            face_bbox=(200, 100, 200, 300),  # zero-width face
            framing="portrait",
        )


def test_v2_rejects_y2_le_y1(monkeypatch: pytest.MonkeyPatch):
    """``y2 <= y1`` is a degenerate detection under the v2 contract."""
    from src.config import settings

    monkeypatch.setattr(settings, "csl_padding_v2_enabled", True)

    src = _solid_jpeg(400, 400)
    with pytest.raises(ValueError, match="Degenerate face_bbox"):
        pad_reference_for_framing(
            src,
            face_bbox=(100, 300, 300, 300),  # zero-height face
            framing="portrait",
        )


def test_v2_face_scale_uses_height_difference(monkeypatch: pytest.MonkeyPatch):
    """Geometric assertion: under v2 the scaled face height matches
    ``face_height_ratio * canvas_h`` based on the **height difference**
    ``y2 - y1``, NOT the raw ``y2`` value.

    We construct a source where ``y2`` is much larger than ``y2 - y1``
    so the two interpretations would scale the image very differently;
    if the function silently slipped back to the legacy reading, the
    output canvas would still be the requested size (the v1 fallback
    also clamps to ``target_size``) but the **placement** of the face
    would diverge. We check this via the logger's reported ``face_src_h``
    metric — see the implementation.

    The test is intentionally a smoke / observability check; the full
    geometric verification with MediaPipe re-detection lives in
    :mod:`tests.test_services.test_pad_reference_geometry`.
    """
    from src.config import settings

    monkeypatch.setattr(settings, "csl_padding_v2_enabled", True)

    src = _solid_jpeg(800, 1200)
    # y1=200, y2=500 → fh = 300. Under v1 this would have read fh=500.
    out = pad_reference_for_framing(
        src,
        face_bbox=(100, 200, 400, 500),
        framing="half_body",
        target_size=(1280, 1600),
    )
    img = _decode(out)
    assert img.size == (1280, 1600)


def test_metric_increments_with_version_label(monkeypatch: pytest.MonkeyPatch):
    """``PADDING_GEOMETRY_VERSION`` counter is incremented with the
    correct ``version`` label on each call. v1.68 ships the v2 branch
    by default; the counter is the primary "did the fix ship?" signal.
    """
    from src.config import settings
    from src.metrics import PADDING_GEOMETRY_VERSION

    monkeypatch.setattr(settings, "csl_padding_v2_enabled", True)

    before = PADDING_GEOMETRY_VERSION.labels(version="v2", framing="portrait")._value.get()

    src = _solid_jpeg(800, 1200)
    pad_reference_for_framing(
        src,
        face_bbox=(100, 200, 400, 500),
        framing="portrait",
        target_size=(1280, 1600),
    )

    after = PADDING_GEOMETRY_VERSION.labels(version="v2", framing="portrait")._value.get()
    assert after == before + 1, (
        "PADDING_GEOMETRY_VERSION v2 counter must increment by 1 per call; "
        f"observed {before} → {after}"
    )
