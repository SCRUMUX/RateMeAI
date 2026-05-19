"""Reference image preprocessing for edit-model compositions.

Background
----------

Edit-model providers (GPT Image 2 Edit, Nano Banana 2 Edit) infer the
target aspect / framing from the input image they receive. On
"tight-selfie" inputs — face_area_ratio > 0.30, often a Telegram
``photo[-1]`` preview (~1280 px head-and-shoulders crop) — the model
duplicates the input's head/torso ratio verbatim. The result is the
"glued head" pathology: a half-body or full-body composition with an
oversized head pasted on a smaller body. Numerical anchors in the
prompt help, but they cannot fully overcome the spatial cue from the
reference itself.

:func:`pad_reference_for_framing` solves the spatial half of the
problem deterministically: it re-positions the detected face on a
canvas of the **target** aspect and **target** relative size, filling
the negative space with edge-blurred extensions of the original.
After this preprocessor runs, the edit model sees a reference that
ALREADY has the correct anatomical layout for the requested framing,
and it only has to repaint clothing / background.

Geometry is gated by the caller (see ``executor`` ``should_pad``
decision) — this module trusts that its inputs are already filtered
to the "tight selfie + portrait/half/full body" cohort.

v1.68 (May 2026) — bbox contract fix
-------------------------------------

Up to v1.67 :func:`pad_reference_for_framing` destructured the
``face_bbox`` argument as ``(x, y, w, h)``, but its only producer
(:func:`src.services.input_quality.analyze_input_quality`) has always
emitted ``(x1, y1, x2, y2)``. The mismatch silently scrambled the
face-height and face-centre computations on every call:

* The legacy code read ``fh = y2`` as if it were "face height in
  pixels", when in reality it is "distance from the top of the
  image to the chin" — typically 1.5×-3× the real face height.
* This made the uniform scale factor undershoot the target, so the
  face landed *too small* on the canvas; combined with a wrong
  centre offset (``face_cy = y1 + y2/2``) it drifted toward the top
  of the canvas.

The net effect on tight selfies was the opposite of what padding
was designed to deliver: instead of normalising head/body ratio,
the operation handed edit-models a near-original tight crop with a
distinctive empty halo around the head. Edit-models reacted by
reproducing the visible "glued head" artefact almost verbatim.

The fix is gated by ``settings.csl_padding_v2_enabled`` (default
True) so the legacy interpretation remains available as a 30-second
rollback while the corrected code bakes in production.

v1.65 / v1.68 alignment
------------------------

The textual doctrine (``_COMPOSITION_NUMERICAL_HINT`` in
``src.prompts.image_gen``) and the geometric doctrine
(``_FRAMING_GEOMETRY`` below) describe the same target layout from
two angles:

* Textual side (v1.68): ``Reframe the reference into a
  head-and-shoulders bust shot taken at chest height, the head
  occupying roughly the upper third of the canvas height …`` —
  ``face_height_ratio=0.28`` is exactly "upper third of the
  canvas height".
* Half body side: prompt says ``medium waist-up shot``, ``head
  occupying roughly the upper fifth of the canvas height``, ``both
  shoulders fully visible``, ``torso extending to the belt line``;
  ``face_height_ratio=0.15`` + ``face_center_y_ratio=0.20`` lays
  out exactly that on the canvas.
* Full body side: prompt says ``full-length standing shot from a
  slight low angle, head occupying roughly an eighth of the canvas
  height, torso, legs and feet all visible centred in the frame``;
  ``face_height_ratio=0.08`` + ``face_center_y_ratio=0.12`` lays
  out exactly that.

The lens spec lives in ``PHOTOREAL_BLOCK`` only (v1.68 dedupe);
this anchor stays lens-agnostic so the model doesn't receive two
copies of the same lens token.

Prompt and reference push the model in the same direction; they
must stay co-curated when either side is tuned.
"""

from __future__ import annotations

import io
import logging
from typing import Final

from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)


# Target face geometry per framing.
#
# ``face_height_ratio``  — fraction of canvas height the face should
#                          occupy (sets the head/body proportion).
# ``face_center_y_ratio`` — fraction down the canvas where the face
#                          centre lands (rule-of-thirds-ish: face sits
#                          in the upper part of the frame, leaving
#                          room for shoulders/torso/legs below).
#
# Values mirror :data:`src.prompts.image_gen._COMPOSITION_NUMERICAL_HINT`.
# Whatever the prompt says ("medium waist-up shot…torso extending to
# the belt line" for half_body), the canvas geometry matches so
# prompt + reference push the model in the same direction. See the
# module docstring for the row-by-row textual/geometric mapping.
_FRAMING_GEOMETRY: Final[dict[str, dict[str, float]]] = {
    "portrait":  {"face_height_ratio": 0.28, "face_center_y_ratio": 0.30},
    "half_body": {"face_height_ratio": 0.15, "face_center_y_ratio": 0.20},
    "full_body": {"face_height_ratio": 0.08, "face_center_y_ratio": 0.12},
}


# Edge-blur radius, in pixels, used to fill the negative space. A
# blurred extension of the existing pixels reads to edit models as
# "out-of-focus background" rather than "hard cut-out", which would
# otherwise pull attention back to the original tight crop.
_EDGE_BLUR_RADIUS: Final[int] = 80


