"""v1.68 — pad_reference_for_framing geometric placement contract.

The padding operation has TWO targets:

* ``face_height_ratio * canvas_h`` — face fills the right share of
  the canvas height.
* ``face_center_y_ratio * canvas_h`` — face centre lands at the
  expected y-coordinate.

Both are read out of
:data:`src.services.reference_preprocess._FRAMING_GEOMETRY`. The
tests below use a synthetic "face" rendered as a coloured rectangle
on a neutral background — we then sample the centre of the
post-padding output and infer whether the face landed at the right
y-coordinate.

This guards against silent regressions: a future refactor of the
padding math that breaks placement geometry (e.g. swaps centre and
top, or applies the wrong axis ratio) would still produce a canvas
of the requested size — only the relative placement would shift, and
nothing else in the suite would catch that.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from src.services.reference_preprocess import (
    _FRAMING_GEOMETRY,
    pad_reference_for_framing,
)


def _synthetic_portrait(
    canvas_w: int,
    canvas_h: int,
    face_box: tuple[int, int, int, int],
    face_color: tuple[int, int, int] = (220, 80, 60),
    background_color: tuple[int, int, int] = (60, 60, 60),
) -> bytes:
    """Render a fake portrait: a coloured rectangle (= the "face") on
    a contrasting background, returned as JPEG bytes.

    ``face_box`` is ``(x1, y1, x2, y2)`` — the same format the real
    pipeline produces.
    """
    img = Image.new("RGB", (canvas_w, canvas_h), color=background_color)
    x1, y1, x2, y2 = face_box
    face = Image.new("RGB", (x2 - x1, y2 - y1), color=face_color)
    img.paste(face, (x1, y1))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _color_distance(
    sample: tuple[int, int, int],
    target: tuple[int, int, int],
) -> float:
    return sum((s - t) ** 2 for s, t in zip(sample, target)) ** 0.5


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_face_lands_at_target_y_under_v2(
    framing: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """The face centre of the padded canvas should land at
    ``face_center_y_ratio * canvas_h``.

    We render a vividly-coloured "face" rectangle, run it through the
    padding pipeline, then probe the canvas at the expected y to
    confirm the foreground face-coloured pixels actually live there.

    Threshold is strict (distance < 25) so only the un-blurred
    foreground rectangle matches — the edge-blurred background copy
    has the face colour smeared and falls outside this threshold.
    """
    from src.config import settings

    monkeypatch.setattr(settings, "csl_padding_v2_enabled", True)

    canvas_w, canvas_h = 1280, 1600
    geom = _FRAMING_GEOMETRY[framing]
    expected_cy = int(canvas_h * geom["face_center_y_ratio"])

    src_w, src_h = 600, 800
    face_box = (200, 250, 400, 450)  # 200×200 face at centre (300, 350)
    face_color = (220, 80, 60)
    background_color = (40, 40, 40)
    src = _synthetic_portrait(
        src_w, src_h, face_box,
        face_color=face_color,
        background_color=background_color,
    )

    out = pad_reference_for_framing(
        src,
        face_bbox=face_box,
        framing=framing,
        target_size=(canvas_w, canvas_h),
    )
    img = Image.open(io.BytesIO(out)).convert("RGB")
    assert img.size == (canvas_w, canvas_h)

    # Probe at the canvas centre line; the face is centred in the
    # source so paste_x ≈ canvas centre.
    sample_x = canvas_w // 2
    sample = img.getpixel((sample_x, expected_cy))
    distance = _color_distance(sample, face_color)
    assert distance < 25.0, (
        f"framing={framing!r}: expected pure face colour at (x={sample_x}, "
        f"y={expected_cy}) within distance 25 of {face_color}; got "
        f"sample={sample} (distance={distance:.1f}). Either the paste "
        "geometry diverged or the foreground face is no longer placed "
        "at face_center_y_ratio."
    )


@pytest.mark.parametrize("framing", ["portrait", "half_body", "full_body"])
def test_face_height_ratio_under_v2(
    framing: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """The padded canvas places the face at approximately
    ``face_height_ratio * canvas_h`` pixels tall.

    We probe at the expected top and bottom of the face (centre Y
    ± half the target height) and confirm the foreground face
    rectangle covers those positions. The blurred background can
    contain face-coloured pixels at other y positions, but it
    cannot ride on top of the foreground at the expected centre.
    """
    from src.config import settings

    monkeypatch.setattr(settings, "csl_padding_v2_enabled", True)

    canvas_w, canvas_h = 1280, 1600
    geom = _FRAMING_GEOMETRY[framing]
    expected_face_h = int(canvas_h * geom["face_height_ratio"])
    expected_cy = int(canvas_h * geom["face_center_y_ratio"])

    src_w, src_h = 600, 800
    face_box = (200, 250, 400, 450)
    face_color = (220, 80, 60)
    src = _synthetic_portrait(
        src_w, src_h, face_box, face_color=face_color,
    )

    out = pad_reference_for_framing(
        src,
        face_bbox=face_box,
        framing=framing,
        target_size=(canvas_w, canvas_h),
    )
    img = Image.open(io.BytesIO(out)).convert("RGB")
    sample_x = canvas_w // 2

    # Inset by 20% from the face edges to avoid JPEG-softened borders.
    inset = int(0.20 * expected_face_h / 2)
    probe_top_y = max(0, expected_cy - expected_face_h // 2 + inset)
    probe_bottom_y = min(canvas_h - 1, expected_cy + expected_face_h // 2 - inset)
    probe_center_y = expected_cy

    for label, y in (
        ("top", probe_top_y),
        ("center", probe_center_y),
        ("bottom", probe_bottom_y),
    ):
        sample = img.getpixel((sample_x, y))
        distance = _color_distance(sample, face_color)
        assert distance < 25.0, (
            f"framing={framing!r}: face_color expected at the {label} "
            f"of the foreground face (x={sample_x}, y={y}); got "
            f"sample={sample} (distance={distance:.1f}). Face_height_"
            "ratio geometry no longer matches the cinematic anchor."
        )