def pad_reference_for_framing(
    image_bytes: bytes,
    face_bbox: tuple[int, int, int, int],
    framing: str,
    *,
    target_size: tuple[int, int] = (1280, 1600),
) -> bytes:
    """Re-compose ``image_bytes`` onto a canvas of ``target_size`` so
    that the face sits at the geometry expected by ``framing``.

    The transformation has three stages:

    1. Resolve the **target** face height in canvas pixels from
       :data:`_FRAMING_GEOMETRY`; resolve the **target** face centre.
    2. Compute the uniform scale that maps the input's current face
       height to the target face height; resize the whole input by
       that scale (preserves head/torso ratio inside the input).
    3. Paste the scaled input onto a freshly created canvas, placing
       the face centre at the target coordinates. Fill the canvas
       background with an edge-blurred extension of the scaled input
       (a heavy box-blur copy stretched to cover the full canvas).

    Args:
        image_bytes: raw JPEG / PNG bytes of the user reference.
        face_bbox: ``(x1, y1, x2, y2)`` face bounding box in input
            image coordinates (top-left and bottom-right corners),
            as produced by
            :func:`src.services.input_quality.analyze_input_quality`.
            ``x2 > x1`` and ``y2 > y1`` is required.

            .. note:: v1.68 (May 2026) — the legacy implementation
               destructured this tuple as ``(x, y, w, h)``, which
               silently produced wildly wrong scale + centre on every
               call (the "huge head, glued on" pathology). The fix is
               gated by ``settings.csl_padding_v2_enabled`` so the
               legacy interpretation remains available as a rollback
               while the corrected version bakes in production.
        framing: ``"portrait" | "half_body" | "full_body"``. Anything
            else raises ``ValueError``.
        target_size: ``(width, height)`` of the output canvas. The
            default matches ``portrait_4_3`` ≈ 1280x1600 (the
            standard non-doc style aspect after v1.64). Callers that
            want a different aspect (e.g. ``square_hd``) can pass
            their own.

    Returns:
        JPEG bytes of the padded canvas at quality 92.

    Raises:
        ValueError: ``framing`` not in :data:`_FRAMING_GEOMETRY` or
            ``face_bbox`` is degenerate.
        OSError: ``PIL`` failed to decode the input bytes.
    """
    if framing not in _FRAMING_GEOMETRY:
        raise ValueError(
            f"Unknown framing {framing!r}; expected one of "
            f"{sorted(_FRAMING_GEOMETRY)}"
        )

    # v1.68 — gated bbox-format fix. The legacy branch interpreted the
    # tuple as ``(x, y, w, h)`` while
    # :class:`src.services.input_quality.InputQualityReport` always
    # produces ``(x1, y1, x2, y2)``. The v2 branch reads the tuple
    # correctly. Default is v2 (the fix); flip
    # ``csl_padding_v2_enabled=false`` to fall back if the corrected
    # geometry produces unforeseen regressions on a specific style.
    try:
        from src.config import settings as _settings
        _use_v2 = bool(getattr(_settings, "csl_padding_v2_enabled", True))
    except Exception:
        _use_v2 = True

    if _use_v2:
        x1, y1, x2, y2 = face_bbox
        fw = x2 - x1
        fh = y2 - y1
        face_cx_src = x1 + fw / 2.0
        face_cy_src = y1 + fh / 2.0
        version_label = "v2"
    else:
        # Legacy interpretation kept verbatim for rollback parity.
        fx, fy, fw, fh = face_bbox
        face_cx_src = fx + fw / 2.0
        face_cy_src = fy + fh / 2.0
        version_label = "v1"

    if fw <= 0 or fh <= 0:
        raise ValueError(
            f"Degenerate face_bbox={face_bbox!r}; width/height must be > 0"
        )

    geom = _FRAMING_GEOMETRY[framing]
    canvas_w, canvas_h = target_size

    # --- Stage 1: target face geometry on canvas ------------------------
    target_face_h_px = max(1, int(canvas_h * geom["face_height_ratio"]))
    target_face_cx_px = canvas_w // 2
    target_face_cy_px = int(canvas_h * geom["face_center_y_ratio"])

    # --- Stage 2: resize input so its face matches target_face_h --------
    scale = target_face_h_px / float(fh)
    src = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    new_w = max(1, int(round(src.width * scale)))
    new_h = max(1, int(round(src.height * scale)))
    scaled = src.resize((new_w, new_h), Image.LANCZOS)

    # Face centre in the scaled image.
    scaled_face_cx = int(round(face_cx_src * scale))
    scaled_face_cy = int(round(face_cy_src * scale))

    # --- Stage 3a: build edge-blur background ----------------------------
    # We stretch the scaled image to cover the full canvas at low
    # quality and blur it heavily — the colours/exposure match the
    # foreground so the seam between original and fill is soft.
    bg_source = scaled.resize((canvas_w, canvas_h), Image.BILINEAR)
    background = bg_source.filter(
        ImageFilter.GaussianBlur(radius=_EDGE_BLUR_RADIUS)
    )

    # --- Stage 3b: paste the scaled input onto the canvas ---------------
    paste_x = target_face_cx_px - scaled_face_cx
    paste_y = target_face_cy_px - scaled_face_cy

    canvas = background.copy()
    canvas.paste(scaled, (paste_x, paste_y))

    out = io.BytesIO()
    canvas.save(out, format="JPEG", quality=92)
    padded = out.getvalue()

    try:
        from src.metrics import PADDING_GEOMETRY_VERSION

        PADDING_GEOMETRY_VERSION.labels(
            version=version_label,
            framing=framing,
        ).inc()
    except Exception:
        pass

    logger.info(
        "reference_padded version=%s framing=%s in=(%dx%d) out=(%dx%d) "
        "scale=%.3f paste=(%d,%d) face_target_h=%d face_src_h=%d",
        version_label,
        framing,
        src.width,
        src.height,
        canvas_w,
        canvas_h,
        scale,
        paste_x,
        paste_y,
        target_face_h_px,
        int(fh),
    )
    return padded
